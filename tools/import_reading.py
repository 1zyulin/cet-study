"""Convert one supported, text-based CET reading PDF into local practice.

Only the explicit 26--55 layout is supported. Missing answers, options or
headings abort conversion rather than guessing. pdfplumber and pypdf are optional
dependencies for this command, not dependencies of the learning application.
"""
import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.content import ContentError, validate_pack
from app.store import Store


class ReadingImportError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise ReadingImportError(message)


def _clean(text):
    _require(isinstance(text, str) and text.strip(), 'PDF 未抽取到可用文本')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # Our saved diagnostic text has explicit page delimiters. They are not text
    # from the source paper and must not enter an article.
    return re.sub(r'^=== PAGE \d+ ===\s*\n', '', text, flags=re.M).strip()


def _flat(text):
    return re.sub(r'\s+', ' ', text).strip()


def _single(pattern, text, label, flags=re.M):
    matches = list(re.finditer(pattern, text, flags))
    _require(len(matches) == 1, f'{label} 缺失、重复或格式不支持')
    return matches[0]


def parse_answers(text):
    """Read complete number/letter rows under a reading-answer heading.

    Supports both the paper's 10 + 10 + 10 KEYS rows and the separately supplied
    quick-answer PDF's 13 + 13 + 4 rows. It does not infer answers from prose.
    """
    text = unicodedata.normalize('NFKC', _clean(text))
    keys = list(re.finditer(r'^\s*KEYS\s*$', text, re.M))
    _require(len(keys) <= 1, 'KEYS 标题重复')
    if keys:
        text = text[keys[0].end():]
    header = _single(r'^\s*Part\s+III\s+Reading\s+Comprehension[^\n]*$',
                     text, '阅读答案标题')
    text = text[header.end():]
    end = re.search(r'^\s*Part\s+IV\s+Translation\b', text, re.M)
    if end:
        text = text[:end.start()]
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    _require(rows and len(rows) % 2 == 0, '阅读答案须为完整题号行及答案行')
    answers, order = {}, []
    for offset in range(0, len(rows), 2):
        numbers, letters = rows[offset].split(), rows[offset + 1].split()
        _require(all(re.fullmatch(r'\d{2}', n) for n in numbers), '阅读答案题号行无法识别')
        _require(len(numbers) == len(letters) and
                 all(re.fullmatch(r'[A-O]', a) for a in letters), '阅读答案数量或字母错误')
        for number, answer in zip(numbers, letters):
            number = int(number)
            _require(number not in answers, f'阅读答案题号 {number} 重复')
            answers[number] = answer
            order.append(number)
    _require(order == list(range(26, 56)), '阅读答案必须完整且依次覆盖 26—55')
    return answers


def _options(text, expected, label):
    markers = list(re.finditer(r'(?<![A-Za-z0-9])([A-Z])\)', text))
    _require(markers and not text[:markers[0].start()].strip(), f'{label} 选项开头无法识别')
    values = {}
    for i, marker in enumerate(markers):
        key = marker.group(1)
        _require(key not in values, f'{label} 选项 {key} 重复')
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        value = _flat(text[marker.end():end])
        _require(value and '[missing]' not in value.lower(), f'{label} 选项 {key} 缺失')
        values[key] = value
    _require(set(values) == set(expected), f'{label} 选项须完整包含 {expected}')
    return [{'id': key, 'text': values[key]} for key in expected]


def _numbered(text, numbers, label):
    # Two otherwise identical source PDFs omit the full stop after 48/43.
    # A space followed by an English stem is still unambiguous inside a question
    # block; answer-table number rows and option rows do not match this rule.
    markers = list(re.finditer(r'^\s*(\d{2})(?:[.．]\s*|[ \t]+(?=[A-Za-z]))', text, re.M))
    _require([int(m.group(1)) for m in markers] == list(numbers),
             f'{label} 须完整包含依次排列的 {numbers[0]}—{numbers[-1]} 题')
    _require(not text[:markers[0].start()].strip(), f'{label} 题号前出现不支持的内容')
    return [(int(m.group(1)), text[m.end():markers[i + 1].start()
            if i + 1 < len(markers) else len(text)].strip())
            for i, m in enumerate(markers)]


