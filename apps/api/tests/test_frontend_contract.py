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



    def test_portfolio_page_uses_real_summary_endpoint_and_sidebar_link(self):
        repo_root = Path(__file__).resolve().parents[3]
        page = (repo_root / "apps" / "web" / "app" / "dashboard" / "portfolio" / "page.tsx").read_text(encoding="utf-8")
        shell = (repo_root / "apps" / "web" / "app" / "components" / "dashboard-shell.tsx").read_text(encoding="utf-8")

        self.assertIn("/portfolio/summary", page)
        self.assertIn("equity_estimate", page)
        self.assertIn("exposure_by_symbol", page)
        self.assertNotIn("Coming Soon", page)
        self.assertIn("/dashboard/portfolio", shell)


    def test_scanner_worker_uses_direct_mt5_bridge_feed(self):
        repo_root = Path(__file__).resolve().parents[3]
        source = (repo_root / "apps" / "api" / "app" / "workers" / "scanner_tasks.py").read_text(encoding="utf-8")

        self.assertIn("get_bridge_candles", source)
        self.assertIn("get_bridge_quote", source)
        self.assertIn("direct-mt5", source)
        self.assertNotIn("not account or account.connection_state != \"deployed\" or not account.metaapi_account_id", source)

if __name__ == "__main__":
    unittest.main()
