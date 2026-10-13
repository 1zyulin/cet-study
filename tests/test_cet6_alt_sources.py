"""Validate pinned metadata and bounded local source downloads with fixtures."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from tools import fetch_cet6_alt_sources as fetcher


class Cet6AlternativeSourceTests(unittest.TestCase):
    def fixture(self):
        data = b'%PDF-1.7\noriginal synthetic test source\n'
        path = 'cet6_2025/cet6_2025_06_1.pdf'
        item = {'repository': fetcher.SOURCES['loveitsuka'], 'ref': fetcher.LOVEITSUKA_REF,
                'path': path, 'local_name': 'loveitsuka_2025_06_1.pdf', 'size': len(data),
                'blob_sha': fetcher.git_blob_sha(data),
                'download_url': 'https://raw.githubusercontent.com/' + fetcher.SOURCES['loveitsuka'] + '/' + fetcher.LOVEITSUKA_REF + '/' + path}
        return data, item

    def test_all_published_metadata_validates(self):
        index = json.loads(fetcher.INDEX.read_text(encoding='utf-8'))
        for item in index['files']:
            with self.subTest(file=item['local_name']):
                self.assertEqual(fetcher.validate_item(item), item['download_url'])
        items = [item for item in index['files'] if item['repository'] == fetcher.SOURCES['loveitsuka']]
        self.assertEqual(len(items), 6)
        self.assertTrue(all(item['ref'] == fetcher.LOVEITSUKA_REF for item in items))

    def test_unpinned_ref_url_and_unsafe_names_rejected(self):
        _, item = self.fixture()
        for field, value in [('ref', 'main'), ('repository', 'unknown/project'),
                             ('path', '../file.pdf'), ('local_name', '../file.pdf'),
                             ('download_url', 'https://example.com/source.pdf'),
                             ('size', True), ('size', fetcher.MAX_SIZE + 1),
                             ('blob_sha', 'invalid')]:
            candidate = copy.deepcopy(item)
            candidate[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                fetcher.validate_item(candidate)

    def test_hash_size_and_pdf_header_must_agree(self):
        data, item = self.fixture()
        self.assertEqual(fetcher.checked_bytes(data, item), data)
        with self.assertRaisesRegex(ValueError, 'size/hash'):
            fetcher.checked_bytes(data + b'extra', item)
        bad = b'not a PDF'
        item.update(size=len(bad), blob_sha=fetcher.git_blob_sha(bad))
        with self.assertRaisesRegex(ValueError, 'PDF'):
            fetcher.checked_bytes(bad, item)

    def test_verified_cache_avoids_network_and_bad_download_cannot_replace_it(self):
        data, item = self.fixture()
        with tempfile.TemporaryDirectory(prefix='.test-alt-', dir=Path(__file__).resolve().parent) as directory:
            destination = Path(directory)
            target = destination / item['local_name']
            target.write_bytes(data)
            with patch('requests.get') as request:
                self.assertEqual(fetcher.fetch_one(item, destination)['status'], 'cached')
                request.assert_not_called()
            target.write_bytes(b'previous invalid cache')
            response = MagicMock()
            response.__enter__.return_value = response
            response.status_code = 200
            response.iter_content.return_value = [data + b'oversized']
            with patch('requests.get', return_value=response), self.assertRaisesRegex(ValueError, 'exceeds'):
                fetcher.fetch_one(item, destination)
            self.assertEqual(target.read_bytes(), b'previous invalid cache')


if __name__ == '__main__':
    unittest.main()
