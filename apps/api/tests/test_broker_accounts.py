import unittest
from types import SimpleNamespace

from app.routes.broker_accounts import _apply_remote_state, _remote_requires_deployment


class BrokerAccountStateTests(unittest.TestCase):
    def test_deployed_state_is_persisted_and_not_redeployed(self):
        account = SimpleNamespace(connection_state="undeployed")
        remote = {"state": "DEPLOYED"}

        changed = _apply_remote_state(account, remote)

        self.assertTrue(changed)
        self.assertEqual(account.connection_state, "deployed")
        self.assertFalse(_remote_requires_deployment(remote))


if __name__ == "__main__":
    unittest.main()
