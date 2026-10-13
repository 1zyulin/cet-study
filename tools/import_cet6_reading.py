"""Convert text-based CET6 original papers and their supplied answers locally.

The converter accepts the standard paper and the explicitly reformatted 2025
paper layouts. It requires all thirty reading questions and all source answers;
scanned pages, missing words or options are reported rather than synthesized.
PDF/Word libraries are optional dependencies of this conversion command.
"""
import argparse
import hashlib
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.content import validate_pack
from tools.import_reading import ReadingImportError, _require, _flat, _options, _question

ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def extract_document(path):
    """Preserve Word body order, including tables, and PDF positional text."""
    path = Path(path)
    if path.suffix.lower() == '.docx':
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        document = Document(path)
        result = []
        for child in document.element.body.iterchildren():
            if child.tag.endswith('}p'):
                result.append(Paragraph(child, document).text)
            elif child.tag.endswith('}tbl'):
                table = Table(child, document)
                for row in table.rows:
                    # Some Word source options span several cells in one row.
                    result.append(' '.join(cell.text for cell in row.cells))
        return '\n'.join(result)
    if path.suffix.lower() == '.pdf':
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            _require(not getattr(pdf, 'is_encrypted', False), '不支持加密 PDF')
            pages = [page.extract_text(layout=True) or '' for page in pdf.pages]
        _require(any(page.strip() for page in pages), '扫描 PDF 没有文本层，需要其他可核对的文本来源')
        return '\n\n'.join(pages)
    if path.suffix.lower() == '.md':
        return plain_markdown(path.read_text(encoding='utf-8'))
    _require(path.suffix.lower() == '.txt', '来源文件须为 PDF、DOCX、Markdown 或已核对的 TXT')
    return path.read_text(encoding='utf-8')


def plain_markdown(text):
    """Remove only Markdown presentation; preserve the source's literal words."""
    result = []
    for line in text.splitlines():
        line = re.sub(r'^#{1,6}\s+', '', line)
        line = line.replace('**', '')
        line = re.sub(r'_([^_\n]+)_', r'\1', line)
        line = re.sub(r'<u>\s*(?:&emsp;|&#8195;)*\s*(2[6-9]|3[0-5])\s*(?:&emsp;|&#8195;)*\s*</u>', r'___\1___', line)
        line = html.unescape(re.sub(r'</?u>', '', line))
        if line.startswith('Part '):
            line = line.replace(' / ', ' ')
        if line.strip().startswith('|'):
            cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
            if all(not cell or re.fullmatch(r'[-: ]+', cell) for cell in cells):
                continue
            line = ' '.join(cells)
        result.append(line)
    return '\n'.join(result)


def apply_document_corrections(text, filename, corrections, source_path=None):
    """Apply explicit, source-backed local transcription corrections only."""
    entries = corrections.get('corrections', {}).get(filename, [])
    for entry in entries:
        if entry.get('kind'):
            _require(source_path is not None and
                     hashlib.sha256(Path(source_path).read_bytes()).hexdigest() == entry.get('source_sha256'),
                     '更正条目与来源文件指纹不匹配')
            _require(entry.get('evidence_url', '').startswith('https://'), '更正条目缺少核对来源')
            # Public corrections describe short marker tokens, never exam text.
            old, new = entry.get('old', ''), entry.get('new', '')
            _require(isinstance(old, str) and isinstance(new, str) and 0 < len(old) <= 5 and 0 < len(new) <= 5,
                     '标记更正须使用简短标签')
            keys = re.search(r'^\s*KEYS\s*$', text, re.M)
            limit = keys.start() if keys else len(text)
            part = _one(r'^\s*Part\s+(?:III|Ⅲ)\s*[·]?\s*Reading\s+Comprehension[^\n]*$', text[:limit], '更正阅读标题')
            ending = _one(r'^\s*Part\s+(?:IV|Ⅳ)\s*[·]?\s*Translation[^\n]*$', text[:limit], '更正翻译边界')
            reading = text[part.end():ending.start()]
            if entry['kind'] == 'wordbank-label':
                first = _one(r'^\s*Section\s+A\s*$', reading, '更正词库范围')
                last = _one(r'^\s*Section\s+B\s*$', reading, '更正词库边界')
                start, end = first.end(), last.start()
            else:
                _require(entry['kind'] in ('question-leading-token', 'question-option-label'), '更正类型不支持')
                number = entry.get('question')
                _require(isinstance(number, int) and 36 <= number <= 55, '更正题号不支持')
                marker_pattern = r'(?m)^[ \t]*{}[.．][ \t]*(?![A-D][).])(?=[A-Za-z“"\']|1t\b)'
                first = _one(marker_pattern.format(number), reading, '更正题号')
                last = _one(marker_pattern.format(number + 1), reading, '更正下一题') if number < 55 else None
                start, end = first.end(), last.start() if last else len(reading)
            region = reading[start:end]
            if entry['kind'] == 'question-leading-token':
                pattern = r'^' + re.escape(old) + r'\b'
            else:
                pattern = r'(?<![A-Za-z0-9])' + re.escape(old)
            _require(len(re.findall(pattern, region)) == 1, '更正标签须在限定范围内恰好出现一次')
            updated = re.sub(pattern, lambda _: new, region, count=1)
            absolute_start, absolute_end = part.end() + start, part.end() + end
            text = text[:absolute_start] + updated + text[absolute_end:]
            continue
        _require(isinstance(entry.get('old'), str) and entry['old'] and
                 isinstance(entry.get('new'), str) and entry['new'] and
                 entry.get('evidence_url', '').startswith('https://'),
                 '本地校对条目缺少原文、更正文或核对来源')
        _require(text.count(entry['old']) == 1, '校对原文须在当前文件中恰好出现一次')
        text = text.replace(entry['old'], entry['new'])
    return text


