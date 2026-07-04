# Current-S Classification Rulebook v0.1

Native fields have priority. A notification can be native-confirmed only if saved current scanner or state fields prove initial breakout, rebreakout, or extended continuation.

The formal S baseline currently does not carry `original_breakout_date`, `breakout_id`, `base_id`, native extended flag, reset/rebase flag, or cooldown state. Therefore this audit uses the frozen proxy below for audit classification only.

Proxy rules:

- `PROXY_INITIAL_BREAKOUT`: no prior raw S for the same ticker in the formal current-S stream.
- `PROXY_EXTENDED_FOMO`: prior same-ticker raw S exists and the most recent prior raw S is within 20 eligible sessions.
- `CURRENT_S_UNRESOLVED`: prior same-ticker raw S exists but the gap is greater than 20 eligible sessions, because gap alone cannot prove a fresh base or rebreakout.

Forbidden:

- future returns;
- later raw S events;
- manual visual labeling;
- outcome-driven threshold selection;
- PF targeting;
- live notification or trading rule changes.
