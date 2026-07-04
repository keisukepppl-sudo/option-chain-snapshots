# Morita S1/PB/C Route Comparison v0.1

This module builds a research-only route comparison from the completed Morita S1/A-B Candidate Layer v0.1 artifacts.

Routes:

- `S1`: first raw S in a streaming same-ticker raw-S cluster proxy.
- `PB`: first same-ticker raw A/B within 1 to 20 eligible sessions after cluster S1 with `accumulation_score >= 50`.
- `C`: first subsequent raw S in the same cluster proxy.

The primary comparison is common forward underlying behavior over 5, 10, and 20 eligible sessions. The secondary comparison uses the existing synthetic fixed-IV reference model only as a uniform comparison reference.

This module does not alter scanner ranks, raw S/A/B rows, live notifications, orders, state ledgers, portfolio replay, sizing, NLR, mechanical-flow overlays, or A/B exit policy.

Run:

```powershell
python scripts/build_morita_s1_pb_c_route_comparison_v0_1.py --run --verify
```

Focused test:

```powershell
python -m pytest tests/test_morita_s1_pb_c_route_comparison_v0_1.py -q --durations=30
```
