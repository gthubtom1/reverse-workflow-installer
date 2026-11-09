"""Offline notice/selected-feature gate tests. Tiny module fixtures are never distributions."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import argparse
from unittest.mock import patch
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import build_craft_bundle as b
import craft
from versions import InstallError


class PiNoticeTests(unittest.TestCase):
    def setUp(self):
        parent = REPO / '.local/tests'
        parent.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='pi-notices-', dir=parent)
        self.root = Path(self.tmp.name)
        self.dist = self.root / 'distribution'
        self.package = self.dist / 'node_modules' / b.PI_PACKAGE
        self.package.mkdir(parents=True)
        b.write_json(self.package / 'package.json', {'name': b.PI_PACKAGE, 'version': b.PI_VERSION})
        self.integrity = 'sha512-YWJj'
        b.write_json(self.dist / 'package-lock.json', {'lockfileVersion': 3, 'packages': {'': {}, 'node_modules/' + b.PI_PACKAGE: {
            'version': b.PI_VERSION, 'resolved': 'https://registry.npmjs.org/pi/-/pi.tgz', 'integrity': self.integrity}}})

    def tearDown(self):
        self.tmp.cleanup()

    def registry_fixture(self):
        source = self.root / 'source-notices'
        source.mkdir()
        # Use actual collected official grant bytes, not an invented license.
        text = (b.RUNTIME / 'pi/notices/pi-1.5.0-LICENSE').read_bytes()
        (source / 'LICENSE').write_bytes(text)
        item = {'name': b.PI_PACKAGE, 'version': b.PI_VERSION, 'status': 'resolved',
                'integrity': self.integrity, 'license_file': 'LICENSE', 'license_sha256': b.sha(source / 'LICENSE'),
                'license_bytes': len(text), 'reason': 'Fixture tag/version/time association, not an attestation'}
        b.write_json(source / 'source-registry.json', {'schema_version': 1, 'packages': [item],
                    'artifact_hashes': {'LICENSE': {'sha256': b.sha(source / 'LICENSE'), 'bytes': len(text)}}})
        return source, b.sha(source / 'source-registry.json'), item

    def test_acquire_rejects_wrong_cached_node_before_npm_or_network(self):
        archive = self.root / 'wrong-node.zip'
        archive.write_bytes(b'inert invalid archive fixture')
        with patch.object(b.craft, 'host', return_value={'os': 'windows', 'arch': 'x86_64'}), patch.object(b, 'prepare_pi') as install, patch.object(b, 'download_node_archive') as network:
            with self.assertRaisesRegex(InstallError, 'cached official Node archive SHA256 mismatch'):
                b.acquire_pi(argparse.Namespace(stage=str(self.root / 'fresh-acquisition'), node_archive=str(archive), lock=str(b.RUNTIME / 'pi/package-lock.json')))
        install.assert_not_called()
        network.assert_not_called()
        self.assertEqual(archive.read_bytes(), b'inert invalid archive fixture')

    def test_node_download_refuses_unapproved_origin_before_network(self):
        pin = b.load_json(b.RUNTIME / 'pi/node-windows-x64.json')
        bad = {**pin, 'url': 'https://example.invalid/node.zip'}
        with patch.object(b, 'urlopen') as network, self.assertRaisesRegex(InstallError, 'unsupported official Node archive pin'):
            b.download_node_archive(bad, self.root / 'download.zip')
        network.assert_not_called()

    def test_node_download_digest_failure_cannot_reach_extraction(self):
        pin = b.load_json(b.RUNTIME / 'pi/node-windows-x64.json')
        import io
        class Response(io.BytesIO):
            def geturl(self):
                return pin['url']
        target = self.root / 'download.zip'
        with patch.object(b, 'urlopen', return_value=Response(b'corrupt network bytes')), self.assertRaisesRegex(InstallError, 'archive SHA256 mismatch'):
            b.download_node_archive(pin, target)
        self.assertEqual(target.read_bytes(), b'corrupt network bytes')
        self.assertFalse((self.root / 'node.exe').exists())

    def test_official_node_npmrc_exception_requires_exact_archive_identity(self):
        import zipfile
        archive = self.root / 'node-like.zip'
        pin = b.load_json(b.RUNTIME / 'pi/node-windows-x64.json')
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr(pin['archive_root'] + '/node_modules/npm/.npmrc', 'prefix=fixture')
        with self.assertRaisesRegex(InstallError, 'credential/profile'):
            b.safe_extract_zip(archive, self.root / 'ordinary-extraction')
        with self.assertRaisesRegex(InstallError, 'archive identity required'):
            b.extract_official_node(archive, self.root / 'official-extraction', pin)
        self.assertFalse((self.root / 'ordinary-extraction').exists())
        self.assertFalse((self.root / 'official-extraction').exists())

    def test_public_acquire_total_deadline_stops_continuous_slow_stream_and_descendants(self):
        import http.server
        import threading
        import time
        closed = threading.Event()
        class Slow(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                try:
                    while True:
                        self.wfile.write(b'x')
                        self.wfile.flush()
                        time.sleep(0.02)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    closed.set()
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Slow)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        worker = self.root / 'slow-worker.py'
        worker.write_text('import subprocess,sys,time\nfrom pathlib import Path\nfrom urllib.request import urlopen\np=Path(sys.argv[2]);p.mkdir()\nc=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"])\n(p/"child.pid").write_text(str(c.pid))\nurlopen(sys.argv[1],timeout=30).read(65536)\n(p/"acquisition-result.json").write_text("{}")\n', encoding='utf-8')
        stage = self.root / 'slow-acquisition'
        args = argparse.Namespace(stage=str(stage), lock='unused', node_archive=None, deadline_seconds=1, _worker_token=None)
        started = time.monotonic()
        try:
            with patch.object(b, 'acquisition_worker_command', return_value=[sys.executable, worker, f'http://127.0.0.1:{server.server_port}/slow', stage]):
                with self.assertRaisesRegex(InstallError, 'total deadline/lifecycle failure'):
                    b.acquire_cli(args)
            self.assertLess(time.monotonic() - started, 8)
            self.assertTrue(closed.wait(3), 'slow stream connection not closed')
            self.assertTrue((stage / 'child.pid').exists())
            self.assertFalse((stage / 'acquisition-result.json').exists())
            failure = b.load_json(stage / 'acquisition-failure.json')
            self.assertTrue(failure['timed_out'])
            if b.os.name == 'nt':
                self.assertEqual(failure['cleanup'], 'verified')
        finally:
            server.shutdown()
            server.server_close()

    def test_public_acquire_unknown_cleanup_removes_completion_and_existing_stage_is_preserved(self):
        stage = self.root / 'candidate'
        args = argparse.Namespace(stage=str(stage), lock='unused', node_archive=None, deadline_seconds=2, _worker_token=None)
        def uncertain(*a, **k):
            stage.mkdir()
            b.write_json(stage / 'acquisition-result.json', {'premature': True})
            return {'returncode': 0, 'timed_out': False, 'cleanup': 'unknown', 'had_descendants': True, 'scope': 'fixture', 'stderr': ''}
        with patch.object(b, 'run_owned', side_effect=uncertain), self.assertRaisesRegex(InstallError, 'cleanup=unknown'):
            b.acquire_cli(args)
        self.assertFalse((stage / 'acquisition-result.json').exists())
        b.write_json(stage / 'acquisition-result.json', {'existing': True})
        with self.assertRaisesRegex(InstallError, 'fresh directory'):
            b.acquire_cli(args)
        self.assertEqual(b.load_json(stage / 'acquisition-result.json'), {'existing': True})

    def test_unlicense_requires_actual_dedication_grant_and_disclaimer(self):
        text = (b.RUNTIME / 'pi/notices/fast-sha256-1.3.0-LICENSE').read_text(encoding='utf-8')
        self.assertTrue(b.has_license_grant(text))
        self.assertFalse(b.has_license_grant('SPDX-License-Identifier: Unlicense\n' + 'Unlicense ' * 100))
        self.assertFalse(b.has_license_grant(text.replace('Anyone is free to copy, modify, publish, use, compile, sell, or', 'Grant text omitted')))
        self.assertFalse(b.has_license_grant('License: MIT\n' * 100))

    def test_registry_is_copied_exactly_and_association_limit_is_retained(self):
        source, digest, item = self.registry_fixture()
        before = b.tree(source)
        b.integrate_notice_sources(self.dist, source, digest)
        report = b.npm_notice_inventory(self.dist)
        self.assertFalse(report['missing'])
        self.assertEqual(report['source_registry_sha256'], digest)
        self.assertEqual(report['packages'][0]['source_association'], item)
        self.assertIn('not an attestation', report['packages'][0]['source_association']['reason'])
        self.assertEqual(b.tree(source), before)
        self.assertEqual((self.dist / 'licenses/pi/LICENSE').read_bytes(), (source / 'LICENSE').read_bytes())
        b.write_json(self.dist / 'NOTICE-inventory.json', report)
        self.assertEqual(b.require_pi_notices(self.dist), report)

    def test_wrong_registry_hash_and_corrupted_source_notice_fail_before_copy(self):
        source, digest, item = self.registry_fixture()
        with self.assertRaisesRegex(InstallError, 'registry SHA256 mismatch'):
            b.integrate_notice_sources(self.dist, source, '0' * 64)
        self.assertFalse((self.dist / 'licenses/pi').exists())
        (source / 'LICENSE').write_text('drift')
        with self.assertRaisesRegex(InstallError, 'hash/size mismatch'):
            b.integrate_notice_sources(self.dist, source, digest)
        self.assertFalse((self.dist / 'licenses/pi').exists())

    def test_notice_drift_and_wrong_exact_npm_association_fail(self):
        source, digest, item = self.registry_fixture()
        b.integrate_notice_sources(self.dist, source, digest)
        path = self.dist / 'licenses/pi/LICENSE'
        before = path.read_bytes()
        path.write_bytes(before + b'drift')
        with self.assertRaisesRegex(InstallError, 'artifact hash/size drift'):
            b.npm_notice_inventory(self.dist)
        path.write_bytes(before)
        lock = b.load_json(self.dist / 'package-lock.json')
        lock['packages']['node_modules/' + b.PI_PACKAGE]['integrity'] = 'sha512-ZGVm'
        b.write_json(self.dist / 'package-lock.json', lock)
        with self.assertRaisesRegex(InstallError, 'lock integrity mismatch'):
            b.npm_notice_inventory(self.dist)


if __name__ == '__main__':
    unittest.main()
