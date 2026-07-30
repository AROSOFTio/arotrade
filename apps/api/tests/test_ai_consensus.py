from app.services.ai.provider_manager import AIProviderManager


def test_consensus_majority_keeps_disagreements_visible(monkeypatch):
    manager = AIProviderManager()
    providers = manager.ordered(include_unconfigured=True)[:3]
    for provider in providers:
        monkeypatch.setattr(provider, "is_configured", lambda: True)

    outputs = iter([
        {"signal": "buy", "bias": "bullish", "confidence": 80},
        {"signal": "buy", "bias": "bullish", "confidence": 90},
        {"signal": "sell", "bias": "bearish", "confidence": 60},
    ])

    def fake_analyze(provider, **kwargs):
        data = next(outputs)
        return {
            **data,
            "entry_min": 1.0,
            "entry_max": 1.1,
            "stop_loss": 0.9,
            "take_profit_1": 1.3,
            "take_profit_2": None,
            "take_profit_3": None,
            "risk_reward": 2.0,
            "reasoning": ["test"],
            "invalidation": "test",
            "news_warning": None,
            "risk_warning": None,
            "raw": data,
        }

    monkeypatch.setattr(manager, "ordered", lambda include_unconfigured=False: providers)
    monkeypatch.setattr(manager, "analyze_with_provider", fake_analyze)
    result = manager.compare(symbol="EURUSD", timeframe="H1", prompt=None, image_bytes=None, image_mime=None, price_context="x")

    assert result["consensus"]["majority_signal"] == "buy"
    assert result["consensus"]["agreement_count"] == 2
    assert result["consensus"]["model_count"] == 3
    assert result["consensus"]["average_confidence"] == 76.7
    assert result["consensus"]["minority_opinions"] == [{"signal": "sell", "count": 1}]
