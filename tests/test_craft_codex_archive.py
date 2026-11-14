"""Archive verified-snapshot I/O checks; no native build, network or model."""
import argparse
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_craft_codex_bundle as packaging
from configuration import digest, encode_json
from versions import InstallError


class CodexArchiveTests(unittest.TestCase):
    def setUp(self):
        base = REPO / ".local/tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "verified-files"
        self.bundle.mkdir()
        for name, data in (("a.txt", b"frozen a"), ("b.txt", b"frozen b"), (packaging.craft_codex.MANIFEST, b"validated manifest fixture")):
            (self.bundle / name).write_bytes(data)
        self.args = argparse.Namespace(bundle=str(self.bundle), output=str(self.root / "artifact.zip"))
        # Isolate archive I/O from bundle admission, which has its own native-contract tests.
        def admitted_snapshot(root):
            root = Path(root)
            files = {path.name: digest(path.read_bytes()) for path in root.iterdir()}
            return {"root": str(root), "manifest": {"fixture": "admitted file snapshot"},
                    "files": files, "sha256": digest(encode_json(files)), "mode": "unit snapshot"}
        handle = patch.object(packaging.craft_codex, "bundle", admitted_snapshot)
        handle.start()
        self.addCleanup(handle.stop)

    def test_zip_contains_exact_frozen_bytes(self):
        result = packaging.archive(self.args)
        self.assertTrue(result["complete"])
        with zipfile.ZipFile(self.args.output) as zipped:
            self.assertEqual(set(zipped.namelist()), {"a.txt", "b.txt", packaging.craft_codex.MANIFEST})
            self.assertEqual(zipped.read("a.txt"), b"frozen a")
            self.assertEqual(zipped.read("b.txt"), b"frozen b")

    def test_changed_next_file_never_returns_success(self):
        original = zipfile.ZipFile.writestr
        def during_write(stream, info, data, *args, **kwargs):
            result = original(stream, info, data, *args, **kwargs)
            if info.filename == "a.txt":
                (self.bundle / "b.txt").write_bytes(b"changed while zip was being created")
            return result
        with patch.object(zipfile.ZipFile, "writestr", during_write):
            with self.assertRaisesRegex(InstallError, "input changed"):
                packaging.archive(self.args)

    def test_changed_written_source_is_rejected_by_final_recheck(self):
        original = zipfile.ZipFile.writestr
        def during_write(stream, info, data, *args, **kwargs):
            result = original(stream, info, data, *args, **kwargs)
            if info.filename == packaging.craft_codex.MANIFEST:
                (self.bundle / "a.txt").write_bytes(b"changed after original bytes were written")
            return result
        with patch.object(zipfile.ZipFile, "writestr", during_write):
            with self.assertRaisesRegex(InstallError, "source drift"):
                packaging.archive(self.args)


if __name__ == "__main__":
    unittest.main()
