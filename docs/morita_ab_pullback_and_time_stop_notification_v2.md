# Morita A/B Pullback and 10-Session Time-Stop Notification v2

This layer is notification-only. It does not place, cancel, modify, or recommend automatic broker orders.

Implemented behavior:

- S breakout-low breach is a risk alert only.
- Timers start only from confirmed Webull fill or explicit manual entry registration.
- Registered S/A/B setups freeze `progress_target_price = entry_price_underlying * 1.05`, `max_holding_sessions = 10`, and the formal baseline timeout convention.
- Session 8, 9, and 10 reminders are generated from eligible exchange sessions.
- Session 10 emits `[EXIT TODAY - 10-SESSION TIME STOP]` only when +5% progress is not reached.
- Missing market data produces `unknown_market_data`, not a false time-stop.
- A/B pullback BUY READY fails closed unless an exact committed frozen pullback rule source is resolved.
- Webull adapter is read-only.

A/B rule source status in this implementation: `A_B_PULLBACK_RULE_UNRESOLVED`.
