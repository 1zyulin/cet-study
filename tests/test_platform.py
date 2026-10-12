"""Behavioral tests using isolated local data and mocked model services."""
import copy
import io
import json
import os
import tempfile
import unittest
import wave
from contextlib import redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from app import create_app
from app import ai
from app.store import Store
import run


def temporary_directory():
    # Keep isolated data inside the writable test tree, including on restricted
    # Windows hosts whose system temporary directory has different permissions.
    parent = Path(__file__).resolve().parent
    return tempfile.TemporaryDirectory(prefix='.test-', dir=parent)


def exam_pack(exam_id='test-cet4'):
    """Small original fixture; it deliberately contains no real exam material."""
    return {
        'schema_version': 1,
        'exams': [{
            'id': exam_id, 'title': 'Original integration practice',
            'level': 'CET4', 'year': 2025, 'session': 'demo',
            'source_kind': 'demo',
            'source': {'title': 'Test authors', 'rights': 'Original CC0 fixture',
                       'url': '', 'verified': True},
            'sections': [
                {'id': 'reading', 'kind': 'reading', 'title': 'Reading',
                 'passage': 'Mina reads a book each morning.', 'questions': [
                     {'id': 'q1', 'type': 'choice', 'prompt': 'When does Mina read?',
                      'options': [{'id': 'A', 'text': 'Morning'},
                                  {'id': 'B', 'text': 'Night'}],
                      'answer': 'A', 'explanation': 'The passage says each morning.'},
                     {'id': 'q2', 'type': 'choice', 'prompt': 'What does Mina read?',
                      'options': [{'id': 'A', 'text': 'A menu'},
                                  {'id': 'B', 'text': 'A book'}], 'answer': 'B'}]},
                {'id': 'writing', 'kind': 'writing', 'title': 'Writing',
                 'questions': [{'id': 'essay', 'type': 'writing',
                                'prompt': 'Describe a helpful study habit.'}]},
                {'id': 'translation', 'kind': 'translation', 'title': 'Translation',
                 'questions': [{'id': 'translation', 'type': 'translation',
                                'prompt': '每天阅读可以帮助我们学习。',
                                'reference': 'Reading every day helps us learn.'}]},
            ],
        }],
    }


def evaluation():
    return {
        'score': 11.5, 'band': 'Good', 'summary': 'Meaning is clear.',
        'dimensions': {'content': 'Relevant', 'structure': 'Coherent',
                       'vocabulary': 'Appropriate', 'grammar': 'Needs correction'},
        'corrections': [{'original': 'Reading help us.', 'revised': 'Reading helps us.',
                         'reason': 'Subject agreement'}],
        'suggestions': ['Check subject agreement.'],
        'revised_text': 'Reading helps us.',
    }


def model_response(content, status=200):
    response = Mock(status_code=status, content=b'{}')
    response.json.return_value = {'choices': [{'message': {'content': content}}]}
    return response


class PlatformTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'AI_BASE_URL': 'https://example.test/v1',
                                     'AI_MODEL': 'test-model', 'AI_API_KEY': ''})
        env.start()
        self.addCleanup(env.stop)
        loader = patch('app.ai.load_env')
        loader.start()
        self.addCleanup(loader.stop)
        self.app = create_app(data_dir=self.temp.name, seed=False)
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.token = {'X-Local-Token': self.app.config['LOCAL_TOKEN']}

    def post(self, url, body):
        return self.client.post(url, json=body, headers=self.token)

    def import_exam(self, pack=None):
        response = self.post('/api/import/exams', {'pack': pack or exam_pack()})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response

    def configure_ai(self):
        response = self.post('/api/settings', {'api_key': 'secret-test-key'})
        self.assertEqual(response.status_code, 200)


