# Morita Former Leader Retest Short Operations v1

Run the focused study:

```bash
python scripts/build_morita_former_leader_retest_short_v1.py --run
```

Verify the content manifest:

```bash
python scripts/build_morita_former_leader_retest_short_v1.py --verify
```

Run focused tests:

```bash
python -m pytest tests/test_morita_former_leader_retest_short_v1.py -q --durations=30
```

Run the full test suite:

```bash
python -m pytest -q
```

## Expected Guardrails

- Do not edit live scanner notification behavior.
- Do not edit long S rank or sizing logic.
- Do not retune D/L thresholds.
- Do not access broker, account, Webull order, or credential paths.
- Do not promote any result to a live short bot.

## 2022 Coverage Rule

The builder checks the approved OHLCV source minimum date. If the source does not include `2021-01-01` or earlier, 2022 is reported as `blocked_missing_2021_rs_warmup`.

This is intentional. A 2022 result without 2021 warmup would violate the study specification.
