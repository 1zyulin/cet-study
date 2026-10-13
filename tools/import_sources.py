"""Convert supported community sources to local, explicitly unverified packs.

No third-party JavaScript is executed. Downloaded text, packs and reports remain
under ignored data/. This tool does not grant permission to republish material.
"""
import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.content import ContentError, validate_pack
from app.store import Store


class LiteralReader:
    """A small parser for JSON-like JS literals, never expressions or code."""
    def __init__(self, source, start=0):
        self.source, self.pos = source, start

    def whitespace(self):
        while self.pos < len(self.source):
            if self.source[self.pos].isspace():
                self.pos += 1
            elif self.source.startswith('//', self.pos):
                end = self.source.find('\n', self.pos)
                self.pos = len(self.source) if end < 0 else end + 1
            elif self.source.startswith('/*', self.pos):
                end = self.source.find('*/', self.pos + 2)
                if end < 0:
                    raise ContentError('Unterminated source comment')
                self.pos = end + 2
            else:
                break

    def consume(self, char):
        self.whitespace()
        if self.source[self.pos:self.pos + 1] != char:
            raise ContentError(f'Expected {char!r} at source offset {self.pos}')
        self.pos += 1

    def string(self):
        quote = self.source[self.pos]
        self.pos += 1
        chars = []
        escapes = {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f',
                   '/': '/', '\\': '\\', "'": "'", '"': '"'}
        while self.pos < len(self.source):
            c = self.source[self.pos]
            self.pos += 1
            if c == quote:
                return ''.join(chars)
            if c in '\r\n':
                raise ContentError('Unescaped line break in source string')
            if c != '\\':
                chars.append(c)
                continue
            if self.pos >= len(self.source):
                break
            c = self.source[self.pos]
            self.pos += 1
            if c in escapes:
                chars.append(escapes[c])
            elif c in ('u', 'x'):
                width = 4 if c == 'u' else 2
                digits = self.source[self.pos:self.pos + width]
                if not re.fullmatch('[0-9a-fA-F]{' + str(width) + '}', digits):
                    raise ContentError('Invalid escaped source character')
                chars.append(chr(int(digits, 16)))
                self.pos += width
            elif c in '\r\n':
                if c == '\r' and self.source[self.pos:self.pos + 1] == '\n':
                    self.pos += 1
            else:
                raise ContentError('Unsupported source string escape')
        raise ContentError('Unterminated source string')

    def value(self, depth=0):
        if depth > 32:
            raise ContentError('Source nesting limit exceeded')
        self.whitespace()
        c = self.source[self.pos:self.pos + 1]
        if not c:
            raise ContentError('Unexpected end of source')
        if c in ('"', "'"):
            return self.string()
        if c in ('[', '{'):
            is_object = c == '{'
            result = {} if is_object else []
            close = '}' if is_object else ']'
            self.pos += 1
            self.whitespace()
            while self.source[self.pos:self.pos + 1] != close:
                if is_object:
                    self.whitespace()
                    if self.source[self.pos:self.pos + 1] in ('"', "'"):
                        key = self.string()
                    else:
                        m = re.match(r'[A-Za-z_$][\w$]*', self.source[self.pos:])
                        if not m:
                            raise ContentError('Invalid literal object key')
                        key = m[0]
                        self.pos += len(key)
                    if key in result:
                        raise ContentError('Duplicate literal object key')
                    self.consume(':')
                    result[key] = self.value(depth + 1)
                else:
                    result.append(self.value(depth + 1))
                self.whitespace()
                if self.source[self.pos:self.pos + 1] == close:
                    break
                self.consume(',')
                self.whitespace()
            self.consume(close)
            return result
        m = re.match(r'-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?\b', self.source[self.pos:])
        if m:
            self.pos += len(m[0])
            number = float(m[0]) if any(x in m[0] for x in '.eE') else int(m[0])
            if not math.isfinite(number):
                raise ContentError('Non-finite literal number')
            return number
        for word, value in [('true', True), ('false', False), ('null', None)]:
            if re.match(word + r'\b', self.source[self.pos:]):
                self.pos += len(word)
                return value
        raise ContentError(f'Only literal data allowed at source offset {self.pos}')