def indexed_source_records(root=ROOT):
    """Derive cache filenames from public indexes without a private receipt."""
    index = json.loads((root / 'web/source-index.json').read_text(encoding='utf-8'))
    records = {}
    for record in index['files']:
        if record['level'] != 'CET6' or record['kind'] not in ('paper_pdf', 'paper_word', 'answer'):
            continue
        session = re.search(r'/((?:2023|2024|2025)[.]\d{2})/', record['path'])
        number = re.search(r'第([123])套|_([123])(?:_ans)?[.]', record['path'])
        if not session or not number:
            continue
        name = 'cet6_' + session[1].replace('.', '_') + '_' + (number[1] or number[2])
        if record['kind'] == 'answer':
            name += '_ans'
        name += '.docx' if record['kind'] == 'paper_word' else '.pdf'
        records[name] = dict(record, repository=index['source_repository'])
    alternate_path = root / 'web/cet6-alt-source-index.json'
    if alternate_path.exists():
        for record in json.loads(alternate_path.read_text(encoding='utf-8'))['files']:
            records[record['local_name']] = record
    return records


def checked_answer_text(entry, paper, answer):
    """Accept reviewed letters only for their exact source and paper bytes."""
    _require(not entry.get('unreadable'), '核对答案仍有无法辨认项')
    _require(entry.get('paper') == paper.name and
             entry.get('paper_sha256') == hashlib.sha256(paper.read_bytes()).hexdigest(),
             '核对答案与原题文件指纹不匹配')
    _require(entry.get('source_url', '').startswith('https://'), '核对答案缺少来源 URL')
    if entry.get('source_kind') == 'web_answer_table':
        _require(entry.get('evidence') and entry.get('cross_check_url', '').startswith('https://'),
                 '网页答案缺少独立核对来源')
    else:
        _require(entry.get('source') == answer.name and answer.exists() and
                 entry.get('source_sha256') == hashlib.sha256(answer.read_bytes()).hexdigest(),
                 '核对答案与答案文件指纹不匹配')
    answer_text = '\n'.join(f'{n}. {a}' for n, a in entry['answers'].items())
    parse_cet6_answers(answer_text)
    return answer_text


def clean_document(text):
    _require(isinstance(text, str) and text.strip(), '来源没有文本')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'^=== PAGE \d+ ===\s*\n', '', text, flags=re.M)
    # These are page furniture, never the reading article. Keep English text
    # exactly as extracted; only marker glyphs receive Unicode normalization.
    lines = []
    for line in text.splitlines():
        value = line.strip()
        if re.fullmatch(r'.*(?:第\d+页[，,]?\s*共\d+页|第\d+页，共\d+页).*', value):
            continue
        if re.fullmatch(r'(?:六级|英语六级|大学英语六级).*?(?:第[一二三123][套意言]|\[第[一二三123].*?)[\s\]\d]*', value):
            continue
        lines.append(line.rstrip())
    text = '\n'.join(lines)
    # A Cyrillic capital B occurs in one PDF's paragraph labels. Normalize only
    # that label position, leaving the actual article wording untouched.
    text = re.sub(r'(?m)^(\s*)[ВＢ]\)', r'\1B)', text)
    return text.strip()


