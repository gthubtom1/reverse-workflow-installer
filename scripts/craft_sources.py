"""Complete owned Rust snapshots, with explicit non-production portable transforms."""
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import tomllib

import craft
from configuration import encode_json, load_json
from versions import InstallError

EXTRA = {'FROZEN-SOURCE-MANIFEST.json', 'LICENSE-MIT', 'snapshot-origin.json'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def files(root):
    return craft.inventory(root, forbidden={'auth.json', 'mcp.json', 'settings.json', 'credentials.json', '.env', 'backups', '.npmrc'})


def tree_hash(value):
    return hashlib.sha256(json.dumps(dict(sorted(value.items())), separators=(',', ':')).encode()).hexdigest()


def original_files(manifest, expected):
    entries = manifest.get('files')
    if isinstance(entries, list):
        mapping = {x['path']: x['sha256'] for x in entries}
        if len(mapping) != len(entries):
            raise InstallError('duplicate owned source entry')
        digest = hashlib.sha256(''.join(f'{p}\0{mapping[p]}\n' for p in sorted(mapping)).encode()).hexdigest()
    elif isinstance(entries, dict):
        mapping = entries
        digest = tree_hash(mapping)
    else:
        raise InstallError('owned source manifest files missing')
    if not mapping or digest != expected or manifest.get('source_tree_sha256') != expected:
        raise InstallError('owned source tree hash mismatch')
    for rel, digest in mapping.items():
        craft.relative(rel)
        if any(p.casefold() in {'auth.json', 'mcp.json', 'settings.json', 'credentials.json', '.env', 'backups'} for p in Path(rel).parts):
            raise InstallError('owned manifest contains private resource')
        if not re.fullmatch('[0-9a-f]{64}', str(digest)):
            raise InstallError('owned source hash invalid')
    return mapping


def portable_python(text):
    """Require explicit tools in historical development helpers; never execute them."""
    def replace(match):
        value = match.group(2).replace('\\', '/')
        if value.endswith('node.exe'):
            return 'os.environ["CRAFT_TEST_NODE"]'
        if value.endswith('cli.js'):
            return 'os.environ["CRAFT_PI_ENTRY"]'
        if value.endswith('csc.exe'):
            return 'os.environ["CRAFT_NATIVE_CSC"]'
        if value.endswith('objdump.exe'):
            return 'str(Path(os.environ["CRAFT_GNU_BIN"]) / "objdump.exe")'
        if value.endswith('gcc.exe'):
            return 'str(Path(os.environ["CRAFT_GNU_BIN"]) / "gcc.exe")'
        if value.rstrip(';').endswith('mingw64/bin'):
            return 'os.environ["CRAFT_GNU_BIN"]' + (' + os.pathsep' if value.endswith(';') else '')
        raise InstallError('unreviewed absolute path in owned Python helper')
    rewritten = re.sub(r'([\'\"])([A-Za-z]:[\\/][^\'\"\n]*)\1', replace, text)
    rewritten = rewritten.replace('WORKSPACE=ROOT.parent.parent', 'WORKSPACE=Path(os.environ["CRAFT_NATIVE_WORKSPACE"])')
    rewritten = rewritten.replace('workspace=ROOT.parent.parent', 'workspace=Path(os.environ["CRAFT_NATIVE_WORKSPACE"])')
    if rewritten != text:
        parsed = ast.parse(rewritten)
        after_doc = parsed.body[0].end_lineno if parsed.body and isinstance(parsed.body[0], ast.Expr) and isinstance(parsed.body[0].value, ast.Constant) and isinstance(parsed.body[0].value.value, str) else 0
        lines = rewritten.splitlines(True)
        lines.insert(after_doc, 'import os\n')
        rewritten = ''.join(lines)
        ast.parse(rewritten)
    return rewritten


def transform(rel, data, kind):
    text = data.decode('utf-8')
    if rel == 'README.md':
        tail = text[text.index('## Explicit input and output contract'):] if kind == 'bridge' and '## Explicit input and output contract' in text else (text if kind == 'executor' else '')
        tail = re.sub(r'`[A-Za-z]:[\\/][^`]+`', '`the explicitly supplied local tool path`', tail)
        prefix = ('# Installer-owned portable ' + kind + '\n\n'
                  'All production Rust and Cargo bytes are unchanged from FROZEN-SOURCE-MANIFEST.json. '
                  'All meaningful tests, fixtures, examples and development helper source are retained. '
                  'snapshot-origin.json records the original and portable file identities; documentation/test/helper transforms are not production changes.\n\n'
                  'Build/test through the installer packaging recipe in docs/craft-packaging.md. '
                  'Tests require explicit CRAFT_TEST_NODE, CRAFT_TEST_ROOT and (executor) CRAFT_TEST_DRIVER/CRAFT_TEST_CARGO. '
                  'There is no developer-machine tool fallback. Fixture binaries are built only with --features fixtures and never included as runtime binaries. '
                  'Native qualification helpers are preserved development source, syntax checked only here; no live/provider/native qualification is claimed. '
                  'They additionally require explicit CRAFT_GNU_BIN, CRAFT_PI_ENTRY, CRAFT_NATIVE_CSC and CRAFT_NATIVE_WORKSPACE where applicable, plus their reviewed external scenario inputs.\n\n'
                  'The project distributes its owned code under the MIT option of the unchanged dual-license declaration. '
                  'LICENSE-MIT identifies our own project owner; upstream dependencies retain separate original notices.\n\n')
        return (prefix + tail).encode()
    if kind == 'bridge' and rel == 'config.example.json':
        value = json.loads(text)
        value['pi'] = {'program': 'REQUIRED_ABSOLUTE_NODE_EXE', 'argv': ['REQUIRED_ABSOLUTE_OFFICIAL_PI_ENTRY_JS']}
        for key in ('task_cwd', 'agent_dir', 'session_dir'):
            value[key] = 'REQUIRED_ABSOLUTE_OWNED_' + key.upper()
        value['cancel']['marker'] = 'REQUIRED_ABSOLUTE_OWNED_CANCEL_MARKER'
        return encode_json(value)
    if rel == 'tests/protocol.rs' and kind == 'bridge':
        text = text.replace('PathBuf::from(env!("CARGO_MANIFEST_DIR"))\n            .join("target/fixtures")',
                            'PathBuf::from(std::env::var_os("CRAFT_TEST_ROOT").expect("CRAFT_TEST_ROOT must be explicit"))')
        text = re.sub(r'PathBuf::from\("[A-Za-z]:/[^"\n]+node\.exe"\)',
                      'PathBuf::from(std::env::var_os("CRAFT_TEST_NODE").expect("CRAFT_TEST_NODE must be explicit"))', text)
        return text.encode()
    if rel == 'tests/fixtures/fake-pi.cjs' and kind == 'executor':
        text = text.replace("command:'cargo +stable-x86_64-pc-windows-gnu build --quiet --offline'",
                            "command:JSON.parse(fs.readFileSync(path.join(cwd,'portable-fixture-command.json'),'utf8')).command")
        return text.encode()
    if rel == 'tests/fixtures/offline-pi-peer.rs' and kind == 'executor':
        text = re.sub(r'Command::new\("[A-Za-z]:/[^"\n]+node\.exe"\)',
                      'Command::new(std::env::var_os("CRAFT_TEST_NODE").expect("CRAFT_TEST_NODE must be explicit"))', text)
        return text.encode()
    if rel == 'tests/integration.rs' and kind == 'executor':
        text = re.sub(r'let driver = std::env::var_os\("CRAFT_TEST_DRIVER"\).*?\n        \}\);',
                      'let driver = PathBuf::from(std::env::var_os("CRAFT_TEST_DRIVER").expect("CRAFT_TEST_DRIVER must be explicit"));', text, flags=re.S)
        text = re.sub(r'program: "[A-Za-z]:/[^"\n]+node\.exe"\.into\(\)',
                      'program: std::env::var("CRAFT_TEST_NODE").expect("CRAFT_TEST_NODE must be explicit").into()', text)
        text = re.sub(r'\.args\(\["[A-Za-z]:/[^"\n]+node\.exe",',
                      '.args([std::env::var("CRAFT_TEST_NODE").expect("CRAFT_TEST_NODE must be explicit").as_str(),', text)
        explicit_root = 'PathBuf::from(std::env::var_os("CRAFT_TEST_ROOT").expect("CRAFT_TEST_ROOT must be explicit")).join("'
        text = text.replace('Path::new(env!("CARGO_MANIFEST_DIR")).join("test-artifacts/', explicit_root)
        text = text.replace('Path::new(env!("CARGO_MANIFEST_DIR")).join("test-artifacts', explicit_root)
        text = text.replace('command: "cargo +stable-x86_64-pc-windows-gnu build --quiet --offline".into()',
                            'command: portable_command.clone()')
        text = text.replace('    let p = AcceptedResearch {',
                            '    let cargo = std::env::var("CRAFT_TEST_CARGO").expect("CRAFT_TEST_CARGO must be explicit");\n'
                            '    assert!(!cargo.contains([\'"\', \'\\r\', \'\\n\']), "invalid explicit Cargo path");\n'
                            '    let portable_command = String::from("portable-fixture-build.cmd");\n'
                            '    fs::write(ws.app_dir().join(&portable_command), format!("@echo off\\r\\n\\\"{}\\\" build --quiet --offline\\r\\n", cargo)).unwrap();\n'
                            '    fs::write(ws.app_dir().join("portable-fixture-command.json"), serde_json::to_vec(&json!({"command": portable_command})).unwrap()).unwrap();\n'
                            '    let p = AcceptedResearch {')
        return text.encode()
    if kind == 'executor' and rel.startswith('scripts/') and rel.endswith('.py'):
        return portable_python(text).encode()
    return data


def validate(root, kind):
    root = Path(root)
    manifest = load_json(root / 'packaged-source-manifest.json')
    actual = {p: h for p, h in files(root).items() if p != 'packaged-source-manifest.json'}
    label = 'driver' if kind == 'bridge' else 'executor'
    if actual != manifest.get('files') or tree_hash(actual) != manifest.get('packaged_source_tree_sha256'):
        raise InstallError('packaged ' + label + ' source drift')
    origin = load_json(root / 'snapshot-origin.json')
    if origin.get('format_version') != 2 or origin.get('kind') != kind or origin.get('original_manifest_sha256') != sha(root / 'FROZEN-SOURCE-MANIFEST.json'):
        raise InstallError('owned complete-source origin drift')
    original = original_files(load_json(root / 'FROZEN-SOURCE-MANIFEST.json'), manifest['frozen_source_tree_sha256'])
    changed = origin['transformed_files']
    exact = {p: h for p, h in original.items() if p not in changed}
    extras = EXTRA | ({'ATTRIBUTION.md'} if kind == 'bridge' else set())
    if origin['exact_copied_files'] != exact or set(actual) != set(original) | extras:
        raise InstallError('owned complete-source inventory mismatch')
    for rel, digest in original.items():
        if rel.startswith('src/') or rel in ('Cargo.toml', 'Cargo.lock'):
            if rel in changed or actual.get(rel) != digest:
                raise InstallError('production source must remain byte-identical')
        elif rel in changed:
            if changed[rel]['original_sha256'] != digest or changed[rel]['packaged_sha256'] != actual.get(rel):
                raise InstallError('owned portable transform identity mismatch')
        elif actual.get(rel) != digest:
            raise InstallError('owned copied source differs from original')
    cargo = tomllib.loads((root / 'Cargo.toml').read_text(encoding='utf-8'))
    for binary in cargo.get('bin', []):
        if binary.get('path') not in actual:
            raise InstallError('Cargo declared binary/test fixture source missing')
    return manifest


def snapshot(source, manifest_path, expected_tree, kind, destination):
    source, destination = craft.no_links(Path(source).absolute()), craft.no_links(Path(destination).absolute())
    manifest = load_json(manifest_path)
    original = original_files(manifest, expected_tree)
    if destination.exists():
        raise InstallError('owned snapshot destination already exists')
    for rel, digest in original.items():
        craft.no_links(source / rel)
        if sha(source / rel) != digest:
            raise InstallError('frozen owned source changed: ' + rel)
    for folder in ('src', 'tests', 'examples'):
        if (source / folder).is_dir() or any(p.startswith(folder + '/') for p in original):
            found = {folder + '/' + p: h for p, h in files(source / folder).items()}
            if found != {p: h for p, h in original.items() if p.startswith(folder + '/')}:
                raise InstallError('frozen owned source inventory mismatch: ' + folder)
    destination.mkdir(parents=True)
    changes = {}
    for rel, digest in original.items():
        data = (source / rel).read_bytes()
        if rel.startswith('src/') or rel in ('Cargo.toml', 'Cargo.lock', '.gitignore'):
            output = data
        else:
            output = transform(rel, data, kind)
        path = destination / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(output)
        if output != data:
            changes[rel] = {'original_sha256': digest, 'packaged_sha256': sha(path), 'reason': 'portable docs, explicit tool/test environment; production bytes unchanged'}
    shutil.copy2(manifest_path, destination / 'FROZEN-SOURCE-MANIFEST.json')
    shutil.copy2(Path(__file__).resolve().parents[1] / 'LICENSE', destination / 'LICENSE-MIT')
    if kind == 'bridge':
        (destination / 'ATTRIBUTION.md').write_text('Copyright (c) 2026 gthubtom1. Project-owned bridge is distributed under the MIT option of its unchanged MIT OR Apache-2.0 declaration. This is not official Craft/Pi source. Dependencies retain their original licenses.\n', encoding='utf-8')
    for rel, digest in original.items():
        if sha(source / rel) != digest:
            raise InstallError('source changed during owned copy')
    if load_json(manifest_path) != manifest:
        raise InstallError('source manifest changed during copy')
    origin = {'format_version': 2, 'kind': kind, 'original_source_tree_sha256': expected_tree,
              'original_manifest_sha256': sha(manifest_path), 'exact_copied_files': {p: h for p, h in original.items() if p not in changes},
              'transformed_files': changes, 'meaningful_tests_retained': True,
              'development_helpers': 'source retained; syntax only, not native/provider qualification'}
    (destination / 'snapshot-origin.json').write_bytes(encode_json(origin))
    inventory = files(destination)
    value = {'schema_version': 2, 'frozen_source_tree_sha256': expected_tree,
             'packaged_source_tree_sha256': tree_hash(inventory), 'files': inventory,
             'algorithm': 'sha256 sorted compact JSON path->SHA256; excludes this manifest'}
    (destination / 'packaged-source-manifest.json').write_bytes(encode_json(value))
    validate(destination, kind)
    return value
