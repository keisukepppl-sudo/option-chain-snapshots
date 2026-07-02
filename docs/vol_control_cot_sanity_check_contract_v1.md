# Vol-Control COT Sanity Check Contract v1

COT data may be used only as a coarse weekly context check. It is not a ground-truth source for daily volatility-control exposure.

## Canonical File

`market_bomb_history/vol_control_research_v1/input/<input_id>/sources/cot_weekly.csv`

Columns:

`market_name,cftc_market_code,position_as_of_date,publication_timestamp_utc,available_timestamp_utc,reporting_group,long_contracts,short_contracts,spreading_contracts,open_interest_contracts,source_authority,revision_status`

## Required Semantics

- `position_as_of_date` is the position date.
- `publication_timestamp_utc` is when the report became published.
- `available_timestamp_utc` is when it was available to this research input.
- These fields must not be collapsed into one timestamp.

## CLI

```powershell
python market_bomb_vol_control_research_v1.py build-vol-control-cot-sanity-template --input-id <input_id>
python market_bomb_vol_control_research_v1.py inspect-vol-control-cot-sanity-input --input-id <input_id>
```

Inspection reports that COT is:

- Not vol-control ground truth
- Weekly sanity check only
- Not allowed for daily validation
- Not allowed to unlock Phase 2 or actionization

