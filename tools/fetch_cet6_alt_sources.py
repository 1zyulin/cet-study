"""Download fixed CET6 source files locally, checking their Git blob fingerprints.

The public index contains metadata only. Exam text and PDFs remain under ignored
data/source-materials; source availability does not grant redistribution rights.
No downloaded source code is executed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'web/cet6-alt-source-index.json'
SOURCES = {
    'andrew': 'AndrewYuZhenYu/cet6_exam_questions_txt_collection',
    'wamich': 'wamich/english-exem-md',
    'gatsby': 'Gatsby666-jay/CET6-2025-2026',
    'loveitsuka': 'LoveItsukaKotori/cet6-training-app',
}
LOVEITSUKA_REF = 'b3fb51a75607ab29e595be955816699d8a5ba0e4'
MAX_SIZE = 4 * 1024 * 1024


def git_blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def validate_item(item):
    repository = item.get('repository')
    expected_ref = LOVEITSUKA_REF if repository == SOURCES['loveitsuka'] else 'main'
    if repository not in SOURCES.values() or item.get('ref') != expected_ref:
        raise ValueError('Unsupported source repository or ref')
    path = item.get('path', '')
    if not path or '\\' in path or path.startswith('/') or any(part in ('', '.', '..') for part in path.split('/')):
        raise ValueError('Invalid source path')
    name = item.get('local_name', '')
    if not re.fullmatch(r'(?:andrew|wamich|gatsby|loveitsuka)_202[3-5]_(?:06|12)_[1-3](?:_ans)?\.(?:txt|md|pdf)', name):
        raise ValueError('Invalid local source name')
    size = item.get('size')
    if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= MAX_SIZE:
        raise ValueError('Invalid source byte size')
    if not re.fullmatch(r'[0-9a-f]{40}', item.get('blob_sha', '')):
        raise ValueError('Invalid source blob hash')
    url = 'https://raw.githubusercontent.com/' + repository + '/' + expected_ref + '/' + quote(path, safe='/')
    if item.get('download_url') != url:
        raise ValueError('Source URL does not match fixed GitHub path')
    return url


def checked_bytes(data, item):
    if len(data) != item['size'] or git_blob_sha(data) != item['blob_sha']:
        raise ValueError('Source size/hash mismatch; update metadata after inspecting upstream changes')
    if item['local_name'].endswith('.pdf'):
        if not data.startswith(b'%PDF-'):
            raise ValueError('Expected a PDF source')
    else:
        data.decode('utf-8-sig')
    return data


def fetch_one(item, destination):
    url = validate_item(item)
    target = destination / item['local_name']
    if target.exists():
        try:
            checked_bytes(target.read_bytes(), item)
            return {'file': target.name, 'status': 'cached', 'size': item['size']}
        except (ValueError, UnicodeError):
            pass
    with requests.get(url, timeout=(10, 35), stream=True, allow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError('Source download did not return HTTP 200')
        chunks, size = [], 0
        for chunk in response.iter_content(64 * 1024):
            size += len(chunk)
            if size > item['size'] or size > MAX_SIZE:
                raise ValueError('Source download exceeds expected byte size')
            chunks.append(chunk)
    data = checked_bytes(b''.join(chunks), item)
    temporary = target.with_suffix(target.suffix + '.part')
    temporary.write_bytes(data)
    temporary.replace(target)
    return {'file': target.name, 'status': 'downloaded', 'size': len(data)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=['all', *SOURCES], default='all')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    args = parser.parse_args(argv)
    index = json.loads(INDEX.read_text(encoding='utf-8'))
    files = [item for item in index['files'] if args.source == 'all' or item['repository'] == SOURCES[args.source]]
    destination = args.data_dir / 'source-materials'
    destination.mkdir(parents=True, exist_ok=True)
    results, failures = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_one, item, destination): item for item in files}
        for future in as_completed(futures):
            item = futures[future]
            try:
                result = future.result()
                results.append(result)
                print(result['status'] + ': ' + result['file'], flush=True)
            except Exception as exc:
                failures.append({'file': item['local_name'], 'error': str(exc)})
                print('failed: ' + item['local_name'] + ' (' + str(exc) + ')', flush=True)
    report = {'source': args.source, 'expected_files': len(files), 'files': sorted(results, key=lambda x: x['file']), 'failures': failures}
    report_dir = args.data_dir / 'imports'
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / ('cet6-alt-download-' + args.source + '.json')
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'downloaded_or_cached': len(results), 'failed': len(failures), 'report': str(report_path)}), flush=True)
    return 2 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
