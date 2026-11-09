"""Exact accepted 0BSD adoption only; fixtures are raw public registry metadata."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import craft_cargo_notices as notices
from versions import InstallError


class Standard0BSDTests(unittest.TestCase):
    def setUp(self):
        parent = REPO / '.local/tests'
        parent.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='standard-0bsd-', dir=parent)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.crate = self.root / 'crate'
        shutil.copytree(REPO / 'tests/fixtures/cargo-0bsd', self.crate)
        self.evidence = self.root / 'standard'
        shutil.copytree(REPO / 'adapters/craft-pi/runtime/notices/cargo-standard-0bsd', self.evidence)
        self.source = json.loads((self.evidence / 'SOURCE.json').read_text())
        self.lock = self.source['recommended_narrow_exception_lock']
        self.pkg = {'name': 'yaxpeax-arm', 'version': '0.5.0', 'source': self.lock['registry_source'],
                    'license': '0BSD', 'id': 'fixture-id', 'manifest_path': str(self.crate / 'Cargo.toml')}

    def selected(self, pkg=None, checksum=None):
        return notices.standard_0bsd(pkg or self.pkg, self.crate,
                                     checksum or self.lock['registry_archive_sha256'], self.evidence)

    def test_exact_adoption_preserves_standard_and_provenance(self):
        text, source_file, association = self.selected()
        self.assertEqual(notices.sha(text), self.lock['standard_text_sha256'])
        self.assertIn(b'Copyright (C) YEAR by AUTHOR EMAIL', text.read_bytes())
        self.assertFalse(association['original_upstream_license_file_claimed'])
        self.assertFalse(association['author_copyright_notice_supplied'])
        self.assertEqual(notices.sha(source_file), notices.STANDARD_0BSD_SOURCE_SHA256)

    def test_registry_checksum_source_and_non0bsd_declaration_drift_deny(self):
        for key, value in [('source', 'registry+https://invalid.test/index'), ('license', 'MIT'), ('license', 'Apache-2.0')]:
            with self.subTest(field=key, value=value):
                pkg = {**self.pkg, key: value}
                with self.assertRaisesRegex(InstallError, 'identity drift'):
                    self.selected(pkg=pkg)
        with self.assertRaisesRegex(InstallError, 'identity drift'):
            self.selected(checksum='0' * 64)

    def test_both_metadata_hashes_and_source_commit_drift_deny(self):
        for name in ('Cargo.toml', 'Cargo.toml.orig', '.cargo_vcs_info.json'):
            with self.subTest(name=name):
                path = self.crate / name
                before = path.read_bytes()
                if name.endswith('.json'):
                    value = json.loads(before)
                    value['git']['sha1'] = '0' * 40
                    path.write_text(json.dumps(value))
                else:
                    path.write_bytes(before + b'\n# drift\n')
                with self.assertRaisesRegex(InstallError, 'identity drift'):
                    self.selected()
                path.write_bytes(before)

    def test_forged_author_or_changed_standard_text_deny(self):
        path = self.evidence / 'standard-0BSD.txt'
        path.write_bytes(path.read_bytes().replace(b'YEAR by AUTHOR EMAIL', b'2026 by Invented Author'))
        with self.assertRaisesRegex(InstallError, 'standard text drift'):
            self.selected()

    def test_whitelist_metadata_or_standard_commit_drift_deny(self):
        source = self.evidence / 'SOURCE.json'
        value = copy.deepcopy(self.source)
        value['recommended_narrow_exception_lock']['standard_commit'] = '0' * 40
        source.write_text(json.dumps(value))
        with self.assertRaisesRegex(InstallError, 'source evidence drift'):
            self.selected()

    def test_other_name_or_version_is_not_whitelisted(self):
        for delta in ({'name': 'other'}, {'version': '0.5.1'}):
            self.assertIsNone(self.selected(pkg={**self.pkg, **delta}))

    def test_metadata_only_mit_apache_or_unlisted_0bsd_remain_blocked(self):
        locks = self.root / 'Cargo.lock'
        locks.write_text('version = 4\n')
        for license_id in ('MIT', 'Apache-2.0', '0BSD'):
            pkg = {**self.pkg, 'source': None, 'name': 'unlisted', 'license': license_id}
            with self.subTest(license=license_id), self.assertRaisesRegex(InstallError, 'notice texts missing'):
                notices.collect({'fixture': {'packages': [pkg]}}, [pkg['id']], [locks],
                                self.root / 'output', self.root, standards=self.evidence)


if __name__ == '__main__':
    unittest.main()
