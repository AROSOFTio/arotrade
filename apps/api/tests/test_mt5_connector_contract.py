import unittest
from pathlib import Path


class MT5ConnectorContractTests(unittest.TestCase):
    def test_post_body_excludes_string_terminator_in_every_distribution(self):
        repo_root = Path(__file__).resolve().parents[3]
        copies = [
            repo_root / "mt5" / "network.mqh",
            repo_root / "apps" / "mt5" / "network.mqh",
            repo_root / "apps" / "web" / "public" / "mt5" / "network.mqh",
        ]
        sources = [path.read_text(encoding="utf-8") for path in copies]

        self.assertTrue(all(source == sources[0] for source in sources[1:]))
        self.assertIn("data[bytes - 1] == 0", sources[0])
        self.assertIn("ArrayResize(data, bytes - 1)", sources[0])


if __name__ == "__main__":
    unittest.main()
