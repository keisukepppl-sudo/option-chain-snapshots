# Morita Current-S Notification Quality Audit v0.1

This module audits the historical current S notification stream directly. It does not reduce the source to one S per ticker or one S per cluster before classification.

The audit records whether native base, rebreakout, extended, or cooldown evidence exists in the saved formal S stream. If native evidence is unavailable, it applies one fixed point-in-time proxy:

- first same-ticker raw S -> `CURRENT_S_INITIAL_BREAKOUT`;
- same-ticker raw S within 20 eligible sessions of the most recent prior raw S -> `CURRENT_S_EXTENDED_FOMO`;
- same-ticker raw S after more than 20 eligible sessions -> `CURRENT_S_UNRESOLVED`, because elapsed time alone is not native new-base evidence.

Outputs include notification-level classifications, forward underlying outcomes, per-entry adverse path risk, deterministic sample rows, and a uniform fixed-IV reference summary when mechanically reusable.

Run:

```powershell
python scripts/build_morita_current_s_notification_quality_audit_v0_1.py --run --verify
```

Focused tests:

```powershell
python -m pytest tests/test_morita_current_s_notification_quality_audit_v0_1.py -q --durations=30
```