def parse_cet6_answers(text):
    """Read explicit numbered answer pairs, with duplicate agreement checks."""
    text = unicodedata.normalize('NFKC', clean_document(text))
    keys = list(re.finditer(r'^\s*KEYS\s*$', text, re.M))
    _require(len(keys) <= 1, 'KEYS 答案标题重复')
    if keys:
        body = text[keys[0].end():]
        header = _one(r'^\s*Part\s+III\s+Reading\s+Comprehension[^\n]*$', body, '末页阅读答案标题')
        body = body[header.end():]
        translation = re.search(r'^\s*Part\s+IV\s+Translation\b', body, re.M)
        if translation:
            body = body[:translation.start()]
        rows = [line.strip().split() for line in body.splitlines() if line.strip()]
        _require(rows and len(rows) % 2 == 0, '末页答案须为成对题号行和字母行')
        values, order = {}, []
        for offset in range(0, len(rows), 2):
            numbers, letters = rows[offset], rows[offset + 1]
            _require(len(numbers) == len(letters) and all(re.fullmatch(r'\d{2}', n) for n in numbers)
                     and all(re.fullmatch(r'[A-Z]', a) for a in letters), '末页题号或答案行格式错误')
            for number, letter in zip(numbers, letters):
                number = int(number)
                _require(number not in values, '末页答案题号重复')
                values[number] = letter
                order.append(number)
        _require(order == list(range(26, 56)), '末页答案须完整依次包含 26—55')
        return check_answer_letters(values)
    # Only answer-like number/letter pairs are eligible. Narrative question
    # stems and Chinese translation annotations do not meet this pattern.
    pairs = re.findall(r'(?<!\d)(2[6-9]|[34]\d|5[0-5])\s*(?:[.、．]\s*)?([A-Z]|0)(?=\s|[).。—,，;；]|(?:2[6-9]|[34]\d|5[0-5])\s*[.、]|$)', text)
    values = {}
    for number, letter in pairs:
        number = int(number)
        # Some publisher PDF fonts expose capital O as 0 in their answer table.
        # This is restricted to the fifteen-letter cloze bank, not prose.
        if letter == '0':
            _require(number <= 45, f'第 {number} 题答案字形 0 无法核对')
            letter = 'O'
        if number in values:
            _require(values[number] == letter, f'来源答案中第 {number} 题出现冲突')
        values[number] = letter
    _require(set(values) == set(range(26, 56)),
             '独立答案必须明确覆盖 26—55；缺少：' + ','.join(str(n) for n in range(26, 56) if n not in values))
    return check_answer_letters(values)


def check_answer_letters(values):
    _require(all(values[n] in 'ABCDEFGHIJKLMNO' for n in range(26, 36)), '选词填空答案不在 A—O')
    _require(all(values[n] in ALPHABET for n in range(36, 46)), '长篇阅读答案不在段落字母范围')
    _require(all(values[n] in 'ABCD' for n in range(46, 56)), '仔细阅读答案不在 A—D')
    return values


def _one(pattern, text, label, flags=re.M):
    found = list(re.finditer(pattern, text, flags))
    _require(len(found) == 1, f'{label} 缺失或重复')
    return found[0]


def numbered_blocks(text, first, last, label):
    # Original Word exports sometimes place the next question on the same line
    # as the previous sentence; a numeric marker followed by a letter is clear.
    markers = list(re.finditer(r'(?<!\d)(?P<dot>\d{2})[.．]\s*(?![A-D][).])(?=[A-Za-z“"\']|1t\b)|^[ \t]*(?P<space>\d{2})[ \t]+(?=[A-Za-z])', text, re.M))
    numbers = [int(m.group('dot') or m.group('space')) for m in markers]
    _require(numbers == list(range(first, last + 1)),
             f'{label} 题号须依次完整为 {first}—{last}')
    _require(not text[:markers[0].start()].strip(), f'{label} 首题前存在额外文本')
    return [(numbers[i], text[m.end():markers[i + 1].start() if i + 1 < len(markers) else len(text)].strip())
            for i, m in enumerate(markers)]