def _question(number, prompt, options, answers):
    _require(prompt.strip(), f'第 {number} 题题干缺失')
    _require(answers[number] in {o['id'] for o in options},
             f'第 {number} 题答案没有对应选项')
    return {'id': f'q{number}', 'type': 'choice', 'prompt': prompt,
            'options': options, 'answer': answers[number],
            'explanation': '答案依据来源 PDF 的阅读答案表；原文与答案尚待人工校对。'}


def parse_reading_text(text, *, answer_text=None):
    text = _clean(text)
    keys = list(re.finditer(r'^\s*KEYS\s*$', text, re.M))
    _require(len(keys) <= 1, 'KEYS 标题重复')
    internal = parse_answers(text) if keys else None
    external = parse_answers(answer_text) if answer_text is not None else None
    _require(internal is not None or external is not None, '须提供完整阅读答案表')
    if internal is not None and external is not None:
        _require(internal == external, '原卷与独立答案文件的阅读答案不一致')
    answers = internal if internal is not None else external
    # Exclude KEYS before checking section headings to avoid mixing the answer
    # page into either the second article or a question's final option.
    body = text[:keys[0].start()] if keys else text
    part = _single(r'^\s*Part\s+(?:III|Ⅲ)\s+Reading\s+Comprehension[^\n]*$',
                   body, '阅读部分标题')
    translation = _single(r'^\s*Part\s+(?:IV|Ⅳ)\s+Translation[^\n]*$',
                          body, '翻译部分边界')
    _require(part.end() < translation.start(), '阅读与翻译标题顺序错误')
    reading = body[part.end():translation.start()]
    headings = list(re.finditer(r'^\s*Section\s+([ABC])\s*$', reading, re.M))
    _require([m.group(1) for m in headings] == ['A', 'B', 'C'], '阅读须有依次排列的 Section A/B/C')
    blocks = [reading[m.end():headings[i + 1].start() if i < 2 else len(reading)].strip()
              for i, m in enumerate(headings)]

    cloze = blocks[0]
    _require(cloze.startswith('Directions:') and 'ten blanks' in cloze and 'word bank' in cloze,
             '选词填空说明格式不支持')
    bank = _single(r'^\s*A\)\s*', cloze, '选词填空词库开头')
    before_bank = cloze[:bank.start()]
    blanks = list(re.finditer(r'_{2,}\s*(\d{2})\s*_{2,}', before_bank))
    _require([int(m.group(1)) for m in blanks] == list(range(26, 36)), '选词填空须完整包含 26—35 空')
    separators = list(re.finditer(r'\n[ \t]*\n', before_bank[:blanks[0].start()]))
    _require(separators, '无法可靠区分选词填空说明与原文')
    instruction_ends = list(re.finditer(
        r'You\s+may\s+not\s+use\s+any\s+of\s+the\s+words\s+in\s+the\s+bank\s+more\s+than\s+once[.]',
        before_bank))
    _require(len(instruction_ends) <= 1, '选词填空说明结束句重复')
    passage_start = instruction_ends[0].end() if instruction_ends else separators[0].end()
    _require(passage_start < blanks[0].start(), '选词填空说明与原文边界错误')
    # The first numbered gap can occur in the second paragraph. Starting at the
    # last blank line before gap 26 would silently drop an introductory paragraph.
    passage = before_bank[passage_start:].strip()
    word_bank = _options(cloze[bank.start():], 'ABCDEFGHIJKLMNO', '选词填空')
    cloze_section = {'id': 'reading-cloze', 'kind': 'reading', 'title': '选词填空（26—35）',
                     'passage': passage, 'questions': [
                         _question(n, f'第 {n} 空：从词库中选择合适的单词。', word_bank, answers)
                         for n in range(26, 36)]}

    matching = blocks[1]
    _require(matching.startswith('Directions:') and 'paragraph' in matching,
             '长篇阅读说明格式不支持')
    paragraph_start = _single(r'^\s*A\)\s*', matching, '长篇阅读段落开头')
    first_statement = _single(r'^\s*36[.．]\s*', matching, '长篇阅读第 36 题')
    _require(paragraph_start.start() < first_statement.start(), '长篇阅读原文或题号顺序错误')
    article = matching[paragraph_start.start():first_statement.start()].strip()
    paragraphs = list(re.finditer(r'^\s*([A-O])\)\s*', article, re.M))
    labels = [m.group(1) for m in paragraphs]
    _require(10 <= len(labels) <= 15 and labels == list('ABCDEFGHIJKLMNO'[:len(labels)]),
             '长篇阅读段落字母缺失、重复或顺序错误')
    for i, marker in enumerate(paragraphs):
        end = paragraphs[i + 1].start() if i + 1 < len(paragraphs) else len(article)
        _require(article[marker.end():end].strip(), f'长篇阅读段落 {marker.group(1)} 没有原文')
    title_region = matching[:paragraph_start.start()].strip()
    title = title_region.splitlines()[-1].strip()
    _require(title and not title.startswith('Directions:') and 'Answer Sheet' not in title,
             '无法可靠区分长篇阅读说明与标题')
    paragraph_options = [{'id': label, 'text': f'段落 {label}'} for label in labels]
    matching_section = {'id': 'reading-matching', 'kind': 'reading', 'title': '长篇阅读匹配（36—45）',
                        'passage': title + '\n\n' + article, 'questions': [
                            _question(n, _flat(prompt), paragraph_options, answers)
                            for n, prompt in _numbered(matching[first_statement.start():], range(36, 46), '长篇阅读')]}

    careful = blocks[2]
    _require(careful.startswith('Directions:'), '仔细阅读说明格式不支持')
    passage_headers = list(re.finditer(r'^\s*Passage\s+(One|Two)\s*$', careful, re.M))
    _require([m.group(1) for m in passage_headers] == ['One', 'Two'], '仔细阅读须完整包含 Passage One/Two')
    articles, careful_questions = [], []
    for index, header in enumerate(passage_headers):
        chunk = careful[header.end():passage_headers[index + 1].start()
                        if index == 0 else len(careful)].strip()
        first, last = (46, 50) if index == 0 else (51, 55)
        hint = _single(r'^\s*Questions\s+(\d+)\s+to\s+(\d+)\s+are based on the following passage[.]\s*$',
                       chunk, '仔细阅读题号范围')
        _require((int(hint.group(1)), int(hint.group(2))) == (first, last), '仔细阅读文章与题号范围不一致')
        _require(not chunk[:hint.start()].strip(), '文章题号提示前存在不支持的内容')
        chunk = chunk[hint.end():].strip()
        first_q = _single(rf'^\s*{first}[.．]\s*', chunk, f'仔细阅读第 {first} 题')
        article = chunk[:first_q.start()].strip()
        _require(article and not re.search(r'^\s*[A-D]\)', article, re.M), '仔细阅读原文缺失或混入选项')
        articles.append(f'Passage {header.group(1)}（{first}—{last}）\n\n{article}')
        for number, question in _numbered(chunk[first_q.start():], range(first, last + 1), '仔细阅读'):
            option_start = _single(r'^\s*A\)\s*', question, f'第 {number} 题选项开头')
            stem = _flat(question[:option_start.start()])
            options = _options(question[option_start.start():], 'ABCD', f'第 {number} 题')
            prompt = f'Passage {header.group(1)} · 第 {number} 题\n{stem}'
            _require(stem, f'第 {number} 题题干缺失')
            careful_questions.append(_question(number, prompt, options, answers))
    return [cloze_section, matching_section,
            {'id': 'reading-careful', 'kind': 'reading', 'title': '仔细阅读（46—55）',
             'passage': '\n\n'.join(articles), 'questions': careful_questions}]


