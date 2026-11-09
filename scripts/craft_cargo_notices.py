"""Notice inventory for crates actually reported by the locked production Cargo build."""
import hashlib
from pathlib import Path
import re
import shutil
import tomllib

from versions import InstallError


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# Independently accepted single-package evidence. Changing this pin requires review
# and a new source/recipe freeze; arbitrary SPDX declarations never qualify.
STANDARD_0BSD_SOURCE_SHA256 = '988fe80dc1f9a7611579911995a65182a0f8d0b6f4129d19854dec43ed445872'


def standard_0bsd(pkg, root, checksum, evidence):
    import json
    if evidence is None or (pkg['name'], pkg['version']) != ('yaxpeax-arm', '0.5.0'):
        return None
    evidence = Path(evidence)
    from craft import no_links
    source_file = no_links(evidence / 'SOURCE.json')
    if sha(source_file) != STANDARD_0BSD_SOURCE_SHA256:
        raise InstallError('exact 0BSD source evidence drift')
    source = json.loads(source_file.read_text(encoding='utf-8'))
    lock = source['recommended_narrow_exception_lock']
    vcs = root / '.cargo_vcs_info.json'
    try:
        identity = json.loads(vcs.read_text(encoding='utf-8'))
        matches = (pkg.get('source') == lock['registry_source'] and
                   checksum == lock['registry_archive_sha256'] and
                   pkg.get('license') == lock['selected_license'] == '0BSD' and
                   identity['git']['sha1'] == lock['source_commit'] and
                   identity.get('path_in_vcs', '') == lock['path_in_vcs'] and
                   sha(root / 'Cargo.toml') == lock['normalized_metadata_sha256'] and
                   sha(root / 'Cargo.toml.orig') == lock['original_metadata_sha256'])
    except (OSError, KeyError, ValueError) as exc:
        raise InstallError('exact 0BSD compiled package evidence missing') from exc
    if not matches:
        raise InstallError('exact 0BSD compiled package identity drift')
    text = no_links(evidence / 'standard-0BSD.txt')
    if sha(text) != lock['standard_text_sha256']:
        raise InstallError('exact 0BSD standard text drift; placeholders must remain unchanged')
    return text, source_file, source


