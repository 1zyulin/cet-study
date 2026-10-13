"""Synthetic dictionary fixtures verify source filtering and safe downloads."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools import import_wordbooks as importer


def temporary_directory():
    return tempfile.TemporaryDirectory(prefix='.test-wordbook-', dir=Path(__file__).resolve().parent)


class WordbookImportTests(unittest.TestCase):
    def test_cet6_includes_foundations_without_matching_partial_tag_names(self):
        rows = [
            {'word': 'alpha', 'translation': '自创释义甲', 'phonetic': '/a/', 'tag': 'gk cet4'},
            {'word': 'beta', 'translation': '自创释义乙', 'phonetic': '/b/', 'tag': 'cet6'},
            {'word': 'gamma', 'translation': '自创释义丙', 'phonetic': '', 'tag': 'cet4 cet6'},
            {'word': 'ignore', 'translation': '不导入', 'tag': 'cet40 nocet6'},
        ]
        books, report = importer.convert_rows(rows)
        self.assertEqual([w['word'] for w in books['cet4']], ['alpha', 'gamma'])
        self.assertEqual([w['word'] for w in books['cet6']], ['alpha', 'beta', 'gamma'])
        self.assertEqual(report['source_counts'], {'rows': 4, 'cet4_tagged': 2, 'cet6_tagged': 2})
        self.assertTrue(all(w['example'] == '' for w in books['cet6']))

    def test_rejected_words_and_missing_translations_are_reported_not_repaired(self):
        rows = [{'word': 'alpha', 'translation': '甲\\n乙', 'tag': 'cet4'},
                {'word': 'café', 'translation': '带重音不改写', 'tag': 'cet6'},
                {'word': 'unit2', 'translation': '数字不改写', 'tag': 'cet4'},
                {'word': 'empty', 'translation': '', 'tag': 'cet6'}]
        books, report = importer.convert_rows(rows)
        self.assertEqual(len(books['cet6']), 1)
        self.assertEqual(books['cet4'][0]['meaning'], '甲\n乙')
        self.assertEqual([r['word'] for r in report['skipped']], ['café', 'unit2', 'empty'])

    def test_duplicate_normalized_word_keeps_first_source_entry(self):
        books, report = importer.convert_rows([
            {'word': 'Alpha', 'translation': '甲', 'tag': 'cet4'},
            {'word': 'alpha', 'translation': '冲突释义', 'tag': 'cet4'}])
        self.assertEqual(books['cet4'][0]['meaning'], '甲')
        self.assertEqual(len(books['cet6']), 1)
        self.assertEqual(report['skipped_records'], 2)

    def test_missing_csv_headers_rejected(self):
        with temporary_directory() as directory:
            source = Path(directory) / 'bad.csv'
            source.write_text('word,tag\nalpha,cet4\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'headers'):
                importer.convert_csv(source)

    def response(self, data):
        response = Mock()
        response.url = importer.SOURCE_URL
        response.iter_content.return_value = iter([data])
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_download_hash_verification_then_atomic_replacement(self):
        data = b'original synthetic dictionary fixture'
        digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        with temporary_directory() as directory:
            target = Path(directory) / 'source.csv'
            target.write_bytes(b'old file')
            with patch('requests.get', return_value=self.response(data)), \
                 patch.object(importer, 'SOURCE_BYTES', len(data)), \
                 patch.object(importer, 'SOURCE_BLOB', digest):
                hashes = importer.download_source(target)
            self.assertEqual(target.read_bytes(), data)
            self.assertEqual(hashes['git_blob_sha'], digest)
            self.assertFalse(target.with_suffix('.csv.partial').exists())

    def test_bad_download_keeps_existing_source_and_cleans_partial(self):
        with temporary_directory() as directory:
            target = Path(directory) / 'source.csv'
            target.write_bytes(b'old file')
            with patch('requests.get', return_value=self.response(b'bad')), \
                 self.assertRaisesRegex(ValueError, 'incomplete or changed'):
                importer.download_source(target)
            self.assertEqual(target.read_bytes(), b'old file')
            self.assertFalse(target.with_suffix('.csv.partial').exists())

    def test_oversized_download_stops_and_cleans_partial(self):
        with temporary_directory() as directory:
            target = Path(directory) / 'source.csv'
            with patch('requests.get', return_value=self.response(b'12345')), \
                 patch.object(importer, 'MAX_SOURCE_BYTES', 4), \
                 self.assertRaisesRegex(ValueError, 'exceeds'):
                importer.download_source(target)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix('.csv.partial').exists())


if __name__ == '__main__':
    unittest.main()
