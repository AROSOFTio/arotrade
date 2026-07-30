from app.services.mt5_bridge.store import normalise_candle
from app.routes.mt5_bridge import _trim_mt5_json_body


def test_normalise_candle_accepts_mt5_payload_shape():
    candle = normalise_candle({
        "time": "2026-07-30 12:00:00",
        "open": "4070.10",
        "high": "4075.25",
        "low": "4068.50",
        "close": "4072.90",
        "tickVolume": "123",
    })

    assert candle == {
        "time": "2026-07-30 12:00:00",
        "open": 4070.10,
        "high": 4075.25,
        "low": 4068.50,
        "close": 4072.90,
        "volume": 123.0,
    }


def test_mt5_terminal_nul_is_removed_before_json_validation():
    assert _trim_mt5_json_body(b'{"account_id":6}\x00') == b'{"account_id":6}'
    assert _trim_mt5_json_body(b'{"account_id":6}') == b'{"account_id":6}'
