import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = (ROOT / "adapters" / "pi" / "skills" / "reverse-workflow" / "SKILL.md").read_text(encoding="utf-8")
PROMPT = (ROOT / "adapters" / "pi" / "prompts" / "reverse-workflow.md").read_text(encoding="utf-8")
PLAYBOOK = (ROOT / "docs" / "reverse-workflow-playbook.md").read_text(encoding="utf-8")


class GuidedDocumentationContract(unittest.TestCase):
    def test_card_families_are_stable_and_separate(self):
        for card in (
            "GOAL-REPORT", "GOAL-LOGIC", "GOAL-RECONSTRUCT", "GOAL-COMPARE", "GOAL-UPDATE",
            "SCOPE-STATIC-ONLY", "SCOPE-ISOLATED-RUNTIME", "SCOPE-AUTHORIZED-DEVICE", "SCOPE-WORKCOPY",
            "DELIVERY-REPORT", "DELIVERY-CORE", "DELIVERY-COVERAGE", "DELIVERY-UNKNOWN",
        ):
            self.assertIn(card, PLAYBOOK)
        self.assertNotIn("REA-GOAL", PLAYBOOK)
        self.assertNotIn("Ghidra-GOAL", PLAYBOOK)

    def test_technical_methods_are_explicitly_internal(self):
        self.assertRegex(PLAYBOOK, r"不.*选择.*(?:工具|provider|Static/Dynamic|脱壳)")
        self.assertIn("没有真正分叉时", PLAYBOOK)
        self.assertIn("skills/ops/guided-operator-contract.md", ADAPTER)
        self.assertIn("skills/ops/beginner-operator-guidance.md", ADAPTER)

    def test_authorization_coverage_references_are_preserved(self):
        self.assertIn("已验证 1/7", PLAYBOOK)
        for text in (PLAYBOOK, ADAPTER):
            self.assertIn("skills/ops/authorization-coverage.md", text)

    def test_adapter_routes_to_native_workflow_without_a_role_protocol(self):
        for reference in ("receipt-location.json", "RULES.md", "skills/MASTER-ROUTING.md", "reverse.master"):
            self.assertIn(reference, ADAPTER)
        self.assertIn("reverse-workflow skill", PROMPT)
        for obsolete in ("planner/scout", "backend/UI implementation workers", "carry_forward_refs", "每次 worker handoff"):
            self.assertNotIn(obsolete, ADAPTER + PROMPT)

    def test_installer_points_to_reverse_closure_instead_of_implementing_it(self):
        self.assertIn("skills/ops/authorization-coverage.md", ADAPTER)
        self.assertIn("原 case", ADAPTER)
        self.assertIn("原契约", ADAPTER)


if __name__ == "__main__":
    unittest.main()
