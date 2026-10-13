"""Back up a local library, remove demo content, and simplify practice titles."""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.store import Store, dumps, now


def clean_library(store, recovery):
    recovery.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup_path = recovery / f'before-library-cleanup-{stamp}.json'
    counts = dict(removed_exams=0, removed_demo_attempts=0, removed_demo_words=0, renamed_exams=0)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        exams = [json.loads(r['data']) for r in db.execute('SELECT data FROM exams')]
        attempts = [json.loads(r['data']) for r in db.execute('SELECT data FROM attempts')]
        words = [json.loads(r['data']) for r in db.execute('SELECT data FROM words')]
        snapshot = dict(backup_version=1, created_at=now(), exams=exams, attempts=attempts, words=words)
        backup_path.write_text(dumps(snapshot), encoding='utf-8')
        demo_ids = {e['id'] for e in exams if e.get('source_kind') == 'demo'}
        for eid in demo_ids:
            counts['removed_demo_attempts'] += db.execute('DELETE FROM attempts WHERE exam_id=?', (eid,)).rowcount
            counts['removed_exams'] += db.execute('DELETE FROM exams WHERE id=?', (eid,)).rowcount
        for exam in exams:
            if exam['id'] in demo_ids:
                continue
            title = re.sub(r'\s*[（(]待校对[）)]', '', exam['title']).strip()
            if title != exam['title']:
                exam['title'] = title
                db.execute('UPDATE exams SET data=? WHERE id=?', (dumps(exam), exam['id']))
                counts['renamed_exams'] += 1
        for word in words:
            books = list(word.get('books', [word.get('book', '')]))
            if word.get('book') and word['book'] not in books:
                books.append(word['book'])
            books = [b for b in books if b and b != '自创演示词书']
            if not books and word.get('book') == '自创演示词书':
                counts['removed_demo_words'] += db.execute('DELETE FROM words WHERE id=?', (word['id'],)).rowcount
            elif books:
                word['books'] = books
                if word.get('book') not in books:
                    word['book'] = books[-1]
                db.execute('UPDATE words SET data=? WHERE id=?', (dumps(word), word['id']))
    return dict(counts, backup=str(backup_path))


if __name__ == '__main__':
    result = clean_library(Store(ROOT / 'data/study.sqlite3'), ROOT / 'data/recovery')
    print(json.dumps(result, ensure_ascii=True))