class ExamTests(PlatformTestCase):
    def test_import_is_atomic_for_invalid_second_exam(self):
        self.import_exam()
        for defect in ('duplicate', 'invalid_answer', 'empty_questions', 'duplicate_question'):
            with self.subTest(defect=defect):
                pack = exam_pack('new')
                other = copy.deepcopy(pack['exams'][0])
                other['id'] = 'other'
                if defect == 'duplicate':
                    other['id'] = 'new'
                elif defect == 'invalid_answer':
                    other['sections'][0]['questions'][0]['answer'] = 'Z'
                elif defect == 'empty_questions':
                    other['sections'][0]['questions'] = []
                else:
                    other['sections'][1]['questions'][0]['id'] = 'q1'
                pack['exams'].append(other)
                response = self.post('/api/import/exams', {'pack': pack})
                self.assertEqual(response.status_code, 400)
                self.assertEqual([e['id'] for e in self.app.extensions['store'].exams()],
                                 ['test-cet4'])

    def test_malformed_answer_types_are_rejected_without_server_error(self):
        for answer in ({'id': 'A'}, ['A'], None):
            with self.subTest(answer=answer):
                pack = exam_pack()
                pack['exams'][0]['sections'][0]['questions'][0]['answer'] = answer
                response = self.post('/api/import/exams', {'pack': pack})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.app.extensions['store'].exams(), [])

    def test_choices_grade_locally_subjective_answers_wait_for_ai(self):
        self.import_exam()
        visible = self.client.get('/api/exams/test-cet4').get_json()['exam']
        choice = visible['sections'][0]['questions'][0]
        self.assertNotIn('answer', choice)
        self.assertNotIn('explanation', choice)
        response = self.post('/api/exams/test-cet4/submit', {'answers': {
            'q1': 'A', 'q2': 'A', 'essay': 'Reading helps us.', 'translation': ''}})
        self.assertEqual(response.status_code, 200)
        attempt = response.get_json()['attempt']
        self.assertEqual((attempt['correct'], attempt['total_objective']), (1, 2))
        results = {r['question_id']: r for r in attempt['results']}
        self.assertTrue(results['q1']['is_correct'])
        self.assertFalse(results['q2']['is_correct'])
        self.assertEqual(results['q2']['correct_answer'], 'B')
        self.assertEqual(results['essay']['status'], 'pending_ai')
        self.assertEqual(results['translation']['status'], 'pending_ai')
        reopened = Store(Path(self.temp.name) / 'study.sqlite3')
        self.assertEqual(reopened.attempts()[0], attempt)
        self.assertEqual(len(reopened.exams()), 1)

    def test_invalid_submission_creates_no_record(self):
        self.import_exam()
        for answers in ({'unknown': 'A'}, {'q1': 'Z'}, {'q1': True}, []):
            with self.subTest(answers=answers):
                response = self.post('/api/exams/test-cet4/submit', {'answers': answers})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.app.extensions['store'].attempts(), [])

    def test_levels_can_be_filtered(self):
        pack = exam_pack()
        other = exam_pack('test-cet6')['exams'][0]
        other['level'] = 'CET6'
        pack['exams'].append(other)
        self.import_exam(pack)
        exams = self.client.get('/api/exams?level=CET6').get_json()['exams']
        self.assertEqual([e['id'] for e in exams], ['test-cet6'])

    def test_shipped_examples_seed_both_levels_and_can_be_scored(self):
        seeded = create_app(data_dir=Path(self.temp.name) / 'seeded', seed=True)
        seeded.config['TESTING'] = True
        client = seeded.test_client()
        token = {'X-Local-Token': seeded.config['LOCAL_TOKEN']}
        exams = client.get('/api/exams').get_json()['exams']
        self.assertEqual({exam['level'] for exam in exams}, {'CET4', 'CET6'})
        self.assertTrue(all(exam['source_kind'] == 'demo' for exam in exams))
        for exam in exams:
            with self.subTest(exam=exam['id']):
                result = client.post('/api/exams/' + exam['id'] + '/submit',
                                     json={'answers': {}}, headers=token)
                self.assertEqual(result.status_code, 200)
                self.assertGreater(result.get_json()['attempt']['total_objective'], 0)
        self.assertGreater(len(seeded.extensions['store'].words()), 0)

    def test_invalid_listening_timeline_rejects_entire_pack(self):
        timelines = [
            [{'start': -1, 'end': 2, 'text': 'Invalid start'}],
            [{'start': 5, 'end': 2, 'text': 'Invalid duration'}],
            [{'start': 10, 'end': 11, 'text': 'Later'},
             {'start': 1, 'end': 2, 'text': 'Earlier'}],
            [{'start': False, 'end': 1, 'text': 'Boolean is not a time'}],
        ]
        for timeline in timelines:
            with self.subTest(timeline=timeline):
                pack = exam_pack()
                section = pack['exams'][0]['sections'][0]
                section['kind'] = 'listening'
                section['segments'] = timeline
                self.assertEqual(self.post('/api/import/exams', {'pack': pack}).status_code, 400)
                self.assertEqual(self.app.extensions['store'].exams(), [])


