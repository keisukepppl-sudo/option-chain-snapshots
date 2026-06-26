# Dealer Gamma Manual Validation - QQQ

raw file path: `option_chain_snapshots/QQQ/QQQ_2026-06-12.csv`
raw payload hash: `c7e4045049201ca3a414ea4521c61dc2d71b04c4093f8d5f54857526b5f9402f`
as-of timestamp: `2026-06-12T14:20:09+00:00`
underlying price: `715.010009765625`
underlying quote timestamp: `2026-06-12T00:00:00+00:00`
option quote timestamp: `2026-06-12T14:20:09+00:00`
call / put contract counts: see option_contract_count `2908`
OI missing/invalid: `0`
IV missing/invalid: `0`
contract multiplier: fallback 100
gamma calculation examples: aggregate audit uses row gamma when available, otherwise Black-Scholes gamma
call_gamma_open_interest_proxy: `6830254237.1947`
put_gamma_open_interest_proxy: `8198524019.5176`
net_gamma_open_interest_proxy: `-1368269782.323`
dealer_gamma_proxy_assumption: `dealer_short_customer_options_assumption`
sign_convention: `open_interest_sign_heuristic_call_plus_put_minus`
dealer_gamma_proxy: `1368269782.323`
dealer_position_observed: `false`
gamma flip: `174.78`
call wall: `740.0`
put wall: `650.0`
economic_quality: `medium`
