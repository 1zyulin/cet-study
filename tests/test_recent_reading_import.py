"""Source-download integrity tests with local fixtures and no real network."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.import_recent_reading import download_pdf


SOURCE_URL = 'https://github.com/0609x/CET46-Resources/blob/main/original-test.pdf'


def git_blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def original_pdf():
    """An original, valid one-page PDF including its own cross-reference table."""
    data = bytearray(b'%PDF-1.4\n')
    offsets = []
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Resources << >> /Contents 4 0 R >>',
        b'<< /Length 0 >>\nstream\nendstream',
    ]
    for number, content in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f'{number} 0 obj\n'.encode('ascii') + content + b'\nendobj\n')
    xref = len(data)
    data.extend(b'xref\n0 5\n0000000000 65535 f \n')
    for offset in offsets:
        data.extend(f'{offset:010d} 00000 n \n'.encode('ascii'))
    data.extend(f'trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode('ascii'))
    return bytes(data)


def record_for(data, **changes):
    return dict({'url': SOURCE_URL, 'bytes': len(data), 'blob_sha': git_blob_sha(data)}, **changes)


def response_for(chunks):
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.iter_content.return_value = iter(chunks)
    return response


class RecentReadingDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.test-recent-', dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pdf = original_pdf()

    def test_complete_verified_pdf_is_written_after_streaming(self):
        target = self.root / 'verified.pdf'
        response = response_for([self.pdf[:11], b'', self.pdf[11:100], self.pdf[100:]])
        with patch('requests.get', return_value=response) as request:
            download_pdf(record_for(self.pdf), target)
        self.assertEqual(target.read_bytes(), self.pdf)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0],
                         'https://raw.githubusercontent.com/0609x/CET46-Resources/main/original-test.pdf')
        self.assertTrue(request.call_args.kwargs['stream'])
        self.assertGreater(request.call_args.kwargs['timeout'], 0)
        response.raise_for_status.assert_called_once()

    def test_bad_hash_length_or_signature_never_create_or_overwrite_a_file(self):
        cases = [
            ('hash', self.pdf, record_for(self.pdf, blob_sha='0' * 40)),
            ('length', self.pdf, record_for(self.pdf, bytes=len(self.pdf) + 1)),
            ('signature', b'<html>Original non-PDF test response</html>',
             record_for(b'<html>Original non-PDF test response</html>')),
        ]
        for name, data, record in cases:
            for existing in (False, True):
                with self.subTest(defect=name, existing=existing):
                    target = self.root / f'{name}-{existing}.pdf'
                    if existing:
                        target.write_bytes(b'existing cache must survive')
                    response = response_for([data[:5], data[5:]])
                    with patch('requests.get', return_value=response):
                        with self.assertRaisesRegex(ValueError, 'changed or download incomplete'):
                            download_pdf(record, target)
                    if existing:
                        self.assertEqual(target.read_bytes(), b'existing cache must survive')
                    else:
                        self.assertFalse(target.exists())

    def test_unapproved_sources_are_rejected_without_any_network_request(self):
        urls = [
            'http://github.com/0609x/CET46-Resources/blob/main/original-test.pdf',
            'https://github.com.attacker.invalid/0609x/CET46-Resources/blob/main/original-test.pdf',
            'https://github.com/0609x/another-repository/blob/main/original-test.pdf',
            'https://github.com/0609x/CET46-Resources/blob/main.attacker/original-test.pdf',
        ]
        target = self.root / 'source.pdf'
        target.write_bytes(b'previous source')
        for url in urls:
            with self.subTest(url=url):
                with patch('requests.get') as request:
                    with self.assertRaisesRegex(ValueError, 'Unsupported PDF source URL'):
                        download_pdf(record_for(self.pdf, url=url), target)
                    request.assert_not_called()
                self.assertEqual(target.read_bytes(), b'previous source')

    def test_stream_over_four_mebibytes_aborts_without_saving_or_consuming_more(self):
        limit = 4 * 1024 * 1024
        chunk = b'%PDF-' + b'x' * (65536 - 5)

        def oversized_chunks():
            for _ in range(64):
                yield chunk
            yield b'x'
            raise AssertionError('Downloader consumed bytes after exceeding its stream limit')

        for existing in (False, True):
            with self.subTest(existing=existing):
                target = self.root / f'oversized-{existing}.pdf'
                if existing:
                    target.write_bytes(b'previous cache')
                response = response_for(oversized_chunks())
                record = record_for(self.pdf, bytes=limit + 1)
                with patch('requests.get', return_value=response):
                    with self.assertRaisesRegex(ValueError, 'exceeds 4MB'):
                        download_pdf(record, target)
                if existing:
                    self.assertEqual(target.read_bytes(), b'previous cache')
                else:
                    self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
