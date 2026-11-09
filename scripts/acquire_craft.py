#!/usr/bin/env python3
"""Acquire one pinned owned Craft release and qualified reverse source; never install."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import tempfile
import sys
import urllib.request
import zipfile
from urllib.parse import urlparse, quote

import craft
from configuration import atomic, digest, encode_json, load_json
from versions import InstallError
from packaging_process import run_owned
from build_craft_bundle import safe_extract_zip

OWN = 'https://github.com/gthubtom1/reverse-workflow-installer'
REVERSE = 'https://github.com/gthubtom1/reverse-skill'
UPSTREAM = 'https://github.com/storytold/craft-anything'
LIMIT = 2 * 1024**3
STAGE_ROOT_UNITS = 64  # Current pinned releases; actual ZIP members are checked too.


def validate_win32_stage(stage, pin, *, archive=None, kind=None):
    """Read-only portable Win32 budget, before public acquisition or extraction."""
    stage = Path(stage).absolute()
    units = lambda value: len(str(value).encode('utf-16-le')) // 2
    count = units(stage)
    if count > STAGE_ROOT_UNITS:
        raise InstallError(f'stage-path-too-long: 选择短根如 D:/cw/craft; root UTF16={count}/64')
    targets = [stage / 'reverse/.git/objects/pack' / ('pack-' + '0'*40 + '.idx.lock'),
               stage / 'acquisition-candidate.json', stage / 'installer-options.json']
    if archive is not None:
        with zipfile.ZipFile(archive) as zipped:
            targets += [stage / (kind + '-archive') / craft.relative(item.filename.rstrip('/')) /
                        ('_' if item.is_dir() else '') for item in zipped.infolist()]
    for target in targets:
        parent = units(target.parent)
        if units(target) > 259 or parent > 247 or parent + 25 > 259 or any(units(p) > 255 for p in target.parts):
            raise InstallError(f'stage-path-too-long: 选择短根如 D:/cw/craft; target UTF16={units(target)}/259, '
                               f'parent={parent}/247, atomic-temp={parent + 25}/259')



def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InstallError('duplicate JSON field: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise InstallError('unsupported pin schema/fields')


def hex_value(value, length):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{%d}' % length, value):
        raise InstallError('published exact commit/SHA256 required; template is not downloadable')


def validate_pin(pin):
    fields(pin, 'schema_version craft reverse upstream')
    if type(pin['schema_version']) is not int or pin['schema_version'] != 1:
        raise InstallError('unsupported pin schema')
    asset, reverse, upstream = (pin[k] for k in ('craft', 'reverse', 'upstream'))
    fields(asset, 'repository tag commit asset asset_id sha256 manifest_sha256')
    fields(reverse, 'repository tag commit archive_sha256 descriptor_sha256')
    fields(upstream, 'repository commit')
    if asset['repository'] != OWN or asset['tag'] != 'craft-pi-v0.1.0' or reverse['repository'] != REVERSE or reverse['tag'] != 'v1.9.0' or upstream != {'repository': UPSTREAM, 'commit': craft.BASE_COMMIT}:
        raise InstallError('pin repository/tag/provenance mismatch')
    for value in (asset['commit'], reverse['commit']):
        hex_value(value, 40)
    for value in (asset['sha256'], asset['manifest_sha256'], reverse['archive_sha256'], reverse['descriptor_sha256']):
        hex_value(value, 64)
    if not isinstance(asset['asset'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*\.zip', asset['asset']) or type(asset['asset_id']) is not int or asset['asset_id'] <= 0:
        raise InstallError('published asset name/id required')
    return pin


def allowed_url(url, hosts):
    value = urlparse(url)
    if value.scheme != 'https' or value.hostname not in hosts or value.username or value.password or value.port not in (None, 443) or value.fragment:
        raise InstallError('download origin/redirect outside allowed HTTPS hosts')
    return url


class Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed_url(newurl, self.hosts)
        if urlparse(newurl).hostname in {'github.com', 'api.github.com', 'codeload.github.com'} and newurl != req.full_url:
            raise InstallError('redirect changes pinned repository/API/archive path')
        # Reconstruct public request; never forward Authorization/cookies to storage.
        return urllib.request.Request(newurl, headers={'User-Agent': 'reverse-workflow-installer', 'Accept': req.get_header('Accept', '*/*')})


def transfer(url, *, destination=None, limit=LIMIT, opener=None):
    hosts = {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'} if url.startswith(OWN + '/releases/download/') else ({'codeload.github.com'} if url.startswith('https://codeload.github.com/') else {'api.github.com'})
    allowed_url(url, hosts)
    opener = opener or urllib.request.build_opener(Redirects(hosts))
    request = urllib.request.Request(url, headers={'User-Agent': 'reverse-workflow-installer', 'Accept': 'application/json' if destination is None else 'application/octet-stream'})
    with opener.open(request, timeout=20) as response:
        allowed_url(response.geturl(), hosts)
        if urlparse(response.geturl()).hostname in {'github.com', 'api.github.com', 'codeload.github.com'} and response.geturl() != url:
            raise InstallError('response changes pinned repository path')
        if response.status != 200:
            raise InstallError('public download did not return HTTP 200')
        total, chunks = 0, []
        out = Path(destination).open('xb') if destination else None
        try:
            while True:
                data = response.read(1024 * 1024)
                if not data:
                    break
                total += len(data)
                if total > limit:
                    raise InstallError('download byte budget exceeded')
                if out:
                    out.write(data)
                else:
                    chunks.append(data)
        finally:
            if out:
                out.close()
    return strict_json(b''.join(chunks).decode('utf-8')) if destination is None else file_sha(destination)


def file_sha(path):
    hashed = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            hashed.update(data)
    return hashed.hexdigest()


def resolve_pin(pin, fetch=None):
    validate_pin(pin)
    fetch = fetch or (lambda url: transfer(url, limit=4 * 1024**2))
    resolved = {}
    for key in ('craft', 'reverse'):
        record = pin[key]
        api = record['repository'].replace('https://github.com/', 'https://api.github.com/repos/')
        commit = fetch(api + '/commits/' + quote(record['tag'], safe=''))
        release = fetch(api + '/releases/tags/' + quote(record['tag'], safe=''))
        if not isinstance(commit, dict) or not isinstance(release, dict) or commit.get('sha') != record['commit'] or release.get('tag_name') != record['tag'] or release.get('draft') is not False or release.get('prerelease') is not False or release.get('html_url') != record['repository'] + '/releases/tag/' + record['tag'] or type(release.get('id')) is not int:
            raise InstallError('moved tag, wrong repository or unsupported release')
        resolved[key] = {'release_id': release['id'], 'commit': commit['sha']}
        if key == 'craft':
            values = release.get('assets')
            if not isinstance(values, list) or not all(isinstance(a, dict) for a in values):
                raise InstallError('release asset metadata must be an array of objects')
            assets = [a for a in values if a.get('name') == record['asset']]
            url = record['repository'] + '/releases/download/' + record['tag'] + '/' + record['asset']
            if len(assets) != 1 or assets[0].get('id') != record['asset_id'] or assets[0].get('browser_download_url') != url or assets[0].get('url') != api + '/releases/assets/' + str(record['asset_id']) or assets[0].get('digest') != 'sha256:' + record['sha256']:
                raise InstallError('release asset URL/id/SHA256 missing or mismatched')
            resolved[key].update(url=url, asset_id=record['asset_id'], sha256=record['sha256'])
    resolved['reverse']['url'] = 'https://codeload.github.com/gthubtom1/reverse-skill/zip/' + pin['reverse']['commit']
    return resolved


def clean_env(stage):
    env = {k: v for k, v in os.environ.items() if k in ('PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'PATHEXT')}
    env.update(HOME=str(stage / 'home'), USERPROFILE=str(stage / 'home'), GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0')
    return env


def require_windows():
    if os.name != 'nt' or craft.host() != {'os': 'windows', 'arch': 'x86_64'}:
        raise InstallError('unsupported-platform: Craft release acquisition requires Windows x64')


def git_command(command, *, stage, input=None, stdout=subprocess.PIPE):
    """Git inherits the acquisition worker's outer Windows Job; never starts a session."""
    try:
        result = subprocess.run(command, cwd=stage, env=clean_env(stage), input=input,
                                stdout=stdout, stderr=subprocess.PIPE, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise InstallError('reverse Git failed/timed out; outer Job must confirm cleanup') from error
    if result.returncode:
        raise InstallError('reverse Git acquisition command failed')
    return result.stdout


def git_checkout(record, target, stage):
    commands = [['git', '-c', 'core.autocrlf=false', '-c', 'http.followRedirects=false', '-c', 'http.version=HTTP/1.1', '-c', 'core.hooksPath=' + str(stage / 'empty-hooks'), 'clone', '--no-recurse-submodules', '--single-branch', '--depth', '1', '--branch', record['tag'], record['repository'], str(target)],
                ['git', '-C', str(target), 'rev-parse', 'HEAD'], ['git', '-C', str(target), 'status', '--porcelain', '--untracked-files=all']]
    for index, command in enumerate(commands):
        output = git_command(command, stage=stage).decode('utf-8').strip()
        if index == 1 and output != record['commit']:
            raise InstallError('reverse Git tag commit drift')
        if index == 2 and output:
            raise InstallError('reverse acquired checkout is dirty')


def canonical_files(root, commit):
    """Hash exact Git blobs in one batch; never normalize text or binary checkout bytes."""
    stage = root.parent
    base = ['git', '-C', str(root)]
    if git_command(base + ['rev-parse', 'HEAD'], stage=stage).decode().strip() != commit:
        raise InstallError('reverse Git tag commit drift')
    if git_command(base + ['status', '--porcelain', '--untracked-files=all'], stage=stage).strip():
        raise InstallError('reverse acquired checkout is dirty')
    entries, seen = [], set()
    for row in git_command(base + ['ls-tree', '-r', '-z', commit], stage=stage).split(b'\0'):
        if not row:
            continue
        header, raw_name = row.split(b'\t', 1)
        mode, kind, oid = header.decode('ascii').split()
        name = craft.relative(raw_name.decode('utf-8'))
        if mode not in ('100644', '100755') or kind != 'blob' or name.casefold() in seen or not re.fullmatch('[0-9a-f]{40}', oid):
            raise InstallError('unsafe/duplicate canonical Git tree entry')
        seen.add(name.casefold())
        entries.append((name, oid))
    actual = checkout_files(root)
    if not entries or set(actual) != {name for name, _ in entries}:
        raise InstallError('reverse checkout has missing/extra source files')
    result, total = {}, 0
    with tempfile.TemporaryFile(dir=stage) as blobs:
        git_command(base + ['cat-file', '--batch'], stage=stage,
                    input=''.join(oid + '\n' for _, oid in entries).encode('ascii'), stdout=blobs)
        blobs.seek(0)
        for name, oid in entries:
            header = blobs.readline(200).decode('ascii').strip().split()
            if len(header) != 3 or header[:2] != [oid, 'blob'] or not header[2].isdigit():
                raise InstallError('canonical Git blob response mismatch')
            size = int(header[2])
            total += size
            if total > LIMIT:
                raise InstallError('canonical Git source exceeds byte budget')
            hashed = hashlib.sha256()
            while size:
                chunk = blobs.read(min(size, 1024 * 1024))
                if not chunk:
                    raise InstallError('truncated canonical Git blob')
                hashed.update(chunk)
                size -= len(chunk)
            if blobs.read(1) != b'\n':
                raise InstallError('canonical Git blob framing mismatch')
            result[name] = hashed.hexdigest()
        if blobs.read(1):
            raise InstallError('unexpected canonical Git blob output')
    return result


def git_archive_files(root, commit, canonical):
    """Hash Git's actual export bytes; attributes may differ from canonical blobs."""
    stage = root.parent
    result, total = {}, 0
    with tempfile.TemporaryFile(dir=stage) as archive:
        git_command(['git', '-c', 'core.autocrlf=false', '-C', str(root),
                     'archive', '--format=zip', commit], stage=stage, stdout=archive)
        archive.seek(0)
        with zipfile.ZipFile(archive) as exported:
            for item in exported.infolist():
                if item.is_dir():
                    continue
                name = craft.relative(item.filename)
                if name not in canonical or name in result:
                    raise InstallError('unexpected/duplicate reverse Git archive path')
                total += item.file_size
                if total > LIMIT:
                    raise InstallError('reverse Git archive exceeds byte budget')
                hashed = hashlib.sha256()
                with exported.open(item) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        hashed.update(chunk)
                result[name] = hashed.hexdigest()
    if set(result) != set(canonical):
        raise InstallError('reverse Git archive has missing source paths')
    return result


def checkout_files(root):
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        if Path(directory) == root and '.git' in dirs:
            dirs.remove('.git')
        for name in dirs + files:
            path = craft.no_links(Path(directory) / name)
            rel = craft.relative(path.relative_to(root).as_posix())
            if path.is_file():
                result[rel] = file_sha(path)
    return result


def acquire(pin, stage, *, fetch=None, download=transfer, checkout=git_checkout):
    require_windows()
    validate_pin(pin)
    stage = craft.no_links(Path(stage).absolute())
    if stage.exists() or not stage.parent.is_dir():
        raise InstallError('stage must be fresh with an existing parent')
    resolved = resolve_pin(pin, fetch)
    stage.mkdir()
    atomic(stage / 'pin.json', encode_json(pin))
    for key, expected in (('craft', pin['craft']['sha256']), ('reverse', pin['reverse']['archive_sha256'])):
        archive = stage / (key + '.zip')
        download(resolved[key]['url'], destination=archive)
        if file_sha(archive) != expected:
            raise InstallError(key + ' downloaded archive SHA256 mismatch')
        validate_win32_stage(stage, pin, archive=archive, kind=key)
        safe_extract_zip(archive, stage / (key + '-archive'))
    bundle_root = stage / 'craft-archive'
    bundle = craft.bundle(bundle_root)
    if file_sha(bundle_root / craft.MANIFEST) != pin['craft']['manifest_sha256']:
        raise InstallError('Craft manifest SHA256 mismatch')
    source_items = list((stage / 'reverse-archive').iterdir())
    expected_prefix = 'reverse-skill-' + pin['reverse']['commit']
    if len(source_items) != 1 or not source_items[0].is_dir() or source_items[0].name != expected_prefix:
        raise InstallError('reverse archive requires exact commit project prefix')
    extracted = source_items[0]
    contract = craft.reverse_contract(extracted)
    if contract['descriptor_sha256'] != pin['reverse']['descriptor_sha256']:
        raise InstallError('reverse descriptor SHA256 mismatch')
    reverse = stage / 'reverse'
    checkout(pin['reverse'], reverse, stage)
    canonical = canonical_files(reverse, pin['reverse']['commit'])
    exported = git_archive_files(reverse, pin['reverse']['commit'], canonical)
    if exported != craft.inventory(extracted):
        raise InstallError('reverse Git archive differs from pinned source archive')
    contract = craft.reverse_contract(reverse)
    # Detect moved tags/asset replacement during acquisition before any completion.
    if resolve_pin(pin, fetch) != resolved:
        raise InstallError('release metadata changed during acquisition')
    options = ['--craft-bundle', str(bundle_root), '--reverse-root', str(reverse)]
    atomic(stage / 'installer-options.json', encode_json(options))
    text = subprocess.list2cmdline(options) if os.name == 'nt' else shlex.join(options)
    atomic(stage / 'installer-options.txt', (text + '\n').encode())
    # All potentially large identity reads remain inside the owned total deadline.
    if craft.bundle(bundle_root) != bundle or craft.reverse_contract(reverse) != contract or canonical_files(reverse, pin['reverse']['commit']) != canonical:
        raise InstallError('acquired files changed before result')
    result = {'schema_version': 1, 'pin': pin, 'resolved': resolved, 'bundle_sha256': bundle['sha256'],
              'reverse_contract': contract, 'reverse_files': checkout_files(reverse), 'reverse_canonical_files': canonical,
              'reverse_archive_files': exported,
              'reverse_identity_algorithms': {'reverse_files': 'checkout-raw-file-sha256', 'reverse_canonical_files': 'git-commit-blob-sha256', 'reverse_archive_files': 'git-archive-export-file-sha256'}, 'installer_options': options,
              'qualification': 'artifact and source identity only; Pi/provider/task acceptance separate'}
    atomic(stage / 'acquisition-candidate.json', encode_json(result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    pin = parser.add_mutually_exclusive_group(required=True)
    pin.add_argument('--pin-file')
    pin.add_argument('--pin', help='explicit pin JSON object')
    parser.add_argument('--stage', required=True)
    parser.add_argument('--deadline-seconds', type=int, default=600)
    parser.add_argument('--_worker-token', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        require_windows()
        record = validate_pin(strict_json(Path(args.pin_file).read_text(encoding='utf-8') if args.pin_file else args.pin))
        stage = craft.no_links(Path(args.stage).absolute())
        validate_win32_stage(stage, record)
        if not 1 <= args.deadline_seconds <= 600:
            raise InstallError('total wall deadline must be 1..600 seconds')
        if args._worker_token:
            if args._worker_token != os.environ.get('CRAFT_RELEASE_ACQUIRE_TOKEN'):
                raise InstallError('worker requires owned supervisor')
            print(json.dumps(acquire(record, stage)))
            return 0
        if stage.exists() or not stage.parent.is_dir():
            raise InstallError('stage must be fresh with an existing parent')
        token = secrets.token_hex(32)
        env = clean_env(stage)
        env['CRAFT_RELEASE_ACQUIRE_TOKEN'] = token
        command = [sys.executable, '-B', str(Path(__file__).resolve()), '--pin', json.dumps(record), '--stage', str(stage), '--deadline-seconds', str(args.deadline_seconds), '--_worker-token', token]
        cleanup_seconds = min(5, args.deadline_seconds / 2)
        observed = run_owned(command, cwd=Path(__file__).resolve().parent, env=env,
                             timeout=args.deadline_seconds - cleanup_seconds, cleanup_seconds=cleanup_seconds)
        if observed['returncode'] or observed['timed_out'] or observed['cleanup'] != 'verified' or observed['had_descendants']:
            raise InstallError('acquisition failed or cleanup unknown; no completion; ' + observed['stderr'][-1000:])
        result = strict_json(observed['stdout'])
        if load_json(stage / 'acquisition-candidate.json') != result or result.get('pin') != record or result.get('installer_options') != ['--craft-bundle', str(stage / 'craft-archive'), '--reverse-root', str(stage / 'reverse')]:
            raise InstallError('worker result inconsistent')
        result['supervision'] = {k: observed[k] for k in ('returncode', 'timed_out', 'cleanup', 'had_descendants', 'scope')}
        atomic(stage / 'complete.json', encode_json(result))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (InstallError, OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'ok': False, 'code': ('unsupported-platform' if str(error).startswith('unsupported-platform:') else
                     'stage-path-too-long' if str(error).startswith('stage-path-too-long:') else 'acquisition-failed'), 'error': str(error), 'complete': False}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
