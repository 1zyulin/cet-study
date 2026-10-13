"""Build local CET wordbooks from the MIT-licensed ECDICT dictionary.

Run with --download to retrieve the pinned upstream CSV (about 66 MB). This tool
only creates import files; it does not modify the study database. The CET6 book
includes CET4 foundations and CET6-tagged additional words, and its exact
membership is documented in the report. It is not a commercial publisher's book.
"""
import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.content import ContentError
from app.store import validate_word

SOURCE_COMMIT = 'bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b'
SOURCE_BLOB = 'c4ade63ea08cf39d9c3475e96929036d64d94c94'
SOURCE_BYTES = 65_933_428
SOURCE_URL = f'https://raw.githubusercontent.com/skywind3000/ECDICT/{SOURCE_COMMIT}/ecdict.csv'
SOURCE_PAGE = f'https://github.com/skywind3000/ECDICT/blob/{SOURCE_COMMIT}/ecdict.csv'
LICENSE_URL = f'https://github.com/skywind3000/ECDICT/blob/{SOURCE_COMMIT}/LICENSE'
MAX_SOURCE_BYTES = 80 * 1024 * 1024
# Retain the license accompanying the pinned upstream data with local exports.
LICENSE_TEXT = '''MIT License

Copyright (c) 2025 Linwei

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''


def fingerprints(path):
    size = path.stat().st_size
    if size > MAX_SOURCE_BYTES:
        raise ValueError('ECDICT CSV exceeds 80 MB')
    sha256 = hashlib.sha256()
    blob = hashlib.sha1(b'blob ' + str(size).encode('ascii') + b'\0')
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            sha256.update(chunk)
            blob.update(chunk)
    return {'bytes': size, 'sha256': sha256.hexdigest(), 'git_blob_sha': blob.hexdigest()}


def download_source(target):
    import requests
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + '.partial')
    try:
        with requests.get(SOURCE_URL, timeout=(15, 60), stream=True) as response:
            response.raise_for_status()
            if urlparse(response.url).hostname != 'raw.githubusercontent.com':
                raise ValueError('Unsupported download redirect')
            size = 0
            with temporary.open('wb') as stream:
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_SOURCE_BYTES:
                        raise ValueError('ECDICT download exceeds 80 MB')
                    stream.write(chunk)
        hashes = fingerprints(temporary)
        if hashes['bytes'] != SOURCE_BYTES or hashes['git_blob_sha'] != SOURCE_BLOB:
            raise ValueError('ECDICT source is incomplete or changed; import aborted')
        temporary.replace(target)
        return hashes
    finally:
        temporary.unlink(missing_ok=True)


def clean_field(value):
    return (value or '').replace('\\n', '\n').strip()


def convert_rows(rows):
    """Retain source fields; report rejected entries rather than repairing words."""
    books = {'cet4': {}, 'cet6': {}}
    skipped, totals = [], {'rows': 0, 'cet4_tagged': 0, 'cet6_tagged': 0}
    for row_number, row in enumerate(rows, 2):
        totals['rows'] += 1
        tags = set((row.get('tag') or '').lower().split())
        if not tags.intersection({'cet4', 'cet6'}):
            continue
        for tag in ('cet4', 'cet6'):
            totals[tag + '_tagged'] += int(tag in tags)
        try:
            word = validate_word({'word': row.get('word'),
                                  'meaning': clean_field(row.get('translation')),
                                  'phonetic': clean_field(row.get('phonetic')),
                                  'example': ''})
            if not word['meaning']:
                raise ContentError('Source entry has no Chinese translation')
        except ContentError as error:
            skipped.append({'row': row_number, 'word': row.get('word', ''),
                            'tags': sorted(tags), 'reason': str(error)})
            continue
        memberships = ['cet6']
        if 'cet4' in tags:
            memberships.append('cet4')
        for book in memberships:
            if word['word'] in books[book]:
                skipped.append({'row': row_number, 'word': word['word'], 'book': book,
                                'reason': 'Duplicate normalized word; first source entry retained'})
                continue
            books[book][word['word']] = word
    result = {book: [words[word] for word in sorted(words)] for book, words in books.items()}
    for book, words in result.items():
        if not 1 <= len(words) <= 30000:
            raise ValueError(f'{book}: expected 1 to 30000 entries')
    return result, {'source_counts': totals, 'skipped': skipped,
                   'skipped_records': len(skipped),
                   'examples': 'Upstream detail examples are not populated; no example text invented'}


def convert_csv(path):
    with path.open('r', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'word', 'translation', 'phonetic', 'tag'}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError('ECDICT CSV headers must contain word, translation, phonetic, tag')
        return convert_rows(reader)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--csv', type=Path, default=ROOT / 'data/source-materials/ecdict.csv')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data/imports')
    args = parser.parse_args()
    if args.download:
        download_source(args.csv)
    hashes = fingerprints(args.csv)
    if hashes['bytes'] != SOURCE_BYTES or hashes['git_blob_sha'] != SOURCE_BLOB:
        raise ValueError('CSV does not match the pinned ECDICT source; import aborted')
    books, report = convert_csv(args.csv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'ECDICT-LICENSE.txt').write_text(LICENSE_TEXT, encoding='utf-8')
    names = {'cet4': 'ECDICT 四级词表（CET4）', 'cet6': 'ECDICT 六级词表（CET6）'}
    report.update({'created_at': datetime.now(timezone.utc).isoformat(),
                   'source_url': SOURCE_PAGE, 'download_url': SOURCE_URL,
                   'source_commit': SOURCE_COMMIT, 'license': 'MIT', 'license_url': LICENSE_URL,
                   'license_file': 'ECDICT-LICENSE.txt',
                   'source_fingerprint': hashes,
                   'membership_rule': {'cet4': 'tag contains cet4', 'cet6': 'tag contains cet4 or cet6'},
                   'books': []})
    for key, words in books.items():
        target = args.output_dir / f'{key}-words.json'
        target.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding='utf-8')
        report['books'].append({'key': key, 'title': names[key], 'file': target.name,
                                'count': len(words), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                                'missing_phonetic': sum(not word['phonetic'] for word in words),
                                'missing_example': len(words)})
    report_path = args.output_dir / 'wordbook-import-report.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'books': report['books'], 'skipped_records': report['skipped_records'],
                      'source_fingerprint': hashes, 'report': str(report_path)}, ensure_ascii=True))


if __name__ == '__main__':
    main()