class SecurityAndSettingsTests(PlatformTestCase):
    def test_mutations_require_local_token_and_matching_origin(self):
        body = {'pack': exam_pack()}
        for headers in ({}, {'X-Local-Token': 'wrong'}, {'X-Local-Token': '坏令牌'},
                        dict(self.token, Origin='https://evil.test')):
            with self.subTest(headers=headers):
                self.assertEqual(self.client.post('/api/import/exams', json=body,
                                                 headers=headers).status_code, 403)
        self.assertEqual(self.client.get('/api/health',
                                        base_url='http://evil.test').status_code, 403)
        self.assertEqual(self.client.get('/api/health', headers={
            'Origin': 'https://evil.test'}).status_code, 403)
        response = self.client.post('/api/import/exams', json=body,
                                    headers=dict(self.token, Origin='http://localhost'))
        self.assertEqual(response.status_code, 200)

    def test_key_is_private_blank_preserves_and_settings_persist(self):
        self.configure_ai()
        response = self.post('/api/settings', {'api_key': '', 'model': 'another-model'})
        self.assertEqual(response.status_code, 200)
        settings = self.client.get('/api/settings').get_json()
        self.assertEqual(settings, {'base_url': 'https://example.test/v1',
                                    'model': 'another-model', 'has_key': True})
        self.assertNotIn('secret-test-key', response.get_data(as_text=True))
        self.assertNotIn('secret-test-key', self.client.get('/api/backup').get_data(as_text=True))
        reopened = create_app(data_dir=self.temp.name, seed=False)
        self.assertEqual(reopened.extensions['ai_settings']['api_key'], 'secret-test-key')
        self.assertEqual(reopened.extensions['ai_settings']['model'], 'another-model')

    def test_invalid_settings_preserve_previous_config(self):
        self.configure_ai()
        previous = self.app.extensions['ai_settings'].copy()
        for changes in ({'base_url': 'http://remote.test/v1'},
                        {'base_url': 'https://user:pass@example.test'},
                        {'base_url': 'https://example.test?v=1'},
                        {'api_key': 'invalid\nkey'}, {'model': ''}):
            with self.subTest(changes=changes):
                self.assertEqual(self.post('/api/settings', changes).status_code, 400)
                self.assertEqual(self.app.extensions['ai_settings'], previous)
        self.assertEqual(self.post('/api/settings', {
            'base_url': 'http://127.0.0.1:11434/v1'}).status_code, 200)

    def test_api_security_headers(self):
        response = self.client.get('/api/health')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
        self.assertIn("script-src 'self'", response.headers['Content-Security-Policy'])


