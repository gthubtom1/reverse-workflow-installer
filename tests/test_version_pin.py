"""Explicit official-version selection, frozen replay and unchanged mismatch gates."""
import contextlib
import io
import unittest
from unittest.mock import patch

import test_installer as fixtures

cli, w = fixtures.cli, fixtures.w


def metadata(url):
    if "pypi" not in url:
        return fixtures.metadata(url)
    return {"info": {"name": "specify-cli"}, "releases": {
        "1.3.1": [{"filename": "specify_cli-1.3.1.whl", "digests": {"sha256": "1" * 64}, "requires_python": ">=3.11"}],
        "1.3.2": [{"filename": "specify_cli-1.3.2.whl", "digests": {"sha256": "2" * 64}, "requires_python": ">=3.12"}],
        "2.0.0": [{"filename": "yanked.whl", "yanked": True}],
        "2.1.0": [], "3.0.0rc1": [{"filename": "pre.whl"}],
    }}


class VersionPinTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.Fixture()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)

    def plan(self, version=None):
        self.f.args.spec_kit_version = version
        return w.make_plan(self.f.args, metadata)

    def test_default_stays_latest_and_explicit_pin_uses_its_own_artifacts(self):
        default = self.plan()
        self.assertEqual(default["components"]["spec_kit"]["version"], "1.3.2")
        self.assertNotIn("spec_kit_version", default["scope"])
        pinned = self.plan("1.3.1")
        component = pinned["components"]["spec_kit"]
        self.assertEqual(pinned["scope"]["spec_kit_version"], "1.3.1")
        self.assertEqual(component["version_selection"], "explicit-pypi-stable-release")
        self.assertEqual(component["artifacts"], [
            {"filename": "specify_cli-1.3.1.whl", "sha256": "1" * 64, "requires_python": ">=3.11"}])
        w.validate_plan(pinned)
        self.assertTrue(any("specify-cli==1.3.1" in command for command in pinned["commands"]))

    def test_invalid_unavailable_yanked_and_prerelease_pins_fail(self):
        for version in ("1.3", "1.3.1rc1", "1.3.1+local", "missing", "9.9.9", "2.0.0", "2.1.0", "3.0.0rc1", 131):
            with self.subTest(version=version), self.assertRaises(fixtures.InstallError):
                self.plan(version)
        self.assertEqual(self.f.calls, [])

    def test_explicit_release_requires_real_artifact_hash_metadata(self):
        data = metadata("pypi")
        del data["releases"]["1.3.1"][0]["digests"]
        self.f.args.spec_kit_version = "1.3.1"
        with self.assertRaisesRegex(fixtures.InstallError, "SHA-256"):
            w.make_plan(self.f.args, lambda url: data if "pypi" in url else metadata(url))

    def test_pin_without_selected_component_fails_before_resolution(self):
        self.f.args.components = "reverse"
        self.f.args.spec_kit_version = "1.3.1"
        with self.assertRaisesRegex(fixtures.InstallError, "需要选择 spec-kit"), patch.object(w, "resolve", side_effect=AssertionError("must not fetch")):
            w.make_plan(self.f.args)

    def test_frozen_pin_cannot_disagree_with_component(self):
        plan = self.plan("1.3.1")
        self.f.calls.clear()  # Ignore the read-only identity discovery during planning.
        plan["components"]["spec_kit"]["version"] = "1.3.2"
        with self.assertRaisesRegex(fixtures.InstallError, "显式 pin"):
            w.validate_plan(plan)
        self.assertEqual(self.f.calls, [])

    def test_legacy_unpinned_plans_still_validate(self):
        plan = self.plan()
        self.assertNotIn("spec_kit_version", plan["scope"])
        w.validate_plan(plan)

    def test_frozen_cli_replay_never_resolves_latest_and_rejects_override(self):
        plan = self.plan("1.3.1")
        self.f.calls.clear()
        file = self.f.base / "plan.json"
        fixtures.atomic(file, fixtures.encode_json(plan))
        args = ["update", "--root", str(self.f.root), "--plan-file", str(file)]
        with patch.object(w, "make_plan", side_effect=AssertionError("must not resolve metadata")):
            for extra, expected in (([], 0), (["--spec-kit-version", "1.3.1"], 0), (["--spec-kit-version", "1.3.2"], 1)):
                with self.subTest(extra=extra), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cli.main(args + extra), expected)
        self.assertEqual(self.f.calls, [])

    def test_actual_version_gate_still_rejects_mismatch(self):
        plan = self.plan("1.3.1")
        # Existing fake CLI reports 1.3.0. Pinning does not bypass that check.
        with self.assertRaisesRegex(fixtures.InstallError, "cli_version"):
            w.install(plan, self.f.args)
        self.assertFalse((self.f.root / ".installer/receipt.json").exists())

    def test_matching_pinned_install_retains_exact_receipt_identity(self):
        plan = self.plan("1.3.1")
        original = self.f.fake_run
        def run(argv, **kwargs):
            if "version" in argv:
                self.f.calls.append([str(a) for a in argv])
                return '{"cli_version":"1.3.1"}'
            return original(argv, **kwargs)
        with patch.object(w, "run", run):
            result = w.install(plan, self.f.args)
        self.assertEqual(result["components"]["spec_kit"]["version"], "1.3.1")
        self.assertEqual(result["components"]["spec_kit"]["version_selection"], "explicit-pypi-stable-release")
        self.assertTrue(any("specify-cli==1.3.1" in command for command in self.f.calls))
        self.assertTrue(w.verify(self.f.root)["ok"])


if __name__ == "__main__":
    unittest.main()
