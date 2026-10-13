"""Download indexed CET6 papers and answers for local study, never public data."""
import concurrent.futures
import hashlib
import json
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'https://github.com/0609x/CET46-Resources/blob/main/'


def fetch(record):
    match = re.search(r'/((?:2023|2024|2025)[.]\d{2})/', record['path'])
    number = re.search(r'第([123])套|_([123])(?:_ans)?[.]', record['path'])
    if not match or not number or not record['url'].startswith(PREFIX):
        raise ValueError('Unsupported indexed source')
    session, paper = match[1], number[1] or number[2]
    suffix = '.docx' if record['kind'] == 'paper_word' else '.pdf'
    name = 'cet6_' + session.replace('.', '_') + '_' + paper
    if record['kind'] == 'answer':
        name += '_ans'
    target = ROOT / 'data/source-materials' / (name + suffix)
    size = int(record['bytes'])
    if not 0 < size <= 64 * 1024 * 1024:
        raise ValueError('Indexed source exceeds 64MB')
    if target.exists():
        data = target.read_bytes()
        sha = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if sha == record['blob_sha'] and len(data) == size:
            return dict(record, local_file=target.name, cached=True)
    raw = 'https://raw.githubusercontent.com/0609x/CET46-Resources/main/' + record['url'][len(PREFIX):]
    partial = target.with_suffix(target.suffix + '.download')
    hasher = hashlib.sha1(b'blob ' + str(size).encode() + b'\0')
    count, header = 0, b''
    try:
        with requests.get(raw, stream=True, timeout=(15, 60)) as response:
            response.raise_for_status()
            with partial.open('wb') as output:
                for chunk in response.iter_content(65536):
                    if not chunk:
                        continue
                    if not header:
                        header = chunk[:8]
                    count += len(chunk)
                    if count > size:
                        raise ValueError('Source larger than indexed size')
                    hasher.update(chunk)
                    output.write(chunk)
        signature = b'PK' if suffix == '.docx' else b'%PDF-'
        if count != size or hasher.hexdigest() != record['blob_sha'] or not header.startswith(signature):
            raise ValueError('Downloaded source failed size/hash/header validation')
        partial.replace(target)
    finally:
        if partial.exists():
            partial.unlink()
    return dict(record, local_file=target.name, cached=False)


def main():
    records = json.loads((ROOT / 'web/source-index.json').read_text(encoding='utf-8'))['files']
    records = [r for r in records if r['level'] == 'CET6' and r['kind'] in ('paper_pdf', 'paper_word', 'answer')]
    records.sort(key=lambda r: (r['path'], r['kind'] == 'answer'), reverse=True)
    (ROOT / 'data/source-materials').mkdir(parents=True, exist_ok=True)
    results, errors = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch, record): record for record in records}
        for future in concurrent.futures.as_completed(futures):
            record = futures[future]
            try:
                result = future.result()
                results.append(result)
                print(json.dumps({'saved': result['local_file'], 'bytes': result['bytes'], 'cached': result['cached']}), flush=True)
            except Exception as error:
                errors.append({'path': record['path'], 'error': str(error)})
                print(json.dumps(errors[-1], ensure_ascii=True), flush=True)
    output = ROOT / 'data/imports'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'cet6-source-receipt.json').write_text(json.dumps({'files': results, 'failures': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'files': len(results), 'failures': len(errors)}), flush=True)
    return 2 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