def collect(metadata, compiled_ids, locks, destination, source_root, *, supplements=None, standards=None, allow_missing=False):
    import json
    supplemental = {}
    if supplements is not None:
        supplements = Path(supplements)
        registry = json.loads((supplements / 'source-registry.json').read_text(encoding='utf-8'))
        for rel, digest in registry['files'].items():
            from craft import relative, no_links
            p = no_links(supplements / relative(rel))
            if sha(p) != digest:
                raise InstallError('compiled notice supplement source drift: ' + rel)
        supplemental = {p['crate']: p for p in registry['packages']}
    checksums = {}
    for path in locks:
        for item in tomllib.loads(Path(path).read_text(encoding='utf-8')).get('package', []):
            if item.get('checksum'):
                checksums[(item['name'], item['version'], item['source'])] = item['checksum']
    packages = {}
    for meta in metadata.values():
        packages.update({p['id']: p for p in meta['packages']})
    result, missing = {}, []
    for package_id in sorted(compiled_ids):
        pkg = packages.get(package_id)
        if pkg is None:
            raise InstallError('compiled package absent from locked Cargo metadata')
        name, version, source = pkg['name'], pkg['version'], pkg['source']
        root = Path(pkg['manifest_path']).parent
        if source is None and (name.startswith(('craft-anything-', 'craft-pi-')) or name == 'xtask'):
            continue  # Same upstream/owned project licenses are retained at bundle/source roots.
        key = name + '-' + version
        if key in result and result[key]['source'] != source:
            raise InstallError('ambiguous compiled Cargo package license identity: ' + key)
        paths = {p for p in root.iterdir() if p.is_file() and re.match(r'(?i)^(licen[cs]e|copying|notice|copyright)([._-]|$)', p.name)}
        if pkg.get('license_file'):
            path = (root / pkg['license_file']).resolve()
            if not path.is_relative_to(root.resolve()):
                raise InstallError('compiled Cargo license file escapes package: ' + key)
            paths.add(path)
        if not paths:
            # Some crates ship a complete original grant in README instead of LICENSE.
            for path in root.glob('README*'):
                if path.is_file() and re.search(r'(?i)permission is hereby granted|redistribution and use|apache license\s+version|public domain', path.read_text(encoding='utf-8', errors='replace')):
                    paths.add(path)
        supplement = supplemental.get(key)
        if not paths and supplement and supplement.get('license_sources'):
            expected_archive = checksums.get((name, version, source))
            vcs = root / '.cargo_vcs_info.json'
            if supplement['archive_sha256'] != expected_archive:
                raise InstallError('supplement differs from locked compiled crate archive: ' + key)
            if vcs.is_file() and json.loads(vcs.read_text())['git']['sha1'] != supplement.get('commit'):
                raise InstallError('supplement source commit differs from compiled crate: ' + key)
            for grant in supplement['license_sources']:
                from craft import relative
                path = supplements / relative(grant['path'])
                if sha(path) != grant['sha256']:
                    raise InstallError('supplement license grant hash mismatch: ' + key)
                paths.add(path)
        standard = None
        if not paths:
            standard = standard_0bsd(pkg, root, checksums.get((name, version, source)), standards)
            if standard:
                paths.add(standard[0])
        record = {'name': name, 'version': version, 'source': source, 'declared_license': pkg.get('license'),
                  'compiled': True, 'notice_files': {}}
        if source and source.startswith('registry+'):
            expected = checksums.get((name, version, source))
            archive = root.parents[2] / 'cache' / root.parent.name / (key + '.crate')
            if not expected or not archive.is_file() or sha(archive) != expected:
                raise InstallError('compiled registry archive checksum missing/mismatch: ' + key)
            record['registry_archive_sha256'] = expected
        elif source is None:
            record['upstream_vendor_path'] = root.relative_to(source_root).as_posix()
        if not paths:
            missing.append(key)
            record['status'] = 'missing-original-license-text; publication-blocked'
            record['source_association'] = supplement
            result[key] = record
            continue
        if supplement and any(path.is_relative_to(supplements) for path in paths):
            record['source_association'] = supplement
        record['status'] = ('standard-license-text,declared-in-upstream-metadata' if standard else
                            'original-grant-retained; not blanket legal certification')
        if standard:
            record['source_association'] = standard[2]
            record['source_evidence_sha256'] = sha(standard[1])
            evidence_target = Path(destination) / key / 'SOURCE.json'
            evidence_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(standard[1], evidence_target)
            if sha(evidence_target) != STANDARD_0BSD_SOURCE_SHA256:
                raise InstallError('exact 0BSD source evidence changed during copy')
            record['notice_files'][evidence_target.relative_to(destination).as_posix()] = sha(evidence_target)
        grant_found = False
        for path in paths:
            if path.is_file() and not path.is_symlink():
                from build_craft_bundle import has_license_grant
                text = path.read_text(encoding='utf-8', errors='replace')
                cdla = ('Community Data License Agreement - Permissive - Version 2.0' in text and
                        'A Data Recipient may use, modify, and share the Data' in text and
                        'makes available the text of this agreement' in text and len(text) > 1000)
                grant_found |= has_license_grant(text) or cdla
        if not grant_found:
            raise InstallError('compiled notice grant text missing/trivial: ' + key)
        for path in sorted(paths):
            if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
                raise InstallError('compiled notice text missing/trivial: ' + key)
            # Preserve accompanying COPYING/license-choice notes too, while the
            # package must separately contain actual grant text (e.g. LICENSE-MIT).
            target = Path(destination) / key / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            before = sha(path)
            shutil.copy2(path, target)
            if sha(path) != before or sha(target) != before:
                raise InstallError('compiled notice changed during copy: ' + key)
            record['notice_files'][target.relative_to(destination).as_posix()] = before
        result[key] = record
    if missing and not allow_missing:
        raise InstallError('compiled Cargo notice texts missing: ' + ', '.join(missing))
    return result