def read_literal(source, name):
    if len(source.encode('utf-8')) > 8 * 1024 * 1024:
        raise ContentError('Source text too large')
    match = re.search(r'\b(?:const|let|var)\s+' + re.escape(name) + r'\s*=\s*', source)
    if not match:
        raise ContentError(f'Missing source array {name}')
    reader = LiteralReader(source, match.end())
    result = reader.value()
    reader.whitespace()
    if source[reader.pos:reader.pos + 1] not in (';', ''):
        raise ContentError('Expressions after source literal are not allowed')
    if not isinstance(result, list):
        raise ContentError('Source array required')
    return result


def source_info(title, url):
    return {'title': title + ' · 社区整理，待对照原卷校对', 'url': url,
            'rights': '第三方考试资料，仅导入本地学习；软件 MIT 许可不覆盖原题。参考答案为来源整理，非已核验官方答案。',
            'verified': False}


def subject_section(kind, prompt, reference=''):
    return {'id': kind, 'title': '写作' if kind == 'writing' else '翻译',
            'kind': kind, 'questions': [{'id': kind, 'type': kind, 'prompt': prompt,
            'reference': ('来源参考文本（非已核验官方答案）：\n' + reference) if reference else ''}]}


def cet6_subjective(writing, translation, years):
    groups = {}
    for kind, records in [('writing', read_literal(writing, 'WRITING_EXAMS')),
                          ('translation', read_literal(translation, 'TRANSLATION_DATA'))]:
        for item in records:
            if item['year'] not in years:
                continue
            month = int(re.fullmatch(r'(\d+)月', item['period'])[1])
            number = {'第一套': 1, '第二套': 2, '第三套': 3}[item['set']]
            key = item['year'], month, number
            group = groups.setdefault(key, {})
            if kind in group:
                raise ContentError('Duplicate source year/month/set')
            prompt = item['prompt'] if kind == 'writing' else '请将以下中文译成英文：\n' + item['original']
            group[kind] = subject_section(kind, prompt, item.get('reference', ''))
    exams = []
    for (year, month, number), sections in sorted(groups.items()):
        if set(sections) != {'writing', 'translation'}:
            raise ContentError('Writing/translation source coverage mismatch')
        exams.append({'id': f'community-cet6-{year}-{month:02d}-{number}-wt',
            'title': f'{year}年{month}月 六级 第{number}套 · 写作与翻译',
            'level': 'CET6', 'year': year, 'session': f'{month}月 第{number}套',
            'source_kind': 'past_paper',
            'source': source_info('Drhm1224/cet6-all-in-one', 'https://github.com/Drhm1224/cet6-all-in-one/tree/main/data'),
            'sections': [sections['writing'], sections['translation']]})
    return exams


def quoted_block(block, label):
    marker = re.search(r'^\*\*' + label + r'\*\*[^\n]*\n', block, re.M)
    if not marker:
        raise ContentError(f'Missing Markdown field {label}')
    rest = block[marker.end():]
    rest = re.split(r'^\*\*|^#{1,6} ', rest, maxsplit=1, flags=re.M)[0]
    lines = [re.sub(r'^>\s?', '', line) for line in rest.splitlines() if line.startswith('>')]
    value = '\n'.join(lines).strip()
    if not value:
        raise ContentError(f'Empty Markdown field {label}')
    return value


