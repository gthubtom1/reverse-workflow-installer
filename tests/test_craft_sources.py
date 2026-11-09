"""Owned source completeness and portable test transforms, without build/provider calls."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'scripts'))
import craft_sources as source
from configuration import encode_json
from versions import InstallError


class OwnedSourceTests(unittest.TestCase):
    def setUp(self):
        parent=REPO/'.local/tests'
        parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='owned-complete-',dir=parent)
        self.root=Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self):
        root=self.root/'source'
        data={'Cargo.toml':b'[package]\nname="craft-pi-bridge"\nversion="0.1.0"\n[[bin]]\nname="fake-pi"\npath="tests/fixtures/fake_pi.rs"\nrequired-features=["fixtures"]\n',
              'Cargo.lock':b'# inert test lock\n','src/lib.rs':b'// inert production code\n','tests/fixtures/fake_pi.rs':b'// inert peer\n',
              'tests/protocol.rs':b'// inert meaningful protocol test source\n','.gitignore':b'/target/\n',
              'README.md':b'Original local documentation','config.example.json':b'{"pi":{},"cancel":{}}'}
        for rel,content in data.items():
            p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content)
        hashes={p:source.sha(root/p) for p in data}
        import hashlib
        digest=hashlib.sha256(''.join(f'{p}\0{hashes[p]}\n' for p in sorted(hashes)).encode()).hexdigest()
        manifest=self.root/'original.json'
        manifest.write_bytes(encode_json({'source_tree_sha256':digest,'files':[{'path':p,'sha256':h} for p,h in hashes.items()]}))
        return root,manifest,digest

    def test_complete_source_keeps_all_tests_bins_and_original_production_bytes(self):
        root,manifest,digest=self.fixture()
        target=self.root/'packaged'
        value=source.snapshot(root,manifest,digest,'bridge',target)
        source.validate(target,'bridge')
        for rel in ('Cargo.toml','Cargo.lock','src/lib.rs','tests/fixtures/fake_pi.rs','tests/protocol.rs','.gitignore'):
            self.assertEqual((root/rel).read_bytes(),(target/rel).read_bytes())
        self.assertNotEqual(digest,value['packaged_source_tree_sha256'])
        self.assertTrue((target/'config.example.json').exists())
        (target/'tests/fixtures/fake_pi.rs').unlink()
        with self.assertRaisesRegex(InstallError,'source drift'):
            source.validate(target,'bridge')

    def test_declared_fixture_bin_missing_from_frozen_source_cannot_be_certified(self):
        root,manifest,digest=self.fixture()
        # Use a complete manifest of an intentionally broken Cargo source layout.
        (root/'Cargo.toml').write_text('[package]\nname="craft-pi-bridge"\nversion="0.1.0"\n[[bin]]\nname="missing"\npath="tests/fixtures/missing.rs"\n')
        doc=json.loads(manifest.read_text())
        for item in doc['files']:
            if item['path']=='Cargo.toml':item['sha256']=source.sha(root/'Cargo.toml')
        import hashlib
        doc['source_tree_sha256']=hashlib.sha256(''.join(f"{x['path']}\0{x['sha256']}\n" for x in sorted(doc['files'],key=lambda x:x['path'])).encode()).hexdigest()
        manifest.write_bytes(encode_json(doc))
        with self.assertRaisesRegex(InstallError,'fixture source missing'):
            source.snapshot(root,manifest,doc['source_tree_sha256'],'bridge',self.root/'packaged')

    def test_compiled_cargo_notices_bind_real_text_and_registry_archive_checksum(self):
        from craft_cargo_notices import collect
        registry=self.root/'registry'
        crate=registry/'src/test-index/fixture-dep-1.0.0'
        crate.mkdir(parents=True)
        (crate/'LICENSE').write_bytes((REPO/'LICENSE').read_bytes())
        archive=registry/'cache/test-index/fixture-dep-1.0.0.crate'
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b'inert locked archive fixture')
        digest=source.sha(archive)
        lock=self.root/'Cargo.lock'
        lock.write_text(f'[[package]]\nname="fixture-dep"\nversion="1.0.0"\nsource="registry+https://example.invalid/index"\nchecksum="{digest}"\n')
        package={'id':'fixture-dep-id','name':'fixture-dep','version':'1.0.0','source':'registry+https://example.invalid/index',
                 'manifest_path':str(crate/'Cargo.toml'),'license':'MIT'}
        unused={**package,'id':'unused-id','name':'unused','manifest_path':str(self.root/'missing-unused/Cargo.toml')}
        report=collect({'executor':{'packages':[package,unused]}},{package['id']},[lock],self.root/'notices',self.root)
        self.assertEqual(set(report),{'fixture-dep-1.0.0'})
        self.assertEqual(report['fixture-dep-1.0.0']['registry_archive_sha256'],digest)
        self.assertEqual((self.root/'notices/fixture-dep-1.0.0/LICENSE').read_bytes(),(REPO/'LICENSE').read_bytes())
        archive.write_bytes(b'archive drift')
        with self.assertRaisesRegex(InstallError,'checksum missing/mismatch'):
            collect({'executor':{'packages':[package]}},{package['id']},[lock],self.root/'bad-notices',self.root)

    def test_missing_compiled_grant_requires_explicit_nonpublishable_candidate_mode(self):
        from craft_cargo_notices import collect
        crate=self.root/'source/fixture';crate.mkdir(parents=True)
        package={'id':'fixture','name':'fixture','version':'1.0.0','source':None,'manifest_path':str(crate/'Cargo.toml'),'license':'0BSD'}
        with self.assertRaisesRegex(InstallError,'notice texts missing'):
            collect({'executor':{'packages':[package]}},{'fixture'},[],self.root/'notices',self.root/'source')
        report=collect({'executor':{'packages':[package]}},{'fixture'},[],self.root/'candidate-notices',self.root/'source',allow_missing=True)
        self.assertIn('publication-blocked',report['fixture-1.0.0']['status'])
        self.assertFalse(report['fixture-1.0.0']['notice_files'])
        self.assertEqual(report['fixture-1.0.0']['declared_license'],'0BSD')
        self.assertFalse((self.root/'candidate-notices/fixture-1.0.0/LICENSE').exists())

    def test_compiled_spdx_only_without_license_text_is_blocked(self):
        from craft_cargo_notices import collect
        crate=self.root/'source/fixture';crate.mkdir(parents=True)
        (crate/'LICENSE').write_text('MIT\n')
        package={'id':'fixture','name':'fixture','version':'1.0.0','source':None,'manifest_path':str(crate/'Cargo.toml'),'license':'MIT'}
        with self.assertRaisesRegex(InstallError,'missing/trivial'):
            collect({'executor':{'packages':[package]}},{'fixture'},[],self.root/'notices',self.root/'source')

    def test_portable_transforms_require_explicit_tools_and_never_change_production(self):
        driver=b'let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))\n            .join("target/fixtures");\nf.c.pi.program = PathBuf::from("Q:/machine/node.exe");'
        changed=source.transform('tests/protocol.rs',driver,'bridge').decode()
        self.assertIn('CRAFT_TEST_ROOT',changed)
        self.assertIn('CRAFT_TEST_NODE',changed)
        self.assertNotIn('Q:/',changed)
        executor=b'let p = Path::new(env!("CARGO_MANIFEST_DIR")).join("test-artifacts/result.json");\n'
        self.assertIn('join("result.json")',source.transform('tests/integration.rs',executor,'executor').decode())
        peer=b'let c=Command::new("Q:/machine/node.exe");'
        self.assertIn('CRAFT_TEST_NODE',source.transform('tests/fixtures/offline-pi-peer.rs',peer,'executor').decode())
        policy_fixture=source.transform('tests/integration.rs',b'    let p = AcceptedResearch {\ncommand: "cargo +stable-x86_64-pc-windows-gnu build --quiet --offline".into(),','executor').decode()
        peer_fixture=source.transform('tests/fixtures/fake-pi.cjs',b"command:'cargo +stable-x86_64-pc-windows-gnu build --quiet --offline'",'executor').decode()
        self.assertIn('portable-fixture-build.cmd',policy_fixture)
        self.assertIn('command: portable_command.clone()',policy_fixture)
        self.assertIn('portable-fixture-command.json',policy_fixture)
        self.assertIn('portable-fixture-command.json',peer_fixture)
        self.assertNotIn('cargo +stable',peer_fixture)
        python='"""historical helper"""\nfrom pathlib import Path\nNODE=Path("Q:/machine/node.exe")\n'
        fixed=source.portable_python(python)
        compile(fixed,'portable-helper','exec')
        self.assertIn('os.environ["CRAFT_TEST_NODE"]',fixed)


if __name__=='__main__':unittest.main()