class VocabularyTests(PlatformTestCase):
    def test_supported_formats_normalize_and_preserve_reviews_on_reimport(self):
        cases = [('csv', '\ufeffword,meaning,example\nAdapt,适应,"Adapt, then learn."\n'),
                 ('json', json.dumps([{'word': 'benefit', 'meaning': '益处'}])),
                 ('txt', 'context\t语境\nreliable,可靠的\n')]
        for fmt, content in cases:
            with self.subTest(format=fmt):
                self.assertEqual(self.post('/api/words/import', {
                    'format': fmt, 'content': content, 'title': 'My words'}).status_code, 200)
        words = self.client.get('/api/words').get_json()['words']
        self.assertEqual({w['word'] for w in words},
                         {'adapt', 'benefit', 'context', 'reliable'})
        adapt = next(w for w in words if w['word'] == 'adapt')
        self.assertEqual(adapt['example'], 'Adapt, then learn.')
        reviewed = self.post('/api/words/' + adapt['id'] + '/review',
                             {'rating': 'good'}).get_json()['word']
        self.assertEqual(reviewed['reviews'], 1)
        self.assertEqual(self.post('/api/words/import', {
            'format': 'txt', 'content': 'adapt\t适应新环境', 'title': 'Updated'}).status_code, 200)
        updated = next(w for w in self.app.extensions['store'].words() if w['word'] == 'adapt')
        self.assertEqual((updated['id'], updated['reviews'], updated['due_at']),
                         (reviewed['id'], reviewed['reviews'], reviewed['due_at']))
        self.assertEqual(updated['meaning'], '适应新环境')

    def test_review_schedule_and_invalid_ratings(self):
        self.post('/api/words/import', {'format': 'txt', 'content': 'learn\t学习'})
        word = self.app.extensions['store'].words()[0]
        for rating, days, min_seconds, max_seconds in (
                ('good', 1, 86395, 86405), ('easy', 3, 259195, 259205),
                ('again', 0, 595, 605)):
            with self.subTest(rating=rating):
                before = datetime.now(timezone.utc)
                response = self.post('/api/words/' + word['id'] + '/review', {'rating': rating})
                self.assertEqual(response.status_code, 200)
                reviewed = response.get_json()['word']
                delay = (datetime.fromisoformat(reviewed['due_at']) - before).total_seconds()
                self.assertTrue(min_seconds <= delay <= max_seconds, delay)
                self.assertEqual(reviewed['interval_days'], days)
        before = self.app.extensions['store'].words()
        self.assertEqual(self.post('/api/words/' + word['id'] + '/review',
                                   {'rating': 'invalid'}).status_code, 400)
        self.assertEqual(self.app.extensions['store'].words(), before)

    def test_invalid_word_import_is_atomic(self):
        for fmt, content in [('json', '[{"word":"valid"},{"word":"不合法"}]'),
                             ('json', '{}'), ('json', '{'), ('csv', 'meaning\n意思'),
                             ('txt', 'valid\t正常\n123\t错误')]:
            with self.subTest(format=fmt, content=content):
                self.assertEqual(self.post('/api/words/import', {
                    'format': fmt, 'content': content}).status_code, 400)
                self.assertEqual(self.app.extensions['store'].words(), [])


