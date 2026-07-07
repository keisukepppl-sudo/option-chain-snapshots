# Morita Narrow Leadership 2023 Replication Operations v1

Run:

```powershell
python scripts\build_morita_narrow_leadership_2023_replication_v1.py --run
```

Verify:

```powershell
python scripts\build_morita_narrow_leadership_2023_replication_v1.py --verify --output-dir outputs\morita_narrow_leadership_2023_replication
```

Focused tests:

```powershell
python -m pytest tests\test_morita_narrow_leadership_2023_replication_v1.py -q
```

Do not use this artifact for live filtering or sizing. It is a frozen-threshold replication check only.
