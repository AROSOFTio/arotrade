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


class MetaApiGatewayTradeTests(unittest.TestCase):
    @patch.object(metaapi.settings, "METAAPI_TOKEN", "test-token")
    @patch.object(metaapi.settings, "METAAPI_REGION", "london")
    @patch("app.services.metaapi_gateway.httpx.request")
    def test_market_order_payload_omits_client_id_for_rest_schema(self, mock_request):
        mock_request.return_value = httpx.Response(
            200,
            json={"stringCode": "TRADE_RETCODE_DONE", "orderId": "order-1", "positionId": "pos-1"},
        )

        result = metaapi.place_market_order(
            metaapi_account_id="acct-1",
            symbol="XAUUSDm",
            direction="sell",
            volume=0.01,
            stop_loss=4081.0,
            take_profit=4021.0,
            client_id="MTABC123",
            comment="MT-MTABC123",
        )

        payload = mock_request.call_args.kwargs["json"]
        self.assertEqual(result["positionId"], "pos-1")
        self.assertEqual(payload["actionType"], "ORDER_TYPE_SELL")
        self.assertEqual(payload["symbol"], "XAUUSDm")
        self.assertEqual(payload["stopLoss"], 4081.0)
        self.assertEqual(payload["takeProfit"], 4021.0)
        self.assertNotIn("clientId", payload)

if __name__ == "__main__":
    unittest.main()