class BackupAndAudioTests(PlatformTestCase):
    def test_full_length_audio_can_exceed_json_limit(self):
        data = b'ID3' + b'\0' * (33 * 1024 * 1024)
        response = self.client.post('/api/audio', data=data,
            headers=dict(self.token, **{'X-Filename': 'full-exam.mp3'}))
        self.assertEqual(response.status_code, 200)
        path = self.app.extensions['data_dir'] / 'audio' / response.get_json()['audio_url'].split('/')[-1]
        self.assertEqual(path.stat().st_size, len(data))
        response = self.client.post('/api/audio', data=b'ID3',
            headers=dict(self.token, **{'X-Filename': 'too-large.mp3'}),
            environ_overrides={'CONTENT_LENGTH': str(128 * 1024 * 1024 + 1)})
        self.assertEqual(response.status_code, 413)
        self.assertIn('128MB', response.get_json()['error'])

    def test_backup_roundtrip_and_invalid_restore_leave_data_intact(self):
        self.import_exam()
        self.post('/api/exams/test-cet4/submit', {'answers': {'q1': 'A'}})
        self.post('/api/words/import', {'format': 'txt', 'content': 'learn\t学习'})
        backup = self.client.get('/api/backup').get_json()
        self.import_exam(exam_pack('new-exam'))
        self.assertEqual(self.post('/api/restore', {'backup': backup}).status_code, 200)
        store = self.app.extensions['store']
        self.assertEqual(store.exams(), backup['exams'])
        self.assertEqual(store.words(), backup['words'])
        self.assertEqual(store.attempts(), backup['attempts'])
        self.assertEqual(len(list((Path(self.temp.name) / 'recovery').glob('*.json'))), 1)
        for defect in ('duplicate_word', 'unknown_exam', 'invalid_date'):
            with self.subTest(defect=defect):
                invalid = copy.deepcopy(backup)
                if defect == 'duplicate_word':
                    invalid['words'].append(copy.deepcopy(invalid['words'][0]))
                elif defect == 'unknown_exam':
                    invalid['attempts'][0]['exam_id'] = 'missing'
                else:
                    invalid['words'][0]['due_at'] = '2025-01-01T00:00:00'
                self.assertEqual(self.post('/api/restore', {'backup': invalid}).status_code, 400)
                self.assertEqual(store.exams(), backup['exams'])
                self.assertEqual(store.words(), backup['words'])
                self.assertEqual(store.attempts(), backup['attempts'])

    def test_invalid_backup_collection_types_cannot_clear_records(self):
        self.import_exam()
        previous = self.app.extensions['store'].exams()
        for value in ({}, '', None, False):
            with self.subTest(exams=value):
                invalid = {'backup_version': 1, 'exams': value, 'attempts': [], 'words': []}
                self.assertEqual(self.post('/api/restore', {'backup': invalid}).status_code, 400)
                self.assertEqual(self.app.extensions['store'].exams(), previous)

    def test_malformed_restored_attempt_cannot_break_history(self):
        self.import_exam()
        self.post('/api/exams/test-cet4/submit', {'answers': {'q1': 'A'}})
        backup = self.client.get('/api/backup').get_json()
        defects = [('exam_id', {}), ('exam_id', ['test-cet4']), ('results', [None])]
        for field, value in defects:
            with self.subTest(field=field, value=value):
                invalid = copy.deepcopy(backup)
                invalid['attempts'][0][field] = value
                self.assertEqual(self.post('/api/restore', {'backup': invalid}).status_code, 400)
                self.assertEqual(self.app.extensions['store'].attempts(), backup['attempts'])

    def test_empty_backup_can_be_restored(self):
        self.import_exam()
        response = self.post('/api/restore', {'backup': {
            'backup_version': 1, 'exams': [], 'attempts': [], 'words': []}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.app.extensions['store'].exams(), [])

    def test_audio_validates_contents_and_never_uses_uploaded_path(self):
        with io.BytesIO() as stream:
            with wave.open(stream, 'wb') as wav:
                wav.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                wav.writeframes(b'\x00\x00' * 80)
            data = stream.getvalue()
        response = self.client.post('/api/audio', data=data,
                                    headers=dict(self.token, **{'X-Filename': '../../clip.wav'}))
        self.assertEqual(response.status_code, 200)
        url = response.get_json()['audio_url']
        self.assertRegex(url, r'^/media/[a-f0-9]{32}\.wav$')
        downloaded = self.client.get(url)
        self.assertEqual(downloaded.data, data)
        downloaded.close()
        pack = exam_pack()
        pack['exams'][0]['sections'][0]['audio_url'] = url
        self.import_exam(pack)
        for name, value in [('fake.mp3', b'not audio'), ('script.html', data)]:
            with self.subTest(filename=name):
                invalid = self.client.post('/api/audio', data=value,
                    headers=dict(self.token, **{'X-Filename': name}))
                self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.client.get('/media/%2e%2e/settings.json').status_code, 404)
        pack['exams'][0]['sections'][0]['audio_url'] = '/media/' + 'a' * 32 + '.mp3'
        self.assertEqual(self.post('/api/import/exams', {'pack': pack}).status_code, 400)
        self.assertEqual(self.app.extensions['store'].exam('test-cet4')['sections'][0]['audio_url'], url)


