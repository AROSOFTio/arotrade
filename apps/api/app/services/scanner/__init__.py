"""Scanner package — automatic market signal discovery.

Module structure:
  indicators.py  — Pure technical-analysis calculations (EMA, RSI, MACD, ATR, etc.)
  strategies.py  — Pluggable strategy engine that combines indicators
  validator.py   — Deterministic pre/post-Gemini signal validation
  pipeline.py    — Full scan pipeline: candles → TA → Gemini → Signal
"""
