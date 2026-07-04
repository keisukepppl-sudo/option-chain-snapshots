# Morita S Setup-Episode Identity v0.1

This module creates a downstream setup-episode state layer for formal historical current-S notifications.

It verifies the 328-row raw S source, records bounded legacy setup-identity recovery evidence, applies a reusability gate, and backfills one setup-episode state row per raw S notification.

If no source-proven reusable legacy or native base/reset rule exists, the state layer refuses to emit `VALID_REBREAKOUT`.

Minimal current behavior:

- first observed same-ticker raw S in available history -> `INITIAL_OBSERVED_BREAKOUT`;
- repeated same-ticker raw S within 20 eligible sessions and no new-base evidence -> `EXTENDED_NO_NEW_BASE`;
- later same-ticker raw S after more than 20 eligible sessions -> `UNRESOLVED`, because gap alone cannot prove a valid new base.

Run:

```powershell
python scripts/build_morita_s_setup_episode_identity_v0_1.py --run --verify
```
