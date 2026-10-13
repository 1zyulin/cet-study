"""Shared words retain book membership and learning history."""
import copy
import tempfile
import unittest
from pathlib import Path

from app.content import ContentError, validate_pack
from app.store import Store, dumps, validate_backup


class WordMembershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'study.sqlite3')
        self.word = dict(word='learn', meaning='学习', phonetic='lɜːn', example='')

    def test_shared_word_keeps_review_and_both_books(self):
        self.store.import_words([self.word], 'CET4')
        before = self.store.words()[0]
        reviewed = self.store.review(before['id'], 'good')
        self.store.import_words([self.word], 'CET6')
        after = self.store.words()[0]
        self.assertEqual(after['books'], ['CET4', 'CET6'])
        for key in ('id', 'reviews', 'due_at', 'interval_days'):
            self.assertEqual(after[key], reviewed[key])
        self.store.import_words([self.word], 'CET6')
        self.assertEqual(self.store.words()[0]['books'], ['CET4', 'CET6'])

    def test_old_record_gains_membership_without_losing_old_book(self):
        self.store.import_words([self.word], 'Old book')
        legacy = self.store.words()[0]
        del legacy['books']
        with self.store.connect() as db:
            db.execute('UPDATE words SET data=? WHERE id=?', (dumps(legacy), legacy['id']))
        self.store.import_words([self.word], 'CET6')
        self.assertEqual(self.store.words()[0]['books'], ['Old book', 'CET6'])

    def test_backup_restore_preserves_book_membership(self):
        self.store.import_words([self.word], 'CET4')
        self.store.import_words([self.word], 'CET6')
        backup = self.store.backup()
        exams, attempts, words = validate_backup(backup, validate_pack)
        self.store.restore(exams, attempts, words)
        self.assertEqual(self.store.words()[0]['books'], ['CET4', 'CET6'])
        old = copy.deepcopy(backup)
        del old['words'][0]['books']
        self.assertEqual(validate_backup(old, validate_pack)[2][0]['books'], ['CET6'])

    def test_malformed_membership_is_rejected_before_restore(self):
        self.store.import_words([self.word], 'CET4')
        for books in ('CET4', ['CET4', 'CET4'], ['CET6'], ['']):
            with self.subTest(books=books):
                backup = self.store.backup()
                backup['words'][0]['books'] = books
                with self.assertRaises(ContentError):
                    validate_backup(backup, validate_pack)


if __name__ == '__main__':
    unittest.main()
