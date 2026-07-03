# Morita Portfolio Ledger Operations v1

## Local Setup

Run:

```powershell
python morita_portfolio_ledger_v1.py init-local-templates
python morita_portfolio_ledger_v1.py audit-webull-official-docs
```

The local root is ignored:

```text
market_bomb_history/morita_portfolio_ledger_v1/
```

## Manual Flow

1. Import Morita signals from the ignored signal CSV.
2. Import manual order intents from the ignored intent CSV.
3. Import fixture or manual broker CSV exports.
4. Reconcile fills to monitoring lots.
5. Import structured exit reasons.
6. Build the daily ledger run.
7. Verify the ledger content manifest.

## Safety

The ledger is not a broker of record, tax ledger, investment adviser, signal generator, sizing engine, or execution system. All order activity remains human-approved and manual.