def parse_careful_reading_text(text, *, answer_text):
    """Read only 46--55 from the explicitly identified reformatted CET6 layout.

    This source omits original directions and question-range labels, and moves
    matching statements before its article. Do not pass it through the ordinary
    three-section parser or present ten questions as a complete reading paper.
    """
    text = _clean(text)
    answers_text = unicodedata.normalize('NFKC', _clean(answer_text))
    answer_header = _single(r'^\s*Part\s+III\s+Reading\s+Comprehension\s*$',
                            answers_text, '独立阅读答案标题')
    answer_end = _single(r'^\s*Part\s+IV\s+Translation\s*$', answers_text, '独立阅读答案结尾')
    answer_body = answers_text[answer_header.end():answer_end.start()]
    rows = re.findall(r'^\s*((?:\d{2}\s+[A-Z]\s+)*\d{2}\s+[A-Z])\s*$', answer_body, re.M)
    values, order = {}, []
    for row in rows:
        tokens = row.split()
        for number, letter in zip(tokens[::2], tokens[1::2]):
            number = int(number)
            _require(number not in values, f'独立答案题号 {number} 重复')
            values[number] = letter
            order.append(number)
    _require(order == list(range(26, 56)), '独立答案表须完整且依次覆盖 26—55')
    _require(all(values[n] in 'ABCD' for n in range(46, 56)), '仔细阅读答案须为 A—D')
    part = _single(r'^\s*Part\s+III\s*·\s*Reading\s+Comprehension\s*$', text, '重排版阅读标题')
    section = _single(r'^\s*Section\s+C\s+Passages\s*$', text, '重排版仔细阅读标题')
    end = _single(r'^\s*Part\s+IV\s*·\s*Translation\s*$', text, '重排版翻译边界')
    _require(part.end() < section.start() < end.start(), '重排版部分标题顺序错误')
    body = text[section.end():end.start()]
    headers = list(re.finditer(r'^\s*Passage\s+(One|Two)\s*$', body, re.M))
    _require([m.group(1) for m in headers] == ['One', 'Two'], '须完整包含两篇仔细阅读')
    _require(not body[:headers[0].start()].strip(), '首篇文章前出现不支持的内容')
    articles, questions = [], []
    for index, header in enumerate(headers):
        chunk = body[header.end():headers[index + 1].start() if index == 0 else len(body)]
        first, last = (46, 50) if index == 0 else (51, 55)
        first_q = _single(rf'^\s*{first}[.．]\s*', chunk, f'仔细阅读第 {first} 题')
        article = chunk[:first_q.start()].strip()
        _require(article and not re.search(r'^\s*(?:\d{2}[.．]|[A-D]\))', article, re.M),
                 '重排版原文缺失或混入选项/题号')
        articles.append(f'Passage {header.group(1)}（{first}—{last}）\n\n{article}')
        for number, question in _numbered(chunk[first_q.start():], range(first, last + 1), '仔细阅读'):
            option_start = _single(r'^\s*A\)\s*', question, f'第 {number} 题选项开头')
            stem = _flat(question[:option_start.start()])
            _require(stem, f'第 {number} 题题干缺失')
            options = _options(question[option_start.start():], 'ABCD', f'第 {number} 题')
            questions.append(_question(number, f'Passage {header.group(1)} · 第 {number} 题\n{stem}',
                                       options, values))
    return [{'id': 'reading-careful', 'kind': 'reading', 'title': '仔细阅读（46—55，仅此部分）',
             'passage': '\n\n'.join(articles), 'questions': questions}]


