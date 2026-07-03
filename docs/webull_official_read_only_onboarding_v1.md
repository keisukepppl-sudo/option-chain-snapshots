# Webull Official Read-Only Onboarding v1

The only permitted live provider path is official Webull documentation and official Webull read-only APIs or SDKs.

Forbidden:

- Browser automation.
- Screen scraping.
- Unofficial endpoints.
- Third-party SDKs or tutorials.
- Generic arbitrary endpoint calls.
- Any order submission, cancellation, amendment, replacement, exercise, assignment, transfer, withdrawal, or account-setting mutation.

## Stop Conditions

Real sync remains blocked while any of these are unresolved:

- `official_api_account_eligibility_unknown`
- `official_auth_flow_unknown`
- `official_read_only_scope_unknown`
- `official_endpoint_contract_unknown`
- `official_option_position_coverage_unknown`
- `official_option_order_or_fill_coverage_unknown`

If U.S. option coverage is unsupported or unclear, account-level reads may be documented separately, but option monitoring remains incomplete and manual CSV import remains the fallback.

No credentials or account identifiers may be committed or written into reports.
