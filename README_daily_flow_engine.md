# Daily Flow Engine v2

Adds:
- CTA trigger proxy
- AUM-based leveraged ETF flow approximation
- Vol-control proxy
- Market-down relative strength

Leveraged ETF flow:
- Creation/redemption ≈ AUM_t - AUM_{t-1} × (1 + ETF return)
- Rebalance ≈ AUM_t × L × (L - 1) × underlying return