def build_pack(text, *, level, year, session, paper_number, source_url,
               answer_text=None, exam_id=None, careful_only=False):
    _require(level in ('CET4', 'CET6'), 'level 须为 CET4/CET6')
    _require(type(year) is int and 1987 <= year <= 2100, '年份错误')
    _require(type(paper_number) is int and 1 <= paper_number <= 3, '套号须为 1—3')
    _require(isinstance(session, str) and re.fullmatch(rf'{year}[.](03|06|09|12)', session),
             '考次须为与年份一致的 YYYY.MM')
    _require(not careful_only or level == 'CET6', '重排版仔细阅读目前仅支持 CET6')
    suffix = 'careful-reading' if careful_only else 'reading'
    scope = '仅仔细阅读 46—55' if careful_only else '仅阅读'
    exam_id = exam_id or f"community-{level.lower()}-{session.replace('.', '-')}-{paper_number}-{suffix}"
    exam = {'id': exam_id, 'title': f'{year} 年 {session[-2:]} 月 {level} 第 {paper_number} 套 · {scope}',
            'level': level, 'year': year, 'session': f'{session} 第{paper_number}套',
            'source_kind': 'past_paper', 'source': {
                'title': '0609x/CET46-Resources 原题 PDF 与阅读答案表（含末页 KEYS 或独立答案文件）',
                'url': source_url, 'verified': False,
                'rights': '真题与相关解析权利归原权利人。仅供本地学习转换；第三方内容不随项目 MIT 代码授权。社区原文与答案尚未逐页人工校对。'},
            'sections': (parse_careful_reading_text(text, answer_text=answer_text) if careful_only
                         else parse_reading_text(text, answer_text=answer_text))}
    pack = {'schema_version': 1, 'exams': [exam]}
    validate_pack(pack)
    return pack


