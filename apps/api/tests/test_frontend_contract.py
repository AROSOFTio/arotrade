import unittest
from pathlib import Path


class FrontendRiskWarningContractTests(unittest.TestCase):
    def test_markets_page_uses_risk_warnings_and_blocks_confirmation(self):
        repo_root = Path(__file__).resolve().parents[3]
        source = (repo_root / "apps" / "web" / "app" / "dashboard" / "markets" / "page.tsx").read_text(encoding="utf-8")

        self.assertIn("risk_warnings", source)
        self.assertIn("previewHasBlockingRisk", source)
        self.assertIn("executionLoading || previewHasBlockingRisk", source)
        self.assertNotIn("previewData.warnings", source)


if __name__ == "__main__":
    unittest.main()
