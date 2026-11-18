import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from batch_processor import deliver, process, verify
from main import main

ROOT = Path(__file__).resolve().parents[1]


class ProcessorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'input.txt'
        self.output = self.root / 'output'
        self.source.write_bytes(b'id|group|value\r\n1|ALPHA|10\r\n2|BETA|20\r\n3|ALPHA|30')

    def run_batch(self):
        return process(self.source, self.output)

    def test_preserves_header_records_and_final_missing_newline(self):
        original = self.source.read_bytes()
        batch = self.run_batch()
        manifest = verify(batch)
        self.assertEqual(manifest['records'], 3)
        outputs = {item['group']: (batch / item['name']).read_bytes() for item in manifest['files']}
        self.assertEqual(outputs['ALPHA'], b'id|group|value\r\n1|ALPHA|10\r\n3|ALPHA|30')
        self.assertEqual(outputs['BETA'], b'id|group|value\r\n2|BETA|20\r\n')
        self.assertEqual(self.source.read_bytes(), original)

    def test_repeat_reuses_batch(self):
        first = self.run_batch()
        before = (first / 'manifest.json').stat().st_mtime_ns
        self.assertEqual(first, self.run_batch())
        self.assertEqual(before, (first / 'manifest.json').stat().st_mtime_ns)
        self.assertEqual(len(list(self.output.iterdir())), 1)

    def test_invalid_input_leaves_no_partial_batch(self):
        for content in (b'', b'id|group\n', b'id|id\n1|A\n', b'id|group\n1|../bad\n',
                        b'id|group\n1|A\ninvalid\n', b'id|group\n1|A|extra\n'):
            with self.subTest(content=content):
                self.source.write_bytes(content)
                with self.assertRaises(ValueError):
                    self.run_batch()
                self.assertEqual(list(self.output.iterdir()), [])
                self.assertEqual(self.source.read_bytes(), content)

    def test_same_length_corruption_detected(self):
        batch = self.run_batch()
        item = verify(batch)['files'][0]
        path = batch / item['name']
        path.write_bytes(path.read_bytes().replace(b'10', b'99'))
        with self.assertRaises(ValueError):
            verify(batch)
        with self.assertRaises(ValueError):
            self.run_batch()

    def test_unexpected_file_detected(self):
        batch = self.run_batch()
        (batch / 'extra.txt').write_text('extra')
        with self.assertRaises(ValueError):
            verify(batch)

    def test_unsafe_manifest_name_rejected(self):
        batch = self.run_batch()
        manifest = verify(batch)
        manifest['files'][0]['name'] = '../outside.txt'
        (batch / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            verify(batch)

    def test_case_distinct_groups_do_not_collide(self):
        self.source.write_bytes(b'id|group\n1|alpha\n2|ALPHA\n')
        manifest = verify(self.run_batch())
        self.assertEqual(len({item['name'].lower() for item in manifest['files']}), 2)

    def test_many_interleaved_groups(self):
        self.source.write_text('id|group\n' + ''.join(f'{i}|G{i % 50}\n' for i in range(200)))
        manifest = verify(self.run_batch())
        self.assertEqual(len(manifest['files']), 50)
        self.assertTrue(all(item['records'] == 4 for item in manifest['files']))

    def test_custom_delimiter_and_column(self):
        self.source.write_bytes(b'team;id\nRED;1\nBLUE;2\n')
        batch = process(self.source, self.output, 'team', ';')
        self.assertEqual(verify(batch)['records'], 2)

    def test_limits_cleanup(self):
        with patch('batch_processor.MAX_LINE_BYTES', 20):
            self.source.write_bytes(b'id|group\n' + b'x' * 21)
            with self.assertRaises(ValueError):
                self.run_batch()
        self.assertEqual(list(self.output.iterdir()), [])
        self.source.write_bytes(b'id|group\n1|A\n2|B\n')
        with patch('batch_processor.MAX_GROUPS', 1):
            with self.assertRaises(ValueError):
                self.run_batch()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_delivery_verified_and_repeatable(self):
        batch = self.run_batch()
        delivered = deliver(batch, self.root / 'delivery')
        self.assertEqual(verify(batch), verify(delivered))
        self.assertEqual(delivered, deliver(batch, self.root / 'delivery'))

    def test_failed_delivery_leaves_no_partial_batch(self):
        batch = self.run_batch()
        destination = self.root / 'delivery'
        with patch('batch_processor.shutil.copytree', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                deliver(batch, destination)
        self.assertEqual(list(destination.iterdir()), [])
        self.assertEqual(verify(batch)['records'], 3)

    def test_cli_failure_exit_status(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['run', '--input', str(self.root / 'missing')]), 1)

    def test_real_cli_and_synthetic_expected_result(self):
        result = subprocess.run([sys.executable, str(ROOT / 'main.py'), 'run',
                                 '--input', str(ROOT / 'examples/input/events.txt'),
                                 '--output', str(self.output), '--delivery', str(self.root / 'delivery')],
                                capture_output=True, text=True, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual((report['records'], report['groups']), (12, 3))
        self.assertEqual(verify(report['batch']), verify(ROOT / 'examples/expected'))


if __name__ == '__main__':
    unittest.main()