def read_pdf_text(path):
    # Positional extraction avoids pypdf's intra-word spacing artifacts in some
    # publisher PDFs. Keep layout line breaks; never remove all spaces or infer
    # a spelling correction from a dictionary or language model.
    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None
    if pdfplumber is not None:
        with pdfplumber.open(path) as pdf:
            texts = [page.extract_text(layout=True) or '' for page in pdf.pages]
        _require(texts and all(text.strip() for text in texts),
                 'PDF 包含无文本页；不支持扫描件或 OCR 猜测')
        return '\n\n'.join('\n'.join(line.rstrip() for line in text.splitlines())
                           for text in texts)
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise ReadingImportError('此导入命令需要可选的 pypdf；请使用已安装 pypdf 的 Python 环境运行') from error
    reader = PdfReader(path)
    _require(not reader.is_encrypted, '不支持加密 PDF')
    texts = [page.extract_text() or '' for page in reader.pages]
    _require(texts and all(text.strip() for text in texts), 'PDF 包含无文本页；不支持扫描件或 OCR 猜测')
    return '\n\n'.join(texts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', required=True, type=Path)
    parser.add_argument('--answers', type=Path)
    parser.add_argument('--level', required=True, choices=['CET4', 'CET6'])
    parser.add_argument('--year', required=True, type=int)
    parser.add_argument('--session', required=True)
    parser.add_argument('--set', dest='paper_number', required=True, type=int)
    parser.add_argument('--source-url', required=True)
    parser.add_argument('--exam-id')
    parser.add_argument('--careful-only', action='store_true',
                        help='明确选择已支持的 CET6 重排版，仅导入仔细阅读 46—55')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--import-local', action='store_true')
    args = parser.parse_args(argv)
    try:
        text = read_pdf_text(args.pdf)
        answers = read_pdf_text(args.answers) if args.answers else None
        pack = build_pack(text, level=args.level, year=args.year, session=args.session,
                          paper_number=args.paper_number, source_url=args.source_url,
                          answer_text=answers, exam_id=args.exam_id, careful_only=args.careful_only)
        exams = validate_pack(pack)
        output = args.output or args.data_dir / 'imports' / f"reading-{exams[0]['id']}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding='utf-8')
        if args.import_local:
            args.data_dir.mkdir(parents=True, exist_ok=True)
            store = Store(args.data_dir / 'study.sqlite3')
            backup_dir = args.data_dir / 'recovery'
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            backup = backup_dir / f'reading-before-import-{stamp}.json'
            backup.write_text(json.dumps(store.backup(), ensure_ascii=False, indent=2), encoding='utf-8')
            store.import_exams(exams)
        print(json.dumps({'output': str(output), 'exam_id': exams[0]['id'],
                          'questions': sum(len(s['questions']) for s in exams[0]['sections']),
                          'imported_local': args.import_local,
                          'verified': False}, ensure_ascii=False))
    except (ReadingImportError, ContentError, OSError, ValueError) as error:
        parser.exit(2, f'阅读导入失败：{error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
