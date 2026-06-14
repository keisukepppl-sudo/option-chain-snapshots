# Momentum Context Backtest

This folder contains a research backtest for the Russell1000 Minervini / Momentum Scanner.

## What it tests

The script keeps the current core scanner idea intact and compares whether context scores improve results:

- Core only
- Core + Absorption Score thresholds
- Core + Defensive RS thresholds
- Core + Sector RS thresholds
- Core + combinations of the above
- ATR filter variant

It also runs a **Black-Scholes option proxy** for bull call spreads. This is not a historical option-chain backtest.

## Core rule approximation

The vectorized backtest approximates the current production scanner rule:

- Trend Template style pass
- Standard RS >= 95
- Breakout RS >= 95
- Accumulation >= 30
- VCP >= 50
- Distance to pivot between 0% and 12%
- 50-day average volume >= 2,000,000
- Price >= $10
- Optional current market-cap proxy >= $2B

## Major limitations

- Uses current IWB holdings, so survivorship bias exists.
- Historical Russell1000 constituents are not used.
- Market cap, when enabled, is current market cap used as a proxy, not historical.
- The scanner is a vectorized approximation, not a perfect replay of every current module.
- Option proxy uses Black-Scholes with realized-volatility proxy IV and conservative slippage; it is not real option-chain data.
- Results are for decision support only and should not be treated as proof of live-trading profitability.

## Local run

```bash
python backtests/equity_context_backtest.py --period 5y
```

Quick smoke test:

```bash
python backtests/equity_context_backtest.py --period 3y --max-tickers 150 --skip-option-proxy
```

With current market-cap proxy:

```bash
python backtests/equity_context_backtest.py --period 5y --fetch-market-caps
```

## GitHub Actions

Use the workflow:

```text
Actions -> Momentum Context Backtest -> Run workflow
```

Outputs are uploaded as the `momentum-context-backtest` artifact.

## Output files

```text
output/backtests/equity_backtest_trades.csv
output/backtests/equity_backtest_by_variant.csv
output/backtests/equity_backtest_by_year.csv
output/backtests/option_proxy_backtest_trades.csv
output/backtests/option_proxy_backtest_summary.csv
output/backtests/backtest_diagnostics.md
```
