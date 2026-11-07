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
        self.assertIn("GOAL-*", ADAPTER)
        self.assertIn("SCOPE-*", ADAPTER)
        self.assertIn("DELIVERY-*", ADAPTER)
        self.assertNotIn("REA-GOAL", PLAYBOOK)
        self.assertNotIn("Ghidra-GOAL", PLAYBOOK)

    def test_technical_methods_are_explicitly_internal(self):
        for text in (ADAPTER, PROMPT, PLAYBOOK):
            self.assertRegex(text, r"不.*选择.*(?:工具|provider|Static/Dynamic|脱壳)")
        self.assertIn("没有真正分叉时", PLAYBOOK)
        self.assertIn("不能为阶段切换", PROMPT)

    def test_phase_report_and_authorization_closure_are_present(self):
        for phrase in ("本轮做了什么", "目前确认了什么", "目前还不知道什么", "当前阻碍"):
            self.assertIn(phrase, PROMPT)
            self.assertIn(phrase, PLAYBOOK)
        self.assertIn("已验证 1/7", PLAYBOOK)
        self.assertIn("authorization-coverage", ADAPTER)

    def test_installer_points_to_reverse_closure_instead_of_implementing_it(self):
        self.assertIn("skills/ops/authorization-coverage.md", ADAPTER)
        self.assertIn("回归失败重开", ADAPTER)
        self.assertIn("模型自述", ADAPTER)
        self.assertIn("不是执行沙箱", ADAPTER)


if __name__ == "__main__":
    unittest.main()
