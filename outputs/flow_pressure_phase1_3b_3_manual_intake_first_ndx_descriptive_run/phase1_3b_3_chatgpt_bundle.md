# ChatGPT Bundle: Flow Pressure Phase 1.3B.3 Manual Intake and First NDX Descriptive Run

## Objective

Use only manually supplied local free source files to create a canonical five-file package and run the first NDX-exact historical descriptive leveraged ETF proxy if all gates pass.

## Result

Main outcome:

```text
manual_raw_source_inputs_absent
```

Forward collection:

```text
forward_snapshot_not_started
```

Start commit:

```text
e9843629150ff08c8e46d6292fd7f6255966cdcd
```

No normalization or analysis was run because no qualifying manual raw source package was present.

## Local Evidence Checked

Expected archive:

```text
market_bomb_history/leveraged_etf_free_proxy_v1/manual_source_archive/
```

Status:

```text
absent
```

Existing input:

```text
market_bomb_history/leveraged_etf_free_proxy_v1/input/manual_free_proxy_intake_20260701_template/
```

Status:

```text
header-only template
```

Git safety:

```text
git ls-files market_bomb_history/leveraged_etf_free_proxy_v1
<empty>
```

Raw input root remains ignored:

```text
!! market_bomb_history/leveraged_etf_free_proxy_v1/
```

## Canonical Inspection

Read-only command used:

```powershell
python market_bomb_leveraged_etf_free_proxy_v1.py inspect-leveraged-etf-free-proxy-input-contract --input-id manual_free_proxy_intake_20260701_template
```

Inspection result:

```text
validation_status=blocked
ndx_exact_direction_possible=false
qqq_proxy_only_direction_possible=false
aum_scaled_possible=false
split_diagnostics_possible=false
forward_snapshot_ingestion_possible=false
creates_run_artifact=false
```

Canonical files were present but empty:

```text
benchmark_prices.csv rows=0
benchmark_mapping.csv rows=0
leveraged_etf_prices.csv rows=0
aum_or_capital.csv rows=0
split_history.csv rows=0
```

## Minimum Missing Inputs

Required before rerun:

- NDX daily price export;
- TQQQ -> NDX mapping evidence;
- SQQQ -> NDX mapping evidence;
- real source hash/provenance manifest.

Recommended:

- TQQQ/SQQQ daily prices;
- TQQQ/SQQQ AUM, NAV, or shares;
- TQQQ/SQQQ split history;
- QQQ daily price export for proxy context.

## Commands Not Run

- `validate-leveraged-etf-free-proxy-input`
- `run-leveraged-etf-free-proxy-historical --benchmark-mode ndx_exact`
- `verify-leveraged-etf-free-proxy-run`
- `ingest-leveraged-etf-free-proxy-forward-snapshot`

Reason: running on header-only template data would create invalid research output.

## Validation

Code was not changed. Focused free-proxy tests passed:

```text
41 passed
```

## Guardrails Confirmed

- No network/provider/API/download/scrape.
- No raw data committed.
- No fabricated data or timestamps.
- No strict Phase 1.3, Phase 2, release, or backtest.
- No trading, notifications, ranking, sizing, execution, or actionization.
- CTA and Dealer remain out of scope.
- `actionization_allowed=false`.

## Next Instruction

Place real manually acquired files in a local ignored archive or provide a concrete source folder, then rerun Phase 1.3B.3. The minimum package must include NDX daily prices and TQQQ/SQQQ -> NDX mapping evidence with provenance and hashes.
