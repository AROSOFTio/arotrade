import unittest
from unittest.mock import patch

import httpx

from app.services import metaapi_gateway as metaapi


class MetaApiGatewayProvisioningTests(unittest.TestCase):
    @patch.object(metaapi.settings, "METAAPI_TOKEN", "test-token")
    @patch("app.services.metaapi_gateway.time.sleep")
    @patch("app.services.metaapi_gateway.httpx.request")
    def test_create_account_reuses_transaction_id_while_polling_202(self, mock_request, mock_sleep):
        mock_request.side_effect = [
            httpx.Response(202, json={"message": "accepted"}, headers={"Retry-After": "0"}),
            httpx.Response(201, json={"id": "acct-1", "state": "DEPLOYED"}),
        ]

        result = metaapi.create_account(
            name="Demo",
            login="12345678",
            password="secret",
            server="Broker-MT5",
            platform="mt5",
        )

        self.assertEqual(result["state"], "DEPLOYED")
        self.assertEqual(mock_request.call_count, 2)
        first_headers = mock_request.call_args_list[0].kwargs["headers"]
        second_headers = mock_request.call_args_list[1].kwargs["headers"]
        self.assertEqual(first_headers["transaction-id"], second_headers["transaction-id"])
        self.assertEqual(len(first_headers["transaction-id"]), 32)
        self.assertTrue(mock_request.call_args_list[0].kwargs["json"]["manualTrades"])
        self.assertEqual(mock_request.call_args_list[0].kwargs["json"]["magic"], 0)
        mock_sleep.assert_called()


if __name__ == "__main__":
    unittest.main()