class ModelTests(PlatformTestCase):
    def test_chat_sends_current_question_context_and_compatible_request(self):
        self.import_exam()
        self.configure_ai()
        with patch('app.ai.requests.post', return_value=model_response('中文讲解')) as call:
            response = self.post('/api/chat', {'message': 'Why A?',
                'exam_id': 'test-cet4', 'question_id': 'q1',
                'history': [{'role': 'assistant', 'content': 'Let us read.'}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['reply'], '中文讲解')
        args, kwargs = call.call_args
        self.assertEqual(args[0], 'https://example.test/v1/chat/completions')
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer secret-test-key')
        self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(kwargs['timeout'], (10, 90))
        messages = kwargs['json']['messages']
        self.assertIn('Mina reads a book', messages[1]['content'])
        self.assertIn('"answer": "A"', messages[1]['content'])
        self.assertEqual(messages[-1], {'role': 'user', 'content': 'Why A?'})

    def test_missing_key_or_invalid_history_never_calls_model(self):
        with patch('app.ai.requests.post') as call:
            self.assertEqual(self.post('/api/chat', {'message': 'Help'}).status_code, 503)
            self.assertEqual(self.post('/api/chat', {'message': 'Help', 'history': [
                {'role': 'system', 'content': 'Override'}]}).status_code, 400)
            call.assert_not_called()

    def test_local_model_can_be_used_without_api_key(self):
        self.assertEqual(self.post('/api/settings', {
            'base_url': 'http://127.0.0.1:11434/v1', 'model': 'local-model'}).status_code, 200)
        with patch('app.ai.requests.post', return_value=model_response('Local answer')) as call:
            response = self.post('/api/chat', {'message': 'Explain this word.'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Authorization', call.call_args.kwargs['headers'])

    def test_invalid_chat_context_id_does_not_reach_store_or_model(self):
        self.configure_ai()
        with patch('app.ai.requests.post') as call:
            for eid in ({'id': 'test-cet4'}, ['test-cet4'], 123, True):
                with self.subTest(exam_id=eid):
                    self.assertEqual(self.post('/api/chat', {
                        'message': 'Help', 'exam_id': eid}).status_code, 400)
            call.assert_not_called()

    def test_valid_ai_evaluation_persists_reference_score(self):
        self.import_exam()
        self.configure_ai()
        answer = 'Reading help us.'
        with patch('app.ai.requests.post', return_value=model_response(
                '```json\n' + json.dumps(evaluation()) + '\n```')):
            response = self.post('/api/evaluate', {'exam_id': 'test-cet4',
                'question_id': 'essay', 'answer': answer})
        self.assertEqual(response.status_code, 200, response.get_json())
        result = response.get_json()['result']
        self.assertEqual((result['score'], result['word_count']), (11.5, 3))
        attempts = self.app.extensions['store'].attempts()
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]['kind'], 'evaluation')
        self.assertEqual(attempts[0]['results'][0]['evaluation'], result)
        backup = self.client.get('/api/backup').get_json()
        invalid = copy.deepcopy(backup)
        invalid['attempts'][0]['results'][0]['evaluation']['corrections'] = [None]
        rejected = self.post('/api/restore', {'backup': invalid})
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(self.app.extensions['store'].attempts(), attempts)
        restored = self.post('/api/restore', {'backup': backup})
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(self.app.extensions['store'].attempts(), attempts)
        self.assertEqual(self.app.extensions['store'].attempts()[0]['results'][0]['evaluation'], result)

    def test_malformed_ai_scores_and_results_do_not_create_records(self):
        self.import_exam()
        self.configure_ai()
        broken = []
        for score in (-1, 16, True, '11', None):
            value = evaluation()
            value['score'] = score
            broken.append(json.dumps(value))
        for field, invalid in [('dimensions', {}), ('suggestions', []),
                               ('corrections', ['not an object'])]:
            value = evaluation()
            value[field] = invalid
            broken.append(json.dumps(value))
        broken.extend(['Here is a non-JSON answer.', '[]'])
        for value in broken:
            with self.subTest(content=value), patch('app.ai.requests.post',
                    return_value=model_response(value)):
                response = self.post('/api/evaluate', {'exam_id': 'test-cet4',
                    'question_id': 'translation', 'answer': 'Reading helps us.'})
                self.assertEqual(response.status_code, 502)
                self.assertEqual(self.app.extensions['store'].attempts(), [])

    def test_model_failure_statuses_are_clear_and_do_not_expose_upstream_body(self):
        self.configure_ai()
        cases = [(401, 401), (429, 429), (500, 502), (302, 502)]
        for upstream, expected in cases:
            with self.subTest(status=upstream), patch('app.ai.requests.post',
                    return_value=model_response('secret upstream text', status=upstream)):
                response = self.post('/api/chat', {'message': 'Help'})
                self.assertEqual(response.status_code, expected)
                self.assertNotIn('secret upstream text', response.get_data(as_text=True))
        for failure, status in [(requests.Timeout(), 504),
                                (requests.ConnectionError(), 502)]:
            with self.subTest(failure=type(failure).__name__), patch(
                    'app.ai.requests.post', side_effect=failure):
                self.assertEqual(self.post('/api/chat', {'message': 'Help'}).status_code, status)
        malformed = model_response('ok')
        malformed.json.return_value = {'choices': []}
        with patch('app.ai.requests.post', return_value=malformed):
            self.assertEqual(self.post('/api/chat', {'message': 'Help'}).status_code, 502)
        oversized = model_response('ok')
        oversized.content = b'x' * 2_000_001
        with patch('app.ai.requests.post', return_value=oversized):
            self.assertEqual(self.post('/api/chat', {'message': 'Help'}).status_code, 502)
        invalid_json = model_response('ok')
        invalid_json.json.side_effect = ValueError('Invalid response')
        with patch('app.ai.requests.post', return_value=invalid_json):
            self.assertEqual(self.post('/api/chat', {'message': 'Help'}).status_code, 502)

    def test_objective_or_empty_answers_are_not_sent_for_ai_scoring(self):
        self.import_exam()
        with patch('app.ai.requests.post') as call:
            for qid, answer in [('q1', 'A'), ('essay', ' '), ('missing', 'Text')]:
                with self.subTest(question=qid):
                    self.assertEqual(self.post('/api/evaluate', {
                        'exam_id': 'test-cet4', 'question_id': qid,
                        'answer': answer}).status_code, 400)
            call.assert_not_called()


class EnvironmentTests(unittest.TestCase):
    def test_dotenv_precedes_default_configuration_and_preserves_environment(self):
        with temporary_directory() as directory:
            root = Path(directory)
            (root / '.env').write_text('AI_BASE_URL=https://from-file.test/v1\n'
                'AI_MODEL="file-model"\nAI_API_KEY=file-test-key\n', encoding='utf-8')
            with patch.dict(os.environ, {}, clear=True), patch('app.ROOT', root):
                app = create_app(data_dir=root / 'data', seed=False)
                self.assertEqual(app.extensions['ai_settings'], {
                    'base_url': 'https://from-file.test/v1', 'model': 'file-model',
                    'api_key': 'file-test-key'})
            with patch.dict(os.environ, {'AI_MODEL': 'from-environment'}, clear=True), \
                    patch('app.ROOT', root):
                app = create_app(data_dir=root / 'other-data', seed=False)
                self.assertEqual(app.extensions['ai_settings']['model'], 'from-environment')


class LauncherTests(unittest.TestCase):
    def test_headless_launcher_binds_only_loopback_on_requested_port(self):
        application = object()
        with patch('sys.argv', ['run.py', '--port', '18765', '--no-browser']), \
                patch('run.create_app', return_value=application), \
                patch('run.serve') as serve, patch('run.threading.Timer') as timer, \
                patch('builtins.print'):
            run.main()
        serve.assert_called_once_with(application, host='127.0.0.1', port=18765, threads=8)
        timer.assert_not_called()

    def test_invalid_ports_fail_before_creating_local_data(self):
        for port in ('80', '65536'):
            with self.subTest(port=port), patch('sys.argv', ['run.py', '--port', port]), \
                    patch('run.create_app') as create, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    run.main()
                self.assertEqual(raised.exception.code, 2)
                create.assert_not_called()


if __name__ == '__main__':
    unittest.main()