def parse_cet6_reading(text, answers):
    text = clean_document(text)
    keys = re.search(r'^\s*KEYS\s*$', text, re.M)
    if keys:
        text = text[:keys.start()]
    part = _one(r'^\s*Part\s+(?:III|Ⅲ)\s*[·]?\s*Reading\s+Comprehension[^\n]*$', text, '阅读标题')
    ending = _one(r'^\s*Part\s+(?:IV|Ⅳ)\s*[·]?\s*Translation[^\n]*$', text, '翻译边界')
    _require(part.end() < ending.start(), '阅读与翻译顺序错误')
    reading = text[part.end():ending.start()]
    headings = list(re.finditer(r'^\s*Section\s+([ABC])(?:\s+(?:Banked Cloze|Long Reading Matching|Passages))?\s*$', reading, re.M))
    _require([m.group(1) for m in headings] == ['A', 'B', 'C'], '阅读须包含完整的 Section A/B/C')
    blocks = [reading[h.end():headings[i + 1].start() if i < 2 else len(reading)].strip() for i, h in enumerate(headings)]

    cloze = blocks[0]
    bank = _one(r'^[ \t]*(?:Word Bank:[ \t]*)?A\)', cloze, '词库开头')
    before = cloze[:bank.start()]
    if before.startswith('Directions:'):
        end_directions = _one(r'You\s*may\s*not\s+use\s+any\s*of\s+the\s*words\s+in\s+the\s+bank\s+more\s+than\s+once[.]?', before, '选词填空说明结束', re.I)
        passage = before[end_directions.end():].strip()
    else:
        passage = before.strip()
    # Numbered blank markers may be underlined, spaced or bare in a reformatted
    # paper. Require the exact sequence; no fill word is invented.
    underlined = list(re.finditer(r'_{2,}\s*(2[6-9]|3[0-5])\s*_{2,}', passage))
    if len(underlined) == 10:
        blanks = underlined
        numbers = [int(m.group(1)) for m in blanks]
    else:
        blanks = list(re.finditer(r'(?<!\d)(?:2[6-9]|3[0-5])(?!\d|%)', passage))
        numbers = [int(m.group()) for m in blanks]
    _require(numbers == list(range(26, 36)), '选词填空空号不完整或重复')
    _require(passage[:blanks[0].start()].strip(), '选词填空原文开头缺失')
    bank_text = re.sub(r'^Word Bank:\s*', '', cloze[bank.start():].strip())
    instruction = re.search(r'^\s*[📌]?\s*选词填空题[：:]', bank_text, re.M)
    if instruction:
        bank_text = bank_text[:instruction.start()]
    options = _options(bank_text.strip(), 'ABCDEFGHIJKLMNO', '选词填空')
    cloze_section = {'id': 'reading-cloze', 'kind': 'reading', 'title': '选词填空（26—35）', 'passage': passage,
                     'questions': [_question(n, f'第 {n} 空：从词库中选择合适的单词。', options, answers) for n in range(26, 36)]}

    matching = blocks[1]
    first_paragraph = _one(r'^\s*A\)\s*', matching, '长篇阅读 A 段')
    first_question = _one(r'(?<!\d)36[.．]\s*(?![A-D][).])(?=[A-Za-z“"\'])', matching, '长篇阅读第36题')
    reformatted = first_question.start() < first_paragraph.start()
    if reformatted:
        article = matching[first_paragraph.start():].strip()
        question_region = matching[first_question.start():first_paragraph.start()]
        boundary = re.search(r'^\s*[📖]?\s*长篇阅读匹配题[：:]|^\s*原文段落', question_region, re.M)
        _require(boundary is not None, '重排版长篇阅读题目与正文分界缺失')
        question_region = question_region[:boundary.start()]
        title = matching[:first_question.start()].strip()
    else:
        article = matching[first_paragraph.start():first_question.start()].strip()
        question_region = matching[first_question.start():]
        preface = matching[:first_paragraph.start()].strip()
        if preface.startswith('Directions:'):
            title = preface.splitlines()[-1].strip()
        else:
            _require('Long Reading Matching' in headings[1].group(), '长篇阅读说明缺失')
            title = re.split(r'原文段落', preface)[0].strip()
        _require(title and 'Answer Sheet' not in title, '长篇阅读标题缺失')
        boundary = re.search(r'^\s*[📖]?\s*长篇阅读匹配题[：:]', question_region, re.M)
        if boundary:
            question_region = question_region[:boundary.start()]
    paragraph_markers = list(re.finditer(r'^\s*([A-Z])\)\s*', article, re.M))
    labels = [m.group(1) for m in paragraph_markers]
    _require(10 <= len(labels) <= 26 and labels == list(ALPHABET[:len(labels)]), '长篇阅读段落序列缺失、重复或次序错误')
    for i, marker in enumerate(paragraph_markers):
        end = paragraph_markers[i + 1].start() if i + 1 < len(labels) else len(article)
        _require(article[marker.end():end].strip(), f'长篇阅读 {marker.group(1)} 段没有原文')
    paragraph_options = [{'id': label, 'text': f'段落 {label}'} for label in labels]
    matching_section = {'id': 'reading-matching', 'kind': 'reading', 'title': '长篇阅读匹配（36—45）',
                        'passage': title + '\n\n' + article,
                        'questions': [_question(n, _flat(prompt), paragraph_options, answers) for n, prompt in numbered_blocks(question_region.strip(), 36, 45, '长篇阅读')]}

    careful = blocks[2]
    headers = list(re.finditer(r'^\s*Passage\s+(One|Two)\s*$', careful, re.M))
    _require([h.group(1) for h in headers] == ['One', 'Two'], '仔细阅读须有两篇文章')
    articles, questions = [], []
    for i, header in enumerate(headers):
        first, last = (46, 50) if i == 0 else (51, 55)
        chunk = careful[header.end():headers[i + 1].start() if i == 0 else len(careful)].strip()
        hint = re.match(r'Questions\s+(\d+)\s+to\s+(\d+)\s+are\s+based\s+on\s+the\s+following\s*passage[.]?\s*', chunk)
        if hint:
            _require((int(hint[1]), int(hint[2])) == (first, last), '文章题号范围错误')
            chunk = chunk[hint.end():].strip()
        question_start = _one(rf'(?<!\d){first}[.．]\s*(?![A-D][).])(?=[A-Za-z“"\'])', chunk, f'仔细阅读第{first}题')
        article = chunk[:question_start.start()].strip()
        _require(article and not re.search(r'^\s*[A-D]\)', article, re.M), '仔细阅读文章缺失或混入选项')
        articles.append(f'Passage {header.group(1)}（{first}—{last}）\n\n{article}')
        for number, body in numbered_blocks(chunk[question_start.start():], first, last, '仔细阅读'):
            option_start = _one(r'(?<![A-Za-z0-9])A\)', body, f'第{number}题选项')
            stem = _flat(body[:option_start.start()])
            _require(stem, f'第{number}题题干缺失')
            choices = _options(body[option_start.start():], 'ABCD', f'第{number}题')
            questions.append(_question(number, f'Passage {header.group(1)} · 第 {number} 题\n{stem}', choices, answers))
    return [cloze_section, matching_section, {'id': 'reading-careful', 'kind': 'reading', 'title': '仔细阅读（46—55）',
                                             'passage': '\n\n'.join(articles), 'questions': questions}]


