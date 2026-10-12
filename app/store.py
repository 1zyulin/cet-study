"""Local SQLite persistence and vocabulary import."""
import csv
import io
import json
import math
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from .content import ContentError, text


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


class Store:
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS exams(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, exam_id TEXT NOT NULL, created_at TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS words(id TEXT PRIMARY KEY, word TEXT UNIQUE NOT NULL, data TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def exams(self):
        with self.connect() as db:
            return [json.loads(x['data']) for x in db.execute('SELECT data FROM exams ORDER BY id')]

    def exam(self, eid):
        with self.connect() as db:
            r = db.execute('SELECT data FROM exams WHERE id=?', (eid,)).fetchone()
            return json.loads(r['data']) if r else None

    def import_exams(self, exams):
        with self.connect() as db:
            for e in exams:
                db.execute('INSERT INTO exams VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (e['id'], dumps(e)))

    def save_attempt(self, exam, values, kind='exam'):
        attempt = dict(values, id=uuid.uuid4().hex, exam_id=exam['id'], exam_title=exam['title'], created_at=now(), kind=kind)
        with self.connect() as db:
            db.execute('INSERT INTO attempts VALUES (?,?,?,?)', (attempt['id'], exam['id'], attempt['created_at'], dumps(attempt)))
        return attempt

    def attempts(self, limit=None):
        with self.connect() as db:
            sql = 'SELECT data FROM attempts ORDER BY created_at DESC, rowid DESC'
            rows = db.execute(sql + (' LIMIT ?' if limit else ''), (limit,) if limit else ())
            return [json.loads(r['data']) for r in rows]

    def words(self):
        with self.connect() as db:
            return [json.loads(r['data']) for r in db.execute('SELECT data FROM words ORDER BY word')]

    def import_words(self, words, title):
        with self.connect() as db:
            for w in words:
                prev = db.execute('SELECT data FROM words WHERE word=?', (w['word'],)).fetchone()
                old = json.loads(prev['data']) if prev else {'id': uuid.uuid4().hex, 'reviews': 0, 'interval_days': 0, 'due_at': now()}
                record = dict(old, **w, book=title)
                db.execute('INSERT INTO words VALUES (?,?,?) ON CONFLICT(word) DO UPDATE SET data=excluded.data', (record['id'], record['word'], dumps(record)))

    def review(self, wid, rating):
        if rating not in ('again', 'good', 'easy'):
            raise ContentError('复习评级须为 again / good / easy')
        with self.connect() as db:
            row = db.execute('SELECT data FROM words WHERE id=?', (wid,)).fetchone()
            if not row:
                raise ContentError('单词不存在')
            w = json.loads(row['data'])
            days = 0 if rating == 'again' else (max(1, round(w['interval_days'] * 2)) if rating == 'good' else max(3, round(w['interval_days'] * 3)))
            delay = timedelta(minutes=10) if rating == 'again' else timedelta(days=min(days, 365))
            w.update(reviews=w['reviews'] + 1, interval_days=min(days, 365), due_at=(datetime.now(timezone.utc) + delay).isoformat(timespec='seconds'))
            db.execute('UPDATE words SET data=? WHERE id=?', (dumps(w), wid))
            return w

    def backup(self):
        return {'backup_version': 1, 'created_at': now(), 'exams': self.exams(), 'attempts': self.attempts(), 'words': self.words()}

    def restore(self, exams, attempts, words):
        # Validate everything before entering this atomic replacement transaction.
        with self.connect() as db:
            db.execute('DELETE FROM exams')
            db.execute('DELETE FROM attempts')
            db.execute('DELETE FROM words')
            db.executemany('INSERT INTO exams VALUES (?,?)', [(e['id'], dumps(e)) for e in exams])
            db.executemany('INSERT INTO attempts VALUES (?,?,?,?)', [(a['id'], a['exam_id'], a['created_at'], dumps(a)) for a in attempts])
            db.executemany('INSERT INTO words VALUES (?,?,?)', [(w['id'], w['word'], dumps(w)) for w in words])


def validate_word(raw):
    if not isinstance(raw, dict):
        raise ContentError('词条须为对象')
    word = text(raw.get('word'), '单词', 150, True).strip().lower()
    if not re.fullmatch(r"[a-z][a-z '’.-]*", word):
        raise ContentError('单词只允许英文词、短语及常用连字符')
    return {'word': word, 'meaning': text(raw.get('meaning', ''), '释义', 5000).strip(), 'phonetic': text(raw.get('phonetic', ''), '音标', 500), 'example': text(raw.get('example', ''), '例句', 10000)}


def parse_words(fmt, content):
    content = text(content, '词书内容', 5_000_000, True).lstrip('\ufeff')
    if fmt == 'json':
        try:
            raws = json.loads(content)
        except ValueError:
            raise ContentError('词书 JSON 无法解析')
        if not isinstance(raws, list):
            raise ContentError('JSON 词书须为词条数组')
    elif fmt == 'csv':
        try:
            reader = csv.DictReader(io.StringIO(content))
            if not reader.fieldnames or 'word' not in reader.fieldnames:
                raise ContentError('CSV 表头须包含 word，可包含 meaning、phonetic、example')
            raws = list(reader)
        except csv.Error:
            raise ContentError('CSV 格式无法解析')
    elif fmt == 'txt':
        raws = []
        for line in content.splitlines():
            if not line.strip():
                continue
            parts = re.split(r'\t|,', line.strip(), maxsplit=1)
            raws.append({'word': parts[0], 'meaning': parts[1] if len(parts) > 1 else ''})
    else:
        raise ContentError('支持 txt / csv / json 词书')
    if not 1 <= len(raws) <= 30000:
        raise ContentError('每次导入须有 1—30000 条词条')
    return list({w['word']: w for w in map(validate_word, raws)}.values())


def validate_backup(backup, exam_validator):
    if not isinstance(backup, dict) or backup.get('backup_version') != 1:
        raise ContentError('备份版本不支持')
    raw_exams = backup.get('exams', [])
    if not isinstance(raw_exams, list):
        raise ContentError('备份 exams 须为试卷数组')
    exams = exam_validator({'schema_version': 1, 'exams': raw_exams}) if raw_exams else []
    raw_attempts, raw_words = backup.get('attempts'), backup.get('words')
    if not isinstance(raw_attempts, list) or len(raw_attempts) > 100000 or not isinstance(raw_words, list) or len(raw_words) > 100000:
        raise ContentError('备份记录格式或数量错误')
    words, ids, known_words = [], set(), set()
    for r in raw_words:
        w = validate_word(r)
        wid = text(r.get('id'), '词条 ID', 120, True)
        if wid in ids or w['word'] in known_words:
            raise ContentError('备份词条重复')
        ids.add(wid)
        known_words.add(w['word'])
        reviews, interval = r.get('reviews'), r.get('interval_days')
        if type(reviews) is not int or reviews < 0 or type(interval) not in (float, int) or not math.isfinite(interval) or not 0 <= interval <= 365:
            raise ContentError('复习记录格式错误')
        date = text(r.get('due_at'), '复习日期', 100, True)
        try:
            if datetime.fromisoformat(date).tzinfo is None:
                raise ValueError
        except ValueError:
            raise ContentError('复习日期必须含时区')
        words.append(dict(w, id=wid, reviews=reviews, interval_days=interval, due_at=date, book=text(r.get('book', ''), '词书标题', 200)))
    attempts, ids = [], set()
    exam_ids = {e['id'] for e in exams}
    for a in raw_attempts:
        if not isinstance(a, dict):
            raise ContentError('备份练习须为对象')
        exam_id = text(a.get('exam_id'), '练习试卷 ID', 120, True)
        if exam_id not in exam_ids:
            raise ContentError('备份练习引用了未知试卷')
        aid = text(a.get('id'), '记录 ID', 120, True)
        if aid in ids or not isinstance(a.get('results'), list) or len(a['results']) > 3000:
            raise ContentError('练习记录重复或格式错误')
        ids.add(aid)
        text(a.get('created_at'), '记录日期', 100, True)
        text(a.get('exam_title'), '试卷名称', 500, True)
        if a.get('kind') not in ('exam', 'evaluation'):
            raise ContentError('练习记录类型错误')
        if type(a.get('correct')) is not int or type(a.get('total_objective')) is not int or not 0 <= a['correct'] <= a['total_objective']:
            raise ContentError('练习分数格式错误')
        # Validate nested feedback before any records are replaced.
        from .ai import ApiError, validate_evaluation
        for result in a['results']:
            if not isinstance(result, dict):
                raise ContentError('备份作答结果须为对象')
            text(result.get('question_id'), '作答题目 ID', 120, True)
            answer = text(result.get('answer'), '备份作答', 30000)
            if result.get('type') not in ('choice', 'writing', 'translation'):
                raise ContentError('备份题型错误')
            if 'is_correct' in result and type(result['is_correct']) is not bool:
                raise ContentError('备份选择题结果错误')
            for key in ('correct_answer', 'explanation'):
                if key in result:
                    text(result[key], '备份' + key, 30000)
            try:
                if 'evaluation' in result:
                    validate_evaluation(result['evaluation'], answer)
                if 'score' in result:
                    validate_evaluation(result, answer)
            except ApiError:
                raise ContentError('备份 AI 反馈格式错误')
        if 'evaluation' in a:
            try:
                validate_evaluation(a['evaluation'], '')
            except ApiError:
                raise ContentError('备份 AI 反馈格式错误')
        attempts.append(a)
    return exams, attempts, words
