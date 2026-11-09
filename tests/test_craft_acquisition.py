"""Offline acquisition: structured GitHub metadata, real ZIP/files and bounded worker tests."""
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
sys.path.insert(0, str(REPO / 'tests'))
import acquire_craft as ac
import craft
from configuration import atomic, digest, encode_json, load_json
from versions import InstallError
from test_craft import toy_bundle, toy_reverse_contract

LOCAL = REPO / '.local/tests'
LOCAL.mkdir(parents=True, exist_ok=True)
REAL_STAGE_VALIDATOR = ac.validate_win32_stage


def archive_tree(root, destination, prefix=''):
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as output:
        for item in sorted(root.rglob('*')):
            if item.is_file() and '.git' not in item.relative_to(root).parts:
                output.writestr(prefix + item.relative_to(root).as_posix(), item.read_bytes())


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=LOCAL)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bundle = self.base / 'bundle'
        toy_bundle(self.bundle)
        self.source = self.base / 'reverse-source'
        toy_reverse_contract(self.source)
        atomic(self.source / '.github/workflows/test.yml', b'name: source workflow is allowed\n')
        atomic(self.source / 'README.md', b'public source\n')
        self.craft_zip = self.base / 'craft.zip'
        self.reverse_zip = self.base / 'reverse.zip'
        archive_tree(self.bundle, self.craft_zip)
        archive_tree(self.source, self.reverse_zip, 'reverse-skill-' + 'b' * 40 + '/')
        self.pin = {'schema_version': 1,
                    'craft': {'repository': ac.OWN, 'tag': 'craft-pi-v0.1.0', 'commit': 'a' * 40,
                              'asset': 'craft-pi-windows-x64.zip', 'asset_id': 37, 'sha256': ac.file_sha(self.craft_zip),
                              'manifest_sha256': ac.file_sha(self.bundle / craft.MANIFEST)},
                    'reverse': {'repository': ac.REVERSE, 'tag': 'v1.9.0', 'commit': 'b' * 40,
                                'archive_sha256': ac.file_sha(self.reverse_zip), 'descriptor_sha256': ac.file_sha(self.source / craft.REVERSE_DESCRIPTOR)},
                    'upstream': {'repository': ac.UPSTREAM, 'commit': craft.BASE_COMMIT}}
        # The publication patch worktree itself is deep; real extraction fixtures
        # use a short isolated cwd/.local stage, never an active/user root.
        short_parent = Path.cwd()/'.local'
        short_parent.mkdir(exist_ok=True)
        self.stage_temp = tempfile.TemporaryDirectory(prefix='a',dir=short_parent)
        self.addCleanup(self.stage_temp.cleanup)
        self.stage_base = Path(self.stage_temp.name)
        self.stage = self.stage_base / 's'
        self.downloads = []
        self.platform_patch = patch.object(ac, 'require_windows')
        self.platform_patch.start()
        self.addCleanup(self.platform_patch.stop)
        # Existing isolated unit roots are intentionally deep; test the public
        # budget separately rather than add a production bypass flag.
        self.budget_patch = patch.object(ac, 'validate_win32_stage')
        self.budget_patch.start()
        self.addCleanup(self.budget_patch.stop)
        self.git(['init', '-q'], self.source)
        atomic(self.source / '.gitattributes', b'*.ps1 text eol=crlf\n*.md text eol=lf\nVERSION text eol=lf\n*.json text eol=lf\n')
        atomic(self.source / 'route.ps1', b'Write-Output one\nWrite-Output two\n')
        atomic(self.source / 'binary.dat', b'\x00\xff\r\n\n\x00')
        self.git(['add', '.'], self.source)
        self.git(['-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','commit','-qm','fixture'], self.source)
        self.git(['tag', 'v1.9.0'], self.source)
        self.pin['reverse']['commit'] = self.git(['rev-parse','HEAD'],self.source).decode().strip()
        self.reverse_zip.write_bytes(self.git(['archive', '--format=zip',
            '--prefix=reverse-skill-' + self.pin['reverse']['commit'] + '/',
            self.pin['reverse']['commit']], self.source))
        self.pin['reverse']['archive_sha256'] = ac.file_sha(self.reverse_zip)

    def git(self, argv, root):
        result = subprocess.run(['git','-c','core.autocrlf=false','-C',str(root),*argv], env=ac.clean_env(self.base), capture_output=True, check=True)
        return result.stdout

    def fetch(self, url):
        key = 'craft' if 'reverse-workflow-installer' in url else 'reverse'
        record = self.pin[key]
        api = record['repository'].replace('https://github.com/', 'https://api.github.com/repos/')
        if url == api + '/commits/' + record['tag']:
            return {'sha': record['commit']}
        if url != api + '/releases/tags/' + record['tag']:
            raise AssertionError(url)
        result = {'id': 10 if key == 'craft' else 11, 'tag_name': record['tag'], 'draft': False, 'prerelease': False,
                  'html_url': record['repository'] + '/releases/tag/' + record['tag'], 'assets': []}
        if key == 'craft':
            result['assets'] = [{'name': record['asset'], 'id': record['asset_id'], 'digest': 'sha256:' + record['sha256'],
                                 'browser_download_url': record['repository'] + '/releases/download/' + record['tag'] + '/' + record['asset'],
                                 'url': api + '/releases/assets/' + str(record['asset_id'])}]
        return result

    def download(self, url, *, destination):
        self.downloads.append(url)
        source = self.craft_zip if '/releases/download/' in url else self.reverse_zip
        shutil.copyfile(source, destination)
        return ac.file_sha(destination)

    def checkout(self, record, target, stage):
        ac.git_checkout({**record, 'repository': str(self.source)}, target, stage)

    def acquire(self):
        return ac.acquire(self.pin, self.stage, fetch=self.fetch, download=self.download, checkout=self.checkout)

    def test_mixed_repository_positive_exact_paths_and_options(self):
        result = self.acquire()
        self.assertEqual(self.downloads, [ac.OWN + '/releases/download/craft-pi-v0.1.0/craft-pi-windows-x64.zip',
                                        'https://codeload.github.com/gthubtom1/reverse-skill/zip/' + self.pin['reverse']['commit']])
        options = load_json(self.stage / 'installer-options.json')
        self.assertEqual(options, ['--craft-bundle', str(self.stage / 'craft-archive'), '--reverse-root', str(self.stage / 'reverse')])
        self.assertEqual(result['reverse_contract'], craft.reverse_contract(self.stage / 'reverse'))
        self.assertEqual(craft.inventory(self.stage / 'craft-archive'), craft.inventory(self.bundle))
        self.assertTrue((self.stage / 'reverse/.github/workflows/test.yml').is_file())
        self.assertTrue((self.stage / 'acquisition-candidate.json').is_file())
        self.assertFalse((self.stage / 'complete.json').exists())  # Only verified supervisor can complete.

    def test_template_unknown_schema_duplicate_fields_no_download(self):
        for change in (lambda p: p.update(schema_version=2), lambda p: p.update(schema_version=True),
                       lambda p: p['craft'].update(commit=''), lambda p: p['craft'].update(sha256=None),
                       lambda p: p['craft'].update(repository=ac.UPSTREAM), lambda p: p['reverse'].update(repository=ac.OWN),
                       lambda p: p['upstream'].update(commit='f' * 40), lambda p: p.update(unknown=1),
                       lambda p: p['craft'].update(asset='../bad.zip'), lambda p: p['craft'].update(asset_id=True)):
            pin = copy.deepcopy(self.pin)
            change(pin)
            with self.subTest(pin=pin), self.assertRaises(InstallError):
                ac.validate_pin(pin)
        with self.assertRaisesRegex(InstallError, 'duplicate'):
            ac.strict_json('{"schema_version":1,"schema_version":1}')
        self.assertEqual(self.downloads, [])

    def test_wrong_tag_commit_draft_prerelease_repo_asset_id_url_hash_refused(self):
        for mutation in ('commit', 'draft', 'prerelease', 'repo', 'missing', 'duplicate', 'asset-id', 'asset-url', 'api-url', 'digest', 'assets-null', 'assets-item'):
            def bad(url):
                value = self.fetch(url)
                if 'reverse-workflow-installer' not in url:
                    return value
                if '/commits/' in url:
                    if mutation == 'commit': value['sha'] = 'f' * 40
                elif mutation in ('draft', 'prerelease'): value[mutation] = True
                elif mutation == 'repo': value['html_url'] = ac.UPSTREAM + '/releases/tag/craft-pi-v0.1.0'
                elif mutation == 'missing': value['assets'] = []
                elif mutation == 'duplicate': value['assets'].append(copy.deepcopy(value['assets'][0]))
                elif mutation == 'assets-null': value['assets'] = None
                elif mutation == 'assets-item': value['assets'] = ['bad-object']
                else:
                    field = {'asset-id':'id','asset-url':'browser_download_url','api-url':'url','digest':'digest'}.get(mutation)
                    if field: value['assets'][0][field] = 'wrong'
                return value
            with self.subTest(mutation=mutation), self.assertRaises(InstallError):
                ac.acquire(self.pin, self.stage, fetch=bad, download=self.download, checkout=self.checkout)
            self.assertFalse(self.stage.exists())
        self.assertEqual(self.downloads, [])

    def test_reverse_release_commit_mismatch_rejected(self):
        def bad(url):
            return {'sha':'f' * 40} if 'reverse-skill/commits/' in url else self.fetch(url)
        with self.assertRaisesRegex(InstallError, 'moved tag'):
            ac.acquire(self.pin, self.stage, fetch=bad, download=self.download, checkout=self.checkout)
        self.assertFalse(self.stage.exists())

    def test_archive_tamper_and_partial_failure_never_complete(self):
        def broken(url, *, destination):
            atomic(destination, b'partial bytes')
        with self.assertRaisesRegex(InstallError, 'archive SHA256'):
            ac.acquire(self.pin, self.stage, fetch=self.fetch, download=broken, checkout=self.checkout)
        self.assertFalse((self.stage / 'complete.json').exists())
        self.assertFalse((self.stage / 'installer-options.json').exists())
        self.assertTrue(self.bundle.is_dir())

    def test_archive_escape_symlink_casecollision_credentials_rejected(self):
        cases = [('escape','../escaped.txt'), ('absolute','/absolute.txt'), ('credentials','auth.json'), ('case','FILE.txt'), ('symlink','linked')]
        for kind, name in cases:
            path = self.base / (kind + '.zip')
            with zipfile.ZipFile(path,'w') as out:
                if kind == 'case': out.writestr('file.txt', b'one')
                item = zipfile.ZipInfo(name)
                if kind == 'symlink': item.external_attr = 0o120777 << 16
                out.writestr(item, b'bad')
            with self.subTest(kind=kind), self.assertRaises(InstallError):
                ac.safe_extract_zip(path,self.base / ('extracted-' + kind))
            self.assertFalse((self.base / ('extracted-' + kind)).exists())
        self.assertFalse((self.base / 'escaped.txt').exists())

    def test_old_reverse_and_descriptor_hash_mismatch_never_complete(self):
        for version in ('1.8.2','1.9.0'):
            atomic(self.source / 'VERSION',(version+'\n').encode())
            archive_tree(self.source,self.reverse_zip,'reverse-skill-'+self.pin['reverse']['commit']+'/')
            self.pin['reverse']['archive_sha256'] = ac.file_sha(self.reverse_zip)
            if version == '1.9.0': self.pin['reverse']['descriptor_sha256'] = 'e'*64
            self.stage = self.stage_base / version
            with self.assertRaises(InstallError): self.acquire()
            self.assertFalse((self.stage/'complete.json').exists())

    def test_manifest_hash_or_checkout_content_mismatch_rejected(self):
        self.pin['craft']['manifest_sha256']='e'*64
        with self.assertRaisesRegex(InstallError,'manifest SHA256'): self.acquire()
        self.stage=self.stage_base/'second'
        self.pin['craft']['manifest_sha256']=ac.file_sha(self.bundle/craft.MANIFEST)
        def drift(record,target,stage):
            self.checkout(record,target,stage)
            atomic(target/'README.md',b'changed after download')
        with self.assertRaisesRegex(InstallError,'dirty|canonical.*differ'):
            ac.acquire(self.pin,self.stage,fetch=self.fetch,download=self.download,checkout=drift)
        self.assertFalse((self.stage/'complete.json').exists())

    def test_moved_release_during_download_rejected(self):
        counts={}
        def moved(url):
            counts[url]=counts.get(url,0)+1
            value=self.fetch(url)
            if counts[url]>1 and '/releases/tags/' in url: value['id']+=1
            return value
        with self.assertRaisesRegex(InstallError,'metadata changed'):
            ac.acquire(self.pin,self.stage,fetch=moved,download=self.download,checkout=self.checkout)
        self.assertFalse((self.stage/'complete.json').exists())

    def test_fresh_stage_never_overwrites_user_root(self):
        self.stage.mkdir()
        atomic(self.stage/'user.txt',b'keep')
        with self.assertRaisesRegex(InstallError,'fresh'): self.acquire()
        self.assertEqual((self.stage/'user.txt').read_bytes(),b'keep')
        self.assertEqual(self.downloads,[])

    def test_https_redirect_hosts_no_auth_forward_and_byte_budget(self):
        from urllib.request import Request
        redirect=ac.Redirects({'github.com','release-assets.githubusercontent.com'})
        req=Request(ac.OWN+'/releases/download/tag/a.zip',headers={'Authorization':'secret','Cookie':'secret'})
        redirected=redirect.redirect_request(req,None,302,'',{},'https://release-assets.githubusercontent.com/github-production-release-asset/a?token=public-signed')
        self.assertIsNone(redirected.get_header('Authorization'))
        self.assertIsNone(redirected.get_header('Cookie'))
        for url in ('http://release-assets.githubusercontent.com/a','https://evil.example/a','https://github.com@evil.example/a','https://github.com:444/a', ac.UPSTREAM + '/releases/download/tag/a.zip'):
            with self.assertRaises(InstallError): redirect.redirect_request(req,None,302,'',{},url)
        class Response(io.BytesIO):
            status=200
            def geturl(self): return 'https://release-assets.githubusercontent.com/a'
        class Opener:
            def open(self,request,timeout): return Response(b'abcdef')
        with self.assertRaisesRegex(InstallError,'byte budget'):
            ac.transfer(ac.OWN+'/releases/download/tag/a.zip',destination=self.base/'bytes.zip',limit=3,opener=Opener())

    def test_supervisor_unknown_cleanup_no_completion_and_total_timeout(self):
        observed={'returncode':0,'timed_out':False,'cleanup':'unknown','had_descendants':False,'scope':'fixture','stdout':'{}','stderr':''}
        with patch.object(ac,'run_owned',return_value=observed), patch('sys.stderr',new_callable=io.StringIO):
            self.assertEqual(ac.main(['--pin',json.dumps(self.pin),'--stage',str(self.stage),'--deadline-seconds','1']),1)
        self.assertFalse((self.stage/'complete.json').exists())
        started=time.monotonic()
        result=ac.run_owned([sys.executable,'-B','-c','import time; time.sleep(30)'],cwd=self.base,timeout=0.2,cleanup_seconds=2)
        self.assertTrue(result['timed_out'])
        self.assertEqual(result['cleanup'],'verified')
        self.assertLess(time.monotonic()-started,5)

    def test_git_checkout_exact_tag_commit_clean_state_and_no_hooks(self):
        calls=[]
        record=self.pin['reverse']
        def inherited(command,**kwargs):
            calls.append((command,kwargs))
            out=record['commit'] if command[-2:]==['rev-parse','HEAD'] else ''
            return subprocess.CompletedProcess(command,0,stdout=out.encode(),stderr=b'')
        with patch.object(ac.subprocess,'run',side_effect=inherited):
            ac.git_checkout(record,self.base/'git-target',self.base)
        self.assertIn('--no-recurse-submodules',calls[0][0])
        self.assertEqual(calls[0][0][-2],ac.REVERSE)
        self.assertEqual(calls[0][1]['env']['GIT_CONFIG_GLOBAL'],ac.os.devnull)
        self.assertNotIn('GH_TOKEN',calls[0][1]['env'])
        clone, kwargs = calls[0]
        self.assertEqual(clone.count('http.version=HTTP/1.1'),1)
        self.assertEqual(clone[clone.index('http.version=HTTP/1.1')-1],'-c')
        self.assertFalse(any('http.version=' in arg for cmd,_ in calls[1:] for arg in cmd))
        self.assertNotIn('--global',clone)
        self.assertNotIn('-k',clone)
        self.assertFalse(any('sslverify' in arg.casefold() or 'extraheader' in arg.casefold() or 'authorization' in arg.casefold() for arg in clone))
        for name in ('GITHUB_TOKEN','GIT_SSL_NO_VERIFY','GIT_CONFIG_COUNT'):
            self.assertNotIn(name,kwargs['env'])
        self.assertNotIn('start_new_session',kwargs)
        self.assertNotIn('creationflags',kwargs)
        def wrong(command,**kwargs):
            value=inherited(command,**kwargs)
            if command[-2:]==['rev-parse','HEAD']: value.stdout=b'f'*40
            return value
        with patch.object(ac.subprocess,'run',side_effect=wrong),self.assertRaisesRegex(InstallError,'tag commit drift'):
            ac.git_checkout(record,self.base/'git-target',self.base)
        def dirty(command,**kwargs):
            value=inherited(command,**kwargs)
            if 'status' in command: value.stdout=b'?? user-file'
            return value
        with patch.object(ac.subprocess,'run',side_effect=dirty),self.assertRaisesRegex(InstallError,'dirty'):
            ac.git_checkout(record,self.base/'git-target',self.base)

    def test_continuous_local_http_stream_cannot_evade_owned_total_deadline(self):
        # Child owns a local-only server and a read with a 20s socket timeout.
        # Continuous data prevents socket timeout; the outer deadline must stop it.
        code='''import http.server,threading,time,urllib.request
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  self.send_response(200);self.end_headers()
  for i in range(1000):
   self.wfile.write(b'x');self.wfile.flush();time.sleep(.01)
server=http.server.HTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
with urllib.request.urlopen('http://127.0.0.1:%s/'%server.server_port,timeout=20) as response:
 response.read()
'''
        started=time.monotonic()
        value=ac.run_owned([sys.executable,'-B','-c',code],cwd=self.base,timeout=.4,cleanup_seconds=2)
        self.assertTrue(value['timed_out'])
        self.assertEqual(value['cleanup'],'verified')
        self.assertLess(time.monotonic()-started,5)
        self.assertFalse((self.stage/'complete.json').exists())

    def test_template_cli_fails_before_network_and_wrong_archive_prefix(self):
        template=REPO/'adapters/craft-pi/releases/windows-x64.json.example'
        with patch.object(ac,'run_owned',side_effect=AssertionError('must not spawn')),patch('sys.stderr',new_callable=io.StringIO):
            self.assertEqual(ac.main(['--pin-file',str(template),'--stage',str(self.stage)]),1)
        archive_tree(self.source,self.reverse_zip,'reverse-skill-wrong/')
        self.pin['reverse']['archive_sha256']=ac.file_sha(self.reverse_zip)
        with self.assertRaisesRegex(InstallError,'exact commit project prefix'):
            self.acquire()
        self.assertFalse((self.stage/'complete.json').exists())

    def test_real_gitattributes_archive_export_and_canonical_blobs_remain_distinct(self):
        result = self.acquire()
        checkout = self.stage / 'reverse'
        raw = (checkout / 'route.ps1').read_bytes()
        canonical = self.git(['show','HEAD:route.ps1'],checkout)
        self.assertEqual(raw.count(b'\r\n'), 2)
        self.assertEqual(canonical.count(b'\r\n'), 0)
        self.assertEqual(canonical.count(b'\n'), 2)
        self.assertEqual(result['reverse_canonical_files']['route.ps1'], digest(canonical))
        self.assertEqual(result['reverse_files']['route.ps1'], digest(raw))
        with zipfile.ZipFile(self.reverse_zip) as archive:
            exported = archive.read('reverse-skill-' + self.pin['reverse']['commit'] + '/route.ps1')
        self.assertEqual(exported, raw)  # Native git archive honors eol=crlf too.
        self.assertEqual(result['reverse_archive_files']['route.ps1'], digest(exported))
        self.assertEqual(result['reverse_archive_files']['binary.dat'], digest(b'\x00\xff\r\n\n\x00'))
        self.assertNotEqual(result['reverse_files']['route.ps1'], result['reverse_canonical_files']['route.ps1'])
        self.assertEqual((checkout/'binary.dat').read_bytes(), b'\x00\xff\r\n\n\x00')
        atomic(checkout/'untracked.txt', b'extra')
        with self.assertRaisesRegex(InstallError,'dirty'):
            ac.canonical_files(checkout,self.pin['reverse']['commit'])

    def test_canonical_archive_mismatch_is_not_ignored(self):
        original = self.checkout
        def copied(record,target,stage):
            original(record,target,stage)
            # Commit clean extra source: still cannot substitute a different commit.
            self.git(['add','.'],target)
        atomic(self.source/'README.md',b'archive tampered but pin resealed')
        archive_tree(self.source,self.reverse_zip,'reverse-skill-'+self.pin['reverse']['commit']+'/')
        self.pin['reverse']['archive_sha256']=ac.file_sha(self.reverse_zip)
        with self.assertRaisesRegex(InstallError,'Git archive differs'):
            ac.acquire(self.pin,self.stage,fetch=self.fetch,download=self.download,checkout=copied)
        self.assertFalse((self.stage/'complete.json').exists())

    def test_nonwindows_cli_and_worker_are_unsupported_without_any_spawn(self):
        self.platform_patch.stop()
        try:
            with patch.object(ac.craft,'host',return_value={'os':'linux','arch':'x86_64'}),patch.object(ac,'run_owned',side_effect=AssertionError('no spawn')),patch.object(ac.subprocess,'run',side_effect=AssertionError('no git')),patch.object(ac,'resolve_pin',side_effect=AssertionError('no network')):
                with patch('sys.stderr',new_callable=io.StringIO) as errors:
                    self.assertEqual(ac.main(['--pin',json.dumps(self.pin),'--stage',str(self.stage)]),1)
                    self.assertEqual(json.loads(errors.getvalue())['code'],'unsupported-platform')
                with self.assertRaisesRegex(InstallError,'unsupported-platform'):
                    self.acquire()
            self.assertFalse(self.stage.exists())
        finally:
            self.platform_patch.start()

    @unittest.skipUnless(ac.os.name == 'nt', 'real outer Windows Job required')
    def test_outer_job_timeout_contains_inherited_git_and_descendant(self):
        # Slow real git alias starts a child which owns a loopback listener.
        # git_command uses subprocess.run with no new session/group/Job.
        import socket
        ready = self.base/'listener-ready.json'
        sleeper = self.base/'listen.py'
        atomic(sleeper, ("import socket,json,time,os\nfrom pathlib import Path\ns=socket.socket();s.bind(('127.0.0.1',0));s.listen()\nPath("+repr(str(ready))+").write_text(json.dumps({'port':s.getsockname()[1],'pid':os.getpid()}))\ntime.sleep(30)\n").encode())
        code = "import sys;from pathlib import Path;sys.path.insert(0,"+repr(str(REPO/'scripts'))+");import acquire_craft as a; a.git_command(['git','-c',"+repr('alias.wait=!"'+sys.executable+'" "'+str(sleeper)+'"')+",'wait'],stage=Path("+repr(str(self.base))+"))"
        observed = ac.run_owned([sys.executable,'-B','-c',code],cwd=self.base,timeout=3,cleanup_seconds=3)
        self.assertTrue(ready.is_file(), observed)
        port = load_json(ready)['port']
        self.assertTrue(observed['timed_out'])
        self.assertEqual(observed['cleanup'],'verified')
        with socket.socket() as probe:
            probe.settimeout(.3)
            self.assertNotEqual(probe.connect_ex(('127.0.0.1',port)),0)
        self.assertFalse((self.stage/'complete.json').exists())

    def test_public_long_stage_rejects_before_network_process_or_stage_write(self):
        self.budget_patch.stop()
        try:
            long_stage = self.base / 'pub-craft-072'
            with patch.object(ac,'run_owned',side_effect=AssertionError('no process')),patch.object(ac,'resolve_pin',side_effect=AssertionError('no network')),patch.object(ac,'atomic',side_effect=AssertionError('no write')),patch('sys.stderr',new_callable=io.StringIO) as errors:
                self.assertEqual(ac.main(['--pin',json.dumps(self.pin),'--stage',str(long_stage)]),1)
                error = json.loads(errors.getvalue())
                self.assertEqual(error['code'],'stage-path-too-long')
                self.assertIn('D:/cw/craft',error['error'])
                self.assertNotIn(str(self.base),error['error'])
            self.assertFalse(long_stage.exists())
            self.assertFalse((long_stage/'complete.json').exists())
        finally:
            self.budget_patch.start()

    def test_stage_budget_counts_emoji_as_two_utf16_units(self):
        root = Path(self.base.anchor) / ('a' * (64-len(self.base.anchor)))
        self.assertEqual(len(str(root).encode('utf-16-le'))//2,64)
        REAL_STAGE_VALIDATOR(root,self.pin)
        with self.assertRaisesRegex(InstallError,'UTF16=65/64'):
            REAL_STAGE_VALIDATOR(Path(str(root)[:-1]+'😀'),self.pin)

    def test_zip_actual_targets_are_checked_before_extraction(self):
        short = Path(self.base.anchor) / 'cw/craft'
        archive = self.base/'new-long-member.zip'
        with zipfile.ZipFile(archive,'w') as output:
            output.writestr('reverse-skill-'+'b'*40+'/'+'nested/'*25+'file.txt',b'x')
        with self.assertRaisesRegex(InstallError,'stage-path-too-long'):
            REAL_STAGE_VALIDATOR(short,self.pin,archive=archive,kind='reverse')
        self.assertFalse((short/'reverse-archive').exists())
        self.reverse_zip.write_bytes(archive.read_bytes())
        self.pin['reverse']['archive_sha256']=ac.file_sha(self.reverse_zip)
        validated = []
        def member_budget(stage, pin, *, archive=None, kind=None):
            # Isolate actual ZIP-member validation from the runner's checkout
            # length. The public root gate has its own no-side-effect test.
            self.assertIsNotNone(archive)
            validated.append(kind)
            return REAL_STAGE_VALIDATOR(short, pin, archive=archive, kind=kind)
        with patch.object(ac, 'validate_win32_stage', side_effect=member_budget), patch.object(ac,'safe_extract_zip',wraps=ac.safe_extract_zip) as extract, self.assertRaisesRegex(InstallError,'stage-path-too-long'):
            self.acquire()
        self.assertEqual(validated, ['craft', 'reverse'])
        self.assertEqual(extract.call_count,1)  # Craft only; reverse never extracts.
        self.assertFalse((self.stage/'reverse-archive').exists())
        self.assertFalse((self.stage/'complete.json').exists())

    def test_short_public_cli_with_real_validator_completes_offline(self):
        short_parent = Path.cwd()/'.local'
        short_parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='a',dir=short_parent) as parent:
            stage=Path(parent)/'s'
            if len(str(stage).encode('utf-16-le'))//2>64:
                self.skipTest('short local test root unavailable in this checkout')
            self.stage=stage
            self.budget_patch.stop()
            try:
                def worker(command,**kwargs):
                    value=self.acquire()
                    return {'returncode':0,'timed_out':False,'cleanup':'verified','had_descendants':False,'scope':'fixture','stdout':json.dumps(value),'stderr':''}
                with patch.object(ac,'run_owned',side_effect=worker),patch('sys.stdout',new_callable=io.StringIO):
                    self.assertEqual(ac.main(['--pin',json.dumps(self.pin),'--stage',str(stage)]),0)
                self.assertTrue((stage/'complete.json').is_file())
                self.assertEqual(load_json(stage/'complete.json')['reverse_contract'],craft.reverse_contract(stage/'reverse'))
            finally:
                self.budget_patch.start()

    def test_supervisor_publishes_completion_only_after_verified_result(self):
        kwargs_seen={}
        def worker(command,**kwargs):
            kwargs_seen.update(kwargs)
            value=self.acquire()
            return {'returncode':0,'timed_out':False,'cleanup':'verified','had_descendants':False,'scope':'fixture','stdout':json.dumps(value),'stderr':''}
        with patch.object(ac,'run_owned',side_effect=worker),patch('sys.stdout',new_callable=io.StringIO):
            self.assertEqual(ac.main(['--pin',json.dumps(self.pin),'--stage',str(self.stage)]),0)
            self.assertEqual(kwargs_seen['timeout'] + kwargs_seen['cleanup_seconds'], 600)
        self.assertEqual(load_json(self.stage/'complete.json')['supervision']['cleanup'],'verified')


if __name__=='__main__': unittest.main()