def build_cet6_pack(text, answer_text, *, year, month, paper_number, source_url, answer_url,
                    source_title='六级原卷及对应来源答案'):
    _require(year in (2023, 2024, 2025) and month in ('06', '12') and paper_number in (1, 2, 3), '考次或套号不支持')
    answers = parse_cet6_answers(answer_text)
    sections = parse_cet6_reading(text, answers)
    for section in sections:
        for question in section['questions']:
            question['explanation'] = '答案依据对应来源答案表。'
    exam = {'id': f'community-cet6-{year}-{month}-{paper_number}-reading',
            'title': f'{year}年{int(month)}月 六级 第{paper_number}套 · 阅读',
            'level': 'CET6', 'year': year, 'session': f'{year}.{month} 第{paper_number}套', 'source_kind': 'past_paper',
            'source': {'title': source_title, 'url': source_url, 'verified': False,
                       'rights': '真题与相关解析权利归原权利人。仅供本地学习转换，第三方内容不随项目 MIT 代码授权。答案来源：' + answer_url},
            'sections': sections}
    pack = {'schema_version': 1, 'exams': [exam]}
    validate_pack(pack)
    return pack


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=ROOT / 'data/source-materials')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/imports/cet6-reading-2023-2025.json')
    parser.add_argument('--answers-checked', type=Path, default=ROOT / 'web/cet6-reading-answer-index.json')
    parser.add_argument('--corrections', type=Path, default=ROOT / 'web/cet6-reading-correction-index.json')
    args = parser.parse_args(argv)
    records = indexed_source_records()
    checked = json.loads(args.answers_checked.read_text(encoding='utf-8')) if args.answers_checked.exists() else {'papers': {}}
    corrections = json.loads(args.corrections.read_text(encoding='utf-8')) if args.corrections.exists() else {}
    exams, successes, failures = [], [], []
    for year in (2023, 2024, 2025):
        for month in ('06', '12'):
            for number in (1, 2, 3):
                base = f'cet6_{year}_{month}_{number}'
                candidates = [args.source_dir / f'{base}.{extension}' for extension in ('docx', 'pdf')]
                if year == 2023:
                    candidates.insert(0, args.source_dir / f'wamich_{year}_{month}_{number}.md')
                candidates.insert(0, args.source_dir / f'loveitsuka_{year}_{month}_{number}.pdf')
                paper = next((path for path in candidates if path.exists()), candidates[-1])
                answer = args.source_dir / f'{base}_ans.pdf'
                try:
                    source_record = records[paper.name]
                    paper_bytes = paper.read_bytes()
                    blob_sha = hashlib.sha1(b'blob ' + str(len(paper_bytes)).encode() + b'\0' + paper_bytes).hexdigest()
                    _require(blob_sha == source_record['blob_sha'], '原题文件与公开下载索引指纹不匹配')
                    text = apply_document_corrections(extract_document(paper), paper.name, corrections, paper)
                    key = f'{year}.{month}.{number}'
                    answer_check = checked['papers'].get(key)
                    if paper.name.startswith('loveitsuka_') and re.search(r'^\s*KEYS\s*$', text, re.M):
                        answer = paper
                        answer_record = source_record
                        answer_text = text
                        answer_check = None
                    elif answer_check:
                        answer_text = checked_answer_text(answer_check, paper, answer)
                        answer_record = {'url': answer_check['source_url']}
                    else:
                        answer_record = records[answer.name]
                        answer_bytes = answer.read_bytes()
                        answer_blob_sha = hashlib.sha1(b'blob ' + str(len(answer_bytes)).encode() + b'\0' + answer_bytes).hexdigest()
                        _require(answer_blob_sha == answer_record['blob_sha'], '答案文件与公开下载索引指纹不匹配')
                        answer_text = extract_document(answer)
                    # Diagnostic text is local source material, never a release file.
                    paper.with_suffix(paper.suffix + '.txt').write_text(text, encoding='utf-8')
                    if answer != paper and answer.exists():
                        answer.with_suffix(answer.suffix + '.txt').write_text(answer_text, encoding='utf-8')
                    pack = build_cet6_pack(text, answer_text, year=year, month=month, paper_number=number,
                                           source_url=source_record['url'], answer_url=answer_record['url'],
                                           source_title=source_record.get('repository', '0609x/CET46-Resources') + ' 原文及对应来源答案')
                    exams.extend(validate_pack(pack))
                    answer_is_web = answer_check and answer_check.get('source_kind') == 'web_answer_table'
                    successes.append({'paper': paper.name, 'answers': answer_check['source_url'] if answer_is_web else answer.name, 'questions': 30,
                                      'answer_evidence': answer_check.get('evidence') if answer_check else 'source-text',
                                      'corrections': corrections.get('corrections', {}).get(paper.name, []),
                                      'paper_sha256': hashlib.sha256(paper.read_bytes()).hexdigest(),
                                      'answer_sha256': None if answer_is_web else hashlib.sha256(answer.read_bytes()).hexdigest(),
                                      'answer_source_kind': 'web_answer_table' if answer_is_web else 'pdf'})
                except Exception as error:
                    failures.append({'paper': paper.name, 'answers': answer.name, 'error': str(error)})
    if exams:
        validate_pack({'schema_version': 1, 'exams': exams})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'schema_version': 1, 'exams': exams}, ensure_ascii=False, indent=2), encoding='utf-8')
    report = {'papers': len(exams), 'questions': len(exams) * 30, 'verified': False, 'successes': successes, 'failures': failures}
    args.output.with_name('cet6-reading-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'papers': report['papers'], 'questions': report['questions'],
                      'verified': False, 'failures': failures, 'output': str(args.output)}, ensure_ascii=False))
    return 0 if len(exams) == 18 else 2


if __name__ == '__main__':
    raise SystemExit(main())
