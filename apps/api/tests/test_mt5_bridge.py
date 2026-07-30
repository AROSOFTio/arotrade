from app.services.mt5_bridge.store import normalise_candle


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