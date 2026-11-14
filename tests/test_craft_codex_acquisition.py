"""Offline acquisition boundary checks; no real Git, account, model or network."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import acquire_craft_codex as acquisition
from versions import InstallError


class CodexAcquisitionTests(unittest.TestCase):
    def setUp(self):
        base = REPO / ".local/tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = b'{"fixture":"offline artifact bytes"}\n'
        self.pin = {"schema_version": 1, "name": acquisition.NAME,
                    "craft": {"repository": acquisition.shared.OWN, "tag": "craft-codex-v0.1.0",
                              "commit": "a" * 40, "asset": "craft-codex-windows-x64-0.1.0.zip", "asset_id": 123,
                              "sha256": "0" * 64, "manifest_sha256": hashlib.sha256(self.manifest).hexdigest()},
                    "reverse": {"repository": acquisition.shared.REVERSE, "commit": "b" * 40,
                                "descriptor_sha256": "c" * 64},
                    "codex": {"version": "0.167.0-alpha.4.1", "protocol": "app-server-v2"}}
        self.args = argparse.Namespace(pin_file=str(self.root / "pin.json"), stage=str(self.root / "stage"),
                                       codex_cli=str(self.root / "codex.exe"))

    def arrange(self, member=None, bad_digest=False):
        member = member or acquisition.craft_codex.MANIFEST
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as stream:
            stream.writestr(member, self.manifest)
        payload = archive.getvalue()
        self.pin["craft"]["sha256"] = "0" * 64 if bad_digest else hashlib.sha256(payload).hexdigest()
        Path(self.args.pin_file).write_text(json.dumps(self.pin), encoding="utf-8")
        self.args._pin_sha256 = acquisition.shared.file_sha(self.args.pin_file)
        def checkout(record, root, stage):
            root.mkdir()
            (root / "source.txt").write_bytes(b"canonical source")
            (root / "script.ps1").write_bytes(b"Write-Output 'fixture'\r\n")
            (root / ".git").mkdir()
            for name, data in (("HEAD", record["commit"]), ("config", "public repository"), ("index", "frozen index")):
                (root / ".git" / name).write_text(data, encoding="utf-8")
            checkout_files = acquisition.shared.checkout_files(root)
            canonical_files = dict(checkout_files)
            canonical_files["script.ps1"] = hashlib.sha256(b"Write-Output 'fixture'\n").hexdigest()
            return {"canonical_files": canonical_files, "checkout_files": checkout_files}
        self.checkout = checkout
        def download(url, *, destination):
            self.assertEqual(url, acquisition.shared.OWN + "/releases/download/craft-codex-v0.1.0/craft-codex-windows-x64-0.1.0.zip")
            Path(destination).write_bytes(payload)
        for target, name, replacement in (
            (acquisition.shared, "require_windows", lambda: None),
            (acquisition.shared, "validate_win32_stage", lambda *args, **kwargs: None),
            (acquisition.shared, "git_command", lambda *args, **kwargs: b"codex-cli 0.167.0-alpha.4.1\n"),
            (acquisition.shared, "transfer", download),
            (acquisition.craft_codex, "cli_identity", lambda path: {"path": str(Path(path).absolute()), "sha256": "d" * 64}),
            (acquisition.craft_codex, "reviewed_profile", lambda: (b"fixture profile", {"runtime": {"cli_sha256": "d" * 64}})),
            (acquisition.craft_codex, "bundle", lambda root: {"sha256": "f" * 64, "manifest": {"artifact": {"source_commit": "a" * 40}, "codex": self.pin["codex"]}}),
            (acquisition.craft_codex, "reverse_contract", lambda root: {"descriptor_sha256": "c" * 64}),
            (acquisition, "checkout_reverse", checkout),
        ):
            handle = patch.object(target, name, replacement)
            handle.start()
            self.addCleanup(handle.stop)

    def assert_incomplete(self):
        self.assertFalse((Path(self.args.stage) / "acquisition-result.json").exists())
        self.assertFalse((Path(self.args.stage) / "installer-options.json").exists())

    def test_complete_only_after_pinned_bytes_and_reverse_admission(self):
        self.arrange()
        candidate = acquisition.acquire(self.args)
        self.assertEqual(candidate["phase"], "candidate-verified")
        self.assertNotIn("complete", candidate)
        self.assert_incomplete()
        result = acquisition.publish_candidate(self.args, candidate, self.verified_supervision())
        self.assertTrue(result["complete"])
        self.assertEqual(result["pin"]["reverse"]["commit"], "b" * 40)
        self.assertEqual(json.loads((Path(self.args.stage) / "installer-options.json").read_text()), result["installer_options"])
        self.assertEqual(result["archive_sha256"], self.pin["craft"]["sha256"])
        self.assertNotEqual(candidate["inputs"]["reverse_canonical_files"]["script.ps1"], candidate["inputs"]["reverse_files"]["script.ps1"])

    def test_real_local_git_checkout_keeps_canonical_and_crlf_bytes_distinct(self):
        # Only a tiny owned local repository; no remote, account or product init.
        origin, target = self.root / "git-origin", self.root / "git-checkout"
        acquisition.shared.git_command(["git", "init", str(origin)], stage=self.root)
        (origin / ".gitattributes").write_bytes(b"*.ps1 text eol=crlf\n")
        source = b"Write-Output 'offline fixture'\n"
        (origin / "example.ps1").write_bytes(source)
        acquisition.shared.git_command(["git", "-C", str(origin), "add", ".gitattributes", "example.ps1"], stage=self.root)
        acquisition.shared.git_command(["git", "-c", "user.name=Offline Fixture", "-c", "user.email=fixture@example.invalid", "-C", str(origin), "commit", "--no-gpg-sign", "-m", "offline source identity fixture"], stage=self.root)
        commit = acquisition.shared.git_command(["git", "-C", str(origin), "rev-parse", "HEAD"], stage=self.root).decode().strip()
        result = acquisition.checkout_reverse({"repository": str(origin), "commit": commit}, target, self.root)
        self.assertEqual(result["canonical_files"]["example.ps1"], hashlib.sha256(source).hexdigest())
        actual = (target / "example.ps1").read_bytes()
        self.assertEqual(actual, source.replace(b"\n", b"\r\n"))
        self.assertEqual(result["checkout_files"]["example.ps1"], hashlib.sha256(actual).hexdigest())
        self.assertNotEqual(result["canonical_files"]["example.ps1"], result["checkout_files"]["example.ps1"])

    def test_bad_download_digest_never_emits_completion(self):
        self.arrange(bad_digest=True)
        with self.assertRaisesRegex(InstallError, "archive SHA256 mismatch"):
            acquisition.acquire(self.args)
        self.assertTrue(Path(self.args.stage).is_dir())
        self.assert_incomplete()

    def test_source_failure_preserves_download_without_success_options(self):
        self.arrange()
        with patch.object(acquisition, "checkout_reverse", side_effect=InstallError("canonical Git source drift")):
            with self.assertRaisesRegex(InstallError, "source drift"):
                acquisition.acquire(self.args)
        self.assertTrue((Path(self.args.stage) / self.pin["craft"]["asset"]).is_file())
        self.assert_incomplete()

    def test_zip_member_cannot_escape_stage(self):
        self.arrange(member="../../escaped.json")
        with self.assertRaises(InstallError):
            acquisition.acquire(self.args)
        self.assertFalse((self.root / "escaped.json").exists())
        self.assert_incomplete()

    @staticmethod
    def verified_supervision():
        return {"returncode": 0, "timed_out": False, "cleanup": "verified", "had_descendants": False}

    def test_cleanup_rejection_cannot_leave_success_markers(self):
        self.arrange()
        candidate = acquisition.acquire(self.args)
        supervision = self.verified_supervision()
        supervision["cleanup"] = "unknown"
        with self.assertRaisesRegex(InstallError, "cleanup not verified"):
            acquisition.publish_candidate(self.args, candidate, supervision)
        self.assert_incomplete()
        self.assertEqual(json.loads((Path(self.args.stage) / "acquisition-candidate.json").read_text())["phase"], "candidate-verified")

    def test_pin_byte_drift_is_rejected_before_worker_writes(self):
        self.arrange()
        pin = Path(self.args.pin_file)
        pin.write_text(pin.read_text() + "\n", encoding="utf-8")
        with self.assertRaisesRegex(InstallError, "pin drift"):
            acquisition.acquire(self.args)
        self.assertFalse(Path(self.args.stage).exists())

    def test_source_drift_between_worker_and_supervisor_blocks_publication(self):
        self.arrange()
        candidate = acquisition.acquire(self.args)
        (Path(self.args.stage) / "reverse/source.txt").write_bytes(b"changed after worker")
        with self.assertRaisesRegex(InstallError, "source drift"):
            acquisition.publish_candidate(self.args, candidate, self.verified_supervision())
        self.assert_incomplete()

    def test_bundle_drift_during_reverse_checkout_prevents_candidate(self):
        self.arrange()
        def changed_checkout(record, root, stage):
            result = self.checkout(record, root, stage)
            (stage / "craft-archive" / acquisition.craft_codex.MANIFEST).write_bytes(b"changed during checkout")
            return result
        with patch.object(acquisition, "checkout_reverse", changed_checkout):
            with self.assertRaisesRegex(InstallError, "archive/bundle drift"):
                acquisition.acquire(self.args)
        self.assert_incomplete()
        self.assertFalse((Path(self.args.stage) / "acquisition-candidate.json").exists())

    def test_unqualified_same_version_cli_stops_before_process_or_download(self):
        self.arrange()
        with patch.object(acquisition.craft_codex, "reviewed_profile", return_value=(b"other qualified bytes", {"runtime": {"cli_sha256": "e" * 64}})), patch.object(acquisition.shared, "git_command", side_effect=AssertionError("unexpected native version process")):
            with self.assertRaisesRegex(InstallError, "not qualified"):
                acquisition.acquire(self.args)
        self.assertFalse(Path(self.args.stage).exists())

    def test_existing_stage_stops_before_cli_or_download(self):
        self.arrange()
        Path(self.args.stage).mkdir()
        with patch.object(acquisition.craft_codex, "cli_identity", side_effect=AssertionError("unexpected probe")):
            with self.assertRaisesRegex(InstallError, "stage must not exist"):
                acquisition.acquire(self.args)
        self.assert_incomplete()


if __name__ == "__main__":
    unittest.main()
