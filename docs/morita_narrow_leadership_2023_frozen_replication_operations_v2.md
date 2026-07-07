# Morita Narrow Leadership 2023 Frozen Replication Operations v2

Run:

```powershell
python scripts\build_morita_narrow_leadership_2023_frozen_replication_v2.py --run
```

Verify:

```powershell
python scripts\build_morita_narrow_leadership_2023_frozen_replication_v2.py --verify --output-dir outputs\morita_narrow_leadership_2023_frozen_replication_v2
```

Focused tests:

```powershell
python -m pytest tests\test_morita_narrow_leadership_2023_frozen_replication_v2.py -q --durations=30
```

This run is research-only and cannot be used as a live action rule.
