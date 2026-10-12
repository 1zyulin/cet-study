"""Prepare the twelve supported CET4 reading papers locally.

Use --download to obtain the PDF sources; source hashes must match the checked
index. --import-local merges successful papers after creating a recovery backup.
Network retrieval is optional; this command also works with existing local PDFs.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.content import validate_pack
from app.store import Store
from tools.import_reading import build_pack, read_pdf_text


def download_pdf(record, target):
    import requests
    prefix = 'https://github.com/0609x/CET46-Resources/blob/main/'
    if not record['url'].startswith(prefix):
        raise ValueError('Unsupported PDF source URL')
    url = 'https://raw.githubusercontent.com/0609x/CET46-Resources/main/' + record['url'][len(prefix):]
    with requests.get(url, timeout=30, stream=True) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 4 * 1024 * 1024:
                raise ValueError('PDF download exceeds 4MB')
            chunks.append(chunk)
    data = b''.join(chunks)
    digest = hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()
    if digest != record['blob_sha'] or len(data) != record['bytes'] or not data.startswith(b'%PDF-'):
        raise ValueError('Source PDF changed or download incomplete; review the index before importing')
    target.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--import-local', action='store_true')
    args = parser.parse_args()
    index = json.loads((ROOT / 'web/source-index.json').read_text(encoding='utf-8'))
    source_dir = ROOT / 'data/source-materials'
    source_dir.mkdir(parents=True, exist_ok=True)
    exams, failures = [], []
    for record in index['files']:
        name = record['path'].split('/')[-1]
        match = re.fullmatch(r'cet4_(2024|2025)_(06|12)_([1-3])\.pdf', name)
        if record['kind'] != 'paper_pdf' or record['level'] != 'CET4' or not match:
            continue
        path = source_dir / name
        try:
            if args.download:
                download_pdf(record, path)
            pack = build_pack(read_pdf_text(path), level='CET4', year=int(match[1]),
                              session=match[1] + '.' + match[2], paper_number=int(match[3]),
                              source_url=record['url'])
            exams.extend(validate_pack(pack))
        except Exception as error:
            failures.append({'file': name, 'error': str(error)})
    if exams:
        exams = validate_pack({'schema_version': 1, 'exams': exams})
    output = ROOT / 'data/imports'
    output.mkdir(parents=True, exist_ok=True)
    report = {'papers': len(exams), 'questions': sum(len(s['questions']) for e in exams for s in e['sections']),
              'verified': False, 'failures': failures, 'download_requested': args.download}
    (output / 'reading-recent-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if exams:
        (output / 'reading-recent-cet4.json').write_text(json.dumps({'schema_version': 1, 'exams': exams}, ensure_ascii=False, indent=2), encoding='utf-8')
        if args.import_local:
            store = Store(ROOT / 'data/study.sqlite3')
            recovery = ROOT / 'data/recovery'
            recovery.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            (recovery / f'reading-batch-{stamp}.json').write_text(json.dumps(store.backup(), ensure_ascii=False), encoding='utf-8')
            store.import_exams(exams)
    print(json.dumps(report, ensure_ascii=True))
    return 2 if failures or len(exams) != 12 else 0


if __name__ == '__main__':
    raise SystemExit(main())
