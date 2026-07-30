import unittest
from pathlib import Path


class MT5ConnectorContractTests(unittest.TestCase):
    def _repo_root(self) -> Path:
        test_file = Path(__file__).resolve()
        for parent in test_file.parents:
            if (parent / "mt5").is_dir() and (parent / "apps" / "mt5").is_dir():
                return parent
        self.skipTest("repository-level MT5 distributions are not included in this image")

    def test_every_connector_distribution_has_identical_code(self):
        repo_root = self._repo_root()
        files = [
            "AroPilotEA.mq5",
            "config.mqh",
            "connector.mqh",
            "drawings.mqh",
            "indicators.mqh",
            "network.mqh",
            "panel.mqh",
            "risk.mqh",
            "signals.mqh",
            "utils.mqh",
        ]
        roots = [
            repo_root / "mt5",
            repo_root / "apps" / "mt5",
            repo_root / "apps" / "web" / "public" / "mt5",
        ]

        for filename in files:
            sources = [
                "".join((root / filename).read_text(encoding="utf-8").split())
                for root in roots
            ]
            self.assertTrue(
                all(source == sources[0] for source in sources[1:]),
                f"{filename} differs between connector distributions",
            )

    def test_post_body_preserves_working_mt5_conversion_buffer(self):
        repo_root = self._repo_root()
        copies = [
            repo_root / "mt5" / "network.mqh",
            repo_root / "apps" / "mt5" / "network.mqh",
            repo_root / "apps" / "web" / "public" / "mt5" / "network.mqh",
        ]
        sources = [path.read_text(encoding="utf-8") for path in copies]

        self.assertTrue(all(source == sources[0] for source in sources[1:]))
        self.assertIn("StringToCharArray(payload, data, 0, WHOLE_ARRAY", sources[0])
        self.assertNotIn("data[bytes - 1]", sources[0])
        self.assertNotIn("ArrayResize(data", sources[0])

    def test_ea_version_is_market_compatible_in_every_distribution(self):
        repo_root = self._repo_root()
        copies = [
            repo_root / "mt5" / "AroPilotEA.mq5",
            repo_root / "apps" / "mt5" / "AroPilotEA.mq5",
            repo_root / "apps" / "web" / "public" / "mt5" / "AroPilotEA.mq5",
        ]
        sources = [path.read_text(encoding="utf-8") for path in copies]

        self.assertTrue(all(source == sources[0] for source in sources[1:]))
        self.assertIn('#property version   "1.00"', sources[0])
        self.assertNotIn('#property version   "1.0.0"', sources[0])


if __name__ == "__main__":
    unittest.main()