def cet4_subjective(markdown, years):
    headers = list(re.finditer(r'^### (\d{4})\.(\d{1,2})月[^\n]*$', markdown, re.M))
    exams = []
    for index, header in enumerate(headers):
        year, month = int(header[1]), int(header[2])
        if year not in years:
            continue
        end = headers[index + 1].start() if index + 1 < len(headers) else len(markdown)
        session = markdown[header.end():end]
        sets = list(re.finditer(r'^#### 第([1-3])套[^\n]*$', session, re.M))
        if len(sets) != 3:
            raise ContentError(f'Expected three CET4 sets for {year}-{month}')
        for i, match in enumerate(sets):
            number = int(match[1])
            block = session[match.end():sets[i + 1].start() if i + 1 < len(sets) else len(session)]
            writing, translation = quoted_block(block, '写作'), quoted_block(block, '翻译')
            if '120' not in writing or '180' not in writing:
                raise ContentError('CET4 writing word-count instructions missing')
            exams.append({'id': f'community-cet4-{year}-{month:02d}-{number}-wt',
                'title': f'{year}年{month}月 四级 第{number}套 · 写作与翻译',
                'level': 'CET4', 'year': year, 'session': f'{month}月 第{number}套',
                'source_kind': 'past_paper',
                'source': source_info('zzz-sc-tech/cet6-writing-translation · CC BY-NC-SA 4.0',
                    'https://github.com/zzz-sc-tech/cet6-writing-translation'),
                'sections': [subject_section('writing', writing), subject_section('translation',
                    '请将以下中文译成英文：\n' + translation, quoted_block(block, '★ 满分参考译文'))]})
    if not exams:
        raise ContentError('No supported CET4 Markdown exam sections found')
    return exams


SOURCE_URLS = {
    'cet4-writing-translation.md': 'https://raw.githubusercontent.com/zzz-sc-tech/cet6-writing-translation/main/references/真题库-四级-2015-2026.md',
    'cet6-writing.js': 'https://raw.githubusercontent.com/Drhm1224/cet6-all-in-one/main/data/writing.js',
    'cet6-translation.js': 'https://raw.githubusercontent.com/Drhm1224/cet6-all-in-one/main/data/translation.js',
}


def download_sources(directory):
    import requests
    directory.mkdir(parents=True, exist_ok=True)
    for filename, url in SOURCE_URLS.items():
        with requests.get(url, timeout=30, stream=True) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 4 * 1024 * 1024:
                    raise ContentError('Downloaded source exceeds 4MB limit')
                chunks.append(chunk)
            (directory / filename).write_text(b''.join(chunks).decode('utf-8-sig'), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Download supported text sources for local study')
    parser.add_argument('--import-local', action='store_true', help='Merge validated packs into local database')
    parser.add_argument('--source-dir', type=Path, default=ROOT / 'data/source-materials')
    parser.add_argument('--years', type=int, nargs='+', default=[2023, 2024, 2025])
    args = parser.parse_args()
    if args.download:
        download_sources(args.source_dir)
    texts = {name: (args.source_dir / name).read_text(encoding='utf-8-sig') for name in SOURCE_URLS}
    exams = cet4_subjective(texts['cet4-writing-translation.md'], args.years)
    exams += cet6_subjective(texts['cet6-writing.js'], texts['cet6-translation.js'], args.years)
    validated = validate_pack({'schema_version': 1, 'exams': exams})
    output = ROOT / 'data/imports'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'community-subjective-2023-2025.json').write_text(json.dumps(
        {'schema_version': 1, 'exams': validated}, ensure_ascii=False, indent=2), encoding='utf-8')
    report = {'years': args.years, 'exams': len(validated),
              'questions': sum(len(s['questions']) for e in validated for s in e['sections']),
              'verified': False, 'source_sha256': {name: hashlib.sha256(value.encode('utf-8')).hexdigest() for name, value in texts.items()},
              'notes': 'Writing and translation only. References are community text, not verified official answers. Raw data excluded from Git.'}
    (output / 'import-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.import_local:
        store = Store(ROOT / 'data/study.sqlite3')
        (output / 'before-source-import-backup.json').write_text(json.dumps(store.backup(), ensure_ascii=False), encoding='utf-8')
        store.import_exams(validated)
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    main()
