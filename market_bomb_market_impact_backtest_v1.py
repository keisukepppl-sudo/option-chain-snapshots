#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

try:
    import market_bomb_phase3_2_cta_vol_proxy as p32
except Exception:  # pragma: no cover
    p32 = None


ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
VERSION = "market_bomb_market_impact_backtest_v1_20260627"
RULES_PATH = Path("market_bomb_config/market_impact_backtest_rules_v1.json")
LEVERAGED_UNIVERSE_PATH = Path("market_bomb_config/leveraged_etf_universe_v1.json")
DEALER_RULES_PATH = Path("market_bomb_config/dealer_gamma_observed_rules_v1.json")
EXPIRY_CALENDAR_PATH = Path("market_bomb_config/options_expiry_calendar_v1.csv")
EXPIRY_CALENDAR_METADATA_PATH = Path("market_bomb_config/options_expiry_calendar_metadata_v1.json")
EXPIRY_SCHEDULE_AVAILABILITY_RULES_PATH = Path("market_bomb_config/expiry_schedule_availability_rules_v1.json")
EXPIRY_FRIDAY_CLASSIFICATION_PATH = Path("market_bomb_config/expiry_friday_classification_v1.csv")
EXPIRY_FRIDAY_CLASSIFICATION_METADATA_PATH = Path("market_bomb_config/expiry_friday_classification_metadata_v1.json")
SOURCE_COVERAGE_CONTRACTS_PATH = Path("market_bomb_config/market_impact_source_coverage_contracts_v1.json")
LEVERAGED_ETF_INPUT_CONTRACTS_PATH = Path("market_bomb_config/leveraged_etf_input_contracts_v1.json")
DATA_SOURCES_PATH = Path("market_bomb_config/market_impact_data_sources_v1.json")
FEATURE_MAPPINGS_PATH = Path("market_bomb_config/market_impact_feature_mappings_v1.json")
BASELINE_PATH = Path("market_bomb_config/market_impact_baseline_v1.json")
NYSE_CALENDAR_PATH = Path("market_bomb_config/nyse_regular_sessions_v1.csv")
NYSE_CALENDAR_METADATA_PATH = Path("market_bomb_config/nyse_regular_sessions_metadata_v1.json")
EXPIRY_INTRADAY_RULES_PATH = Path("market_bomb_config/market_impact_expiry_intraday_rules_v1.json")
OUTPUT_ROOT = Path("market_bomb_market_impact")
CTA_VOL_QUALITY_CONTRACT_REVISION = "cta_vol_quality_contract_v1_1_8"
CTA_VOL_SELECTION_POLICY_REVISION = "latest_clean_feature_selector_v1_1_8"
LEVERAGED_BUNDLE_POLICY_REVISION = "leveraged_etf_input_bundle_v1_1_8"
MARKET_LEVEL_INTEGRITY_REVISION = "market_level_decision_scope_integrity_v1_1_15"
DEALER_GAMMA_SIGN_POLICY_REVISION = "dealer_gamma_negative_sign_policy_v1_1_8"
DEALER_GAMMA_SOURCE_CONTRACT_REVISION = "dealer_gamma_source_contract_v1_1_15"
DEALER_GAMMA_SELECTION_POLICY_REVISION = "latest_clean_dealer_gamma_selector_v1_1_15"
MARKET_LEVEL_EOD_UNIVERSE_POLICY = "daily_outcomes_full_eod_decision_universe_v1_1_11"
MARKET_LEVEL_INTRADAY_UNIVERSE_POLICY = "canonical_explicit_intraday_universe_v1_1_15"
MARKET_LEVEL_OOS_BUCKET_POLICY = "strict_artifact_only_single_classifier_v1_1_15"
EOD_ACTUAL_FEATURE_LINEAGE_POLICY = "actual_lineage_schema_only_v1_1_15"
INTRADAY_INPUT_AUDIT_UNIVERSE_POLICY = "full_intraday_decision_universe_no_fallback_v1_1_15"
MARKET_LEVEL_BUCKET_CANDIDATE_SOURCE_POLICY = "explicit_eod_and_intraday_universe_only_v1_1_15"
TARGET_CLOCK_GATE_MISSING_POLICY = "fail_closed_audit_missing_v1_1_15"
LEVERAGED_CLOSE_1600_ROLE = "outcome_only_not_primary_input_v1_1_15"
MARKET_LEVEL_DECISION_UNIVERSE_POLICY = "canonical_explicit_universe_only_v1_1_15"
UNIVERSE_DUPLICATE_KEY_POLICY = "canonicalize_once_and_selected_invalid_v1_1_15"
MARKET_LEVEL_COVERAGE_RECONCILIATION_GRANULARITY = "target_clock_decision_scope_outcome_v1_1_15"
COVERAGE_MISMATCH_POLICY = "local_fail_closed_data_quality_blocked_v1_1_15"
DEALER_GAMMA_ALLOWED_DATA_TYPES = {"reconstructed_from_raw_chain", "raw_chain_reconstructed_proxy"}

FEATURE_AUDIT_COLUMNS = [
    "feature_family",
    "feature_name",
    "target_market",
    "feature_value",
    "feature_unit",
    "feature_as_of_timestamp_utc",
    "effective_available_at_utc",
    "decision_timestamp_utc",
    "feature_age_hours",
    "availability_basis",
    "availability_confidence",
    "source_path_or_provider",
    "source_hash_or_request_id",
    "data_type",
    "is_proxy",
    "observed_flow",
    "quality_grade",
    "availability_status",
    "availability_failure_reason",
]

PANEL_COMMON_COLUMNS = [
    "analysis_id",
    "module",
    "feature_family",
    "feature_name",
    "target_market",
    "decision_date",
    "decision_timestamp_utc",
    "feature_value",
    "feature_unit",
    "feature_as_of_timestamp_utc",
    "effective_available_at_utc",
    "feature_age_hours",
    "availability_basis",
    "availability_confidence",
    "source_path_or_provider",
    "source_hash_or_request_id",
    "data_type",
    "is_proxy",
    "observed_flow",
    "quality_grade",
    "availability_status",
    "availability_failure_reason",
    "primary_or_robustness",
]

LEVERAGED_AUDIT_COLUMNS = [
    "target_market",
    "decision_timestamp_utc",
    "bar_timestamp_convention",
    "decision_price_method",
    "decision_bar_timestamp_et",
    "close_price_method",
    "close_bar_timestamp_et",
    "actual_1530_bar_timestamp_utc",
    "actual_1600_bar_timestamp_utc",
    "prior_regular_close_timestamp_utc",
    "aum_as_of_timestamp_utc",
    "aum_effective_available_at_utc",
    "universe_completeness",
    "availability_status",
    "availability_failure_reason",
    "complete_universe_coverage",
    "volume_reference_window",
    "volume_reference_last_date",
    "volume_reference_row_count",
]

LEVERAGED_ETF_COMPONENT_MANIFEST_COLUMNS = [
    "target_market",
    "decision_timestamp_utc",
    "selection_bundle_id",
    "source_component_type",
    "fund_ticker",
    "selected_source_row_identifier",
    "selected_source_content_hash",
    "selected_source_as_of_timestamp_utc",
    "selected_source_effective_available_at_utc",
    "selection_status",
    "availability_state",
    "primary_eligible",
    "invalid_reason",
    "selected_value_or_reference",
    "selection_policy_revision",
]

MARKET_LEVEL_SCOPE_INTEGRITY_COLUMNS = [
    "target_market",
    "decision_timestamp_utc",
    "model_clock",
    "model_scope",
    "required_component",
    "component_integrity_status",
    "component_integrity_reason",
    "source_parity_status",
    "scope_integrity_status",
    "scope_integrity_failure_reason",
]

MARKET_LEVEL_COMPONENT_PROVENANCE_COLUMNS = [
    "target_market",
    "decision_timestamp_utc",
    "model_clock",
    "required_component",
    "selection_status",
    "availability_state",
    "primary_eligible",
    "source_parity_status",
    "input_integrity_status",
    "integrity_status",
    "integrity_reason",
    "selected_source_row_identifier",
    "selected_source_content_hash",
    "selected_source_effective_available_at_utc",
    "provenance_evidence_type",
    "provenance_dependency_component",
    "derived_from_base_integrity_status",
    "provenance_policy_revision",
]

MARKET_LEVEL_EOD_DECISION_UNIVERSE_COLUMNS = [
    "target_market", "decision_date", "decision_timestamp_utc", "model_clock",
    "decision_time_policy", "decision_universe_policy",
]

MARKET_LEVEL_INTRADAY_DECISION_UNIVERSE_COLUMNS = [
    "target_market", "decision_date", "decision_timestamp_utc", "model_clock",
    "decision_time_policy", "coverage_start_et", "coverage_end_et", "coverage_window_basis",
    "calendar_coverage_status", "is_regular_session", "is_early_close",
    "decision_universe_status", "decision_universe_reason",
    "intraday_outcome_availability_status", "intraday_outcome_availability_reason",
    "actual_1530_bar_timestamp_utc", "actual_1600_bar_timestamp_utc",
    "intraday_return_1530_to_close", "intraday_absolute_return_1530_to_close",
    "intraday_range_1530_to_close",
]

MARKET_LEVEL_INTRADAY_UNIVERSE_GATE_COLUMNS = [
    "target_market",
    "model_clock",
    "intraday_source_coverage_start_et",
    "intraday_source_coverage_end_et",
    "calendar_validation_status",
    "calendar_validation_failure_reason",
    "universe_generation_status",
    "universe_generation_reason",
    "candidate_decision_count",
    "target_clock_gate_integrity_status",
    "target_clock_gate_reason",
    "included_regular_session_count",
    "excluded_non_regular_session_count",
    "excluded_early_close_session_count",
]

MARKET_LEVEL_TARGET_CLOCK_GATE_COLUMNS = [
    "target_market",
    "model_clock",
    "model_scope",
    "outcome",
    "target_clock_gate_status",
    "target_clock_gate_reason",
    "candidate_decision_count",
    "universe_gate_selected_invalid_count",
    "universe_gate_unavailable_coverage_count",
]

MARKET_LEVEL_DECISION_BUCKET_COLUMNS = [
    "target_market",
    "decision_timestamp_utc",
    "model_clock",
    "model_scope",
    "outcome",
    "candidate_in_universe_flag",
    "bucket",
    "bucket_reason",
    "scope_integrity_status",
    "outcome_availability_status",
    "numeric_feature_availability_status",
    "missing_numeric_features",
    "panel_row_present",
    "panel_row_count",
    "panel_row_absence_reason",
    "universe_key_integrity_status",
    "universe_key_integrity_reason",
    "duplicate_universe_key_detected",
    "oos_bucket_policy",
]

MARKET_LEVEL_DECISION_UNIVERSE_INTEGRITY_COLUMNS = [
    "target_market",
    "model_clock",
    "decision_timestamp_utc",
    "raw_universe_row_count",
    "canonical_universe_row_count",
    "duplicate_detected",
    "duplicate_metadata_conflict_detected",
    "universe_key_integrity_status",
    "universe_key_integrity_reason",
]

MARKET_LEVEL_UNIVERSE_COVERAGE_RECONCILIATION_COLUMNS = [
    "target_market",
    "model_clock",
    "decision_timestamp_utc",
    "model_scope",
    "outcome",
    "in_canonical_decision_universe",
    "universe_key_integrity_status",
    "universe_key_integrity_reason",
    "expected_required_components",
    "expected_required_component_count",
    "actual_provenance_components",
    "actual_provenance_component_count",
    "missing_provenance_components",
    "duplicate_provenance_components",
    "expected_scope_integrity_components",
    "actual_scope_integrity_components",
    "missing_scope_integrity_components",
    "duplicate_scope_integrity_components",
    "market_level_panel_row_count",
    "panel_row_present",
    "panel_row_status",
    "expected_bucket_row_count",
    "actual_bucket_row_count",
    "bucket_row_status",
    "actual_bucket_value",
    "coverage_reconciliation_status",
    "coverage_reconciliation_reason",
]

DEALER_GAMMA_EOD_ACTUAL_FEATURE_LINEAGE_COLUMNS = [
    "target_market",
    "decision_timestamp_utc",
    "selector_context",
    "expected_selection_status",
    "expected_availability_state",
    "expected_primary_eligible",
    "expected_invalid_reason",
    "expected_selected_source_row_identifier",
    "expected_selected_source_content_hash",
    "expected_selected_source_as_of_timestamp_utc",
    "expected_selected_source_effective_available_at_utc",
    "expected_dealer_gamma_source_contract_revision",
    "expected_selection_policy_revision",
    "actual_feature_row_present",
    "actual_feature_row_identifier",
    "actual_selection_status",
    "actual_primary_eligible",
    "actual_selected_source_row_identifier",
    "actual_selected_source_content_hash",
    "actual_selected_source_as_of_timestamp_utc",
    "actual_selected_source_effective_available_at_utc",
    "actual_dealer_gamma_source_contract_revision",
    "actual_selection_policy_revision",
    "actual_feature_payload_hash",
    "actual_feature_hydration_status",
    "actual_feature_hydration_failure_reason",
    "lineage_status",
    "lineage_failure_reason",
]

DEALER_GAMMA_EOD_FEATURE_HYDRATION_COLUMNS = [
    "target_market",
    "decision_timestamp_utc",
    "selected_source_row_identifier",
    "selected_source_content_hash",
    "hydration_status",
    "hydration_failure_reason",
]

EXPIRY_SNAPSHOT_AUDIT_COLUMNS = [
    "target_market",
    "decision_timestamp_utc",
    "comparison_group",
    "selector_context",
    "feature_timing_bucket",
    "selected_snapshot_asof_utc",
    "selected_snapshot_effective_utc",
    "selected_snapshot_age_hours",
    "selected_snapshot_source_path",
    "selected_snapshot_quality",
    "availability_status",
    "availability_failure_reason",
    "selection_status",
    "primary_eligible",
    "selected_source_row_identifier",
    "selected_source_content_hash",
    "dealer_gamma_source_contract_revision",
    "selection_policy_revision",
]

NYSE_SESSION_AUDIT_COLUMNS = [
    "session_date",
    "calendar_coverage_status",
    "is_regular_session",
    "is_early_close",
    "regular_open_et",
    "regular_close_et",
    "calendar_source",
    "calendar_version",
    "availability_status",
    "availability_failure_reason",
]

EXPIRY_INTRADAY_OUTCOME_AUDIT_COLUMNS = [
    "target_market",
    "event_date",
    "comparison_group",
    "decision_timestamp_utc",
    "bar_timestamp_convention",
    "provider_bar_semantics_verified",
    "provider_bar_semantics_source",
    "provider_bar_semantics_verified_at_utc",
    "session_open_price_method",
    "session_open_price_source_field",
    "session_open_price_timestamp_utc",
    "event_open_bar_timestamp_utc",
    "event_close_bar_timestamp_utc",
    "outcome_window_label",
    "calendar_session_status",
    "is_early_close",
    "outcome_availability_status",
    "outcome_availability_failure_reason",
    "outcome_data_quality",
]

MODULE_QUALITY_AUDIT_COLUMNS = [
    "module",
    "target_market",
    "raw_candidate_row_count",
    "eligible_row_count",
    "excluded_future_timestamp_count",
    "excluded_missing_timestamp_count",
    "excluded_age_count",
    "excluded_quality_count",
    "excluded_target_mismatch_count",
    "selected_row_count",
    "data_quality_blocking_violation_count",
    "research_execution_gate",
    "evidence_verdict",
]

RAW_FEATURE_CANDIDATE_AUDIT_COLUMNS = [
    "module",
    "feature_family",
    "target_market",
    "decision_timestamp_utc",
    "raw_candidate_row_count",
    "eligible_row_count",
    "selected_row_count",
    "excluded_future_timestamp_count",
    "excluded_missing_timestamp_count",
    "excluded_age_count",
    "excluded_quality_count",
    "excluded_target_mismatch_count",
    "data_quality_blocking_violation_count",
    "selected_row_strictly_valid",
    "clean_replacement_available",
    "module_gate_recommendation",
]

EXPIRY_GROUP_OOS_COLUMNS = [
    "target_market",
    "comparison_group",
    "reference_group",
    "feature_family",
    "feature_name",
    "outcome",
    "sample_count",
    "oos_sample_count",
    "test_month_count",
    "minimum_oos_required",
    "minimum_test_months_required",
    "event_group_row_count",
    "reference_group_row_count",
    "event_group_oos_row_count",
    "reference_group_oos_row_count",
    "event_group_test_month_count",
    "reference_group_test_month_count",
    "group_sufficiency_status",
    "research_execution_gate",
    "evidence_verdict",
]

SOURCE_FEATURE_CANDIDATE_AUDIT_COLUMNS = [
    "module",
    "feature_family",
    "target_market",
    "decision_timestamp_utc",
    "source_path_or_provider",
    "source_row_identifier",
    "source_row_hash_or_index",
    "candidate_rank_before_selection",
    "feature_as_of_timestamp_utc",
    "effective_available_at_utc",
    "feature_age_hours",
    "quality_value",
    "quality_policy",
    "target_match_status",
    "timestamp_status",
    "age_status",
    "quality_status",
    "candidate_eligibility_status",
    "candidate_exclusion_reason",
    "selected_for_panel",
    "selected_for_model",
    "selection_reason",
    "clean_replacement_available",
]

SOURCE_FEATURE_CANDIDATE_SUMMARY_COLUMNS = [
    "module",
    "feature_family",
    "target_market",
    "decision_timestamp_utc",
    "raw_candidate_row_count",
    "eligible_row_count",
    "selected_row_count",
    "excluded_future_timestamp_count",
    "excluded_missing_timestamp_count",
    "excluded_age_count",
    "excluded_quality_count",
    "excluded_target_mismatch_count",
    "selected_row_strictly_valid",
    "clean_replacement_available",
    "unavailable_reason",
    "module_gate_recommendation",
]

EXPIRY_GROUP_CONTRAST_RESULT_COLUMNS = [
    "module",
    "feature_family",
    "contrast_id",
    "target_market",
    "event_group",
    "reference_group",
    "outcome",
    "feature_name",
    "sample_count_train",
    "sample_count_oos",
    "event_group_oos_row_count",
    "reference_group_oos_row_count",
    "event_group_test_month_count",
    "reference_group_test_month_count",
    "oos_mse",
    "oos_mae",
    "oos_r2_vs_baseline",
    "delta_oos_mse_vs_baseline",
    "bootstrap_delta_mse_ci_low",
    "bootstrap_delta_mse_ci_high",
    "research_execution_gate",
    "evidence_verdict",
    "baseline_model_version",
    "baseline_feature_columns",
    "event_group_definition_source",
    "reference_group_definition_source",
    "expiry_classification_coverage_status",
    "holiday_adjusted_event_excluded_count",
    "clean_selected_prediction_count",
    "coverage_excluded_prediction_count",
    "selected_invalid_prediction_count",
    "nonselected_invalid_candidate_count",
]

CALENDAR_AVAILABILITY_AUDIT_COLUMNS = [
    "event_date",
    "comparison_group",
    "decision_timestamp_utc",
    "feature_as_of_timestamp_utc",
    "effective_available_at_utc",
    "availability_basis",
    "calendar_availability_timestamp_source",
    "calendar_availability_contract_version",
    "availability_status",
    "availability_failure_reason",
]

EXPIRY_CLASSIFICATION_AUDIT_COLUMNS = [
    "session_date",
    "expected_regular_friday",
    "classification_row_count",
    "classification_status",
    "classification_complete",
    "comparison_group",
    "availability_status",
    "availability_failure_reason",
]

SOURCE_SELECTION_PARITY_COLUMNS = [
    "module",
    "feature_family",
    "model_scope",
    "target_market",
    "decision_timestamp_utc",
    "required_source_family",
    "audit_selected_source_row_identifier",
    "panel_selected_source_row_identifier",
    "audit_selected_source_hash_or_index",
    "panel_selected_source_hash_or_index",
    "audit_selected_effective_available_at_utc",
    "panel_selected_effective_available_at_utc",
    "audit_selection_status",
    "panel_selection_status",
    "audit_selected_source_quality_value",
    "panel_selected_source_quality_value",
    "selection_quality_contract_revision",
    "selection_parity_status",
    "selection_parity_failure_reason",
    "scope_gate_recommendation",
]

LEVERAGED_ETF_INPUT_CANDIDATE_COLUMNS = [
    "input_component",
    "fund_ticker",
    "target_market",
    "decision_timestamp_utc",
    "required_bar_timestamp_et",
    "actual_bar_timestamp_utc",
    "bar_timestamp_convention",
    "provider_bar_semantics_verified",
    "aum_value",
    "aum_value_type",
    "aum_as_of_timestamp_utc",
    "aum_effective_available_at_utc",
    "prior_regular_close_session_date",
    "prior_regular_close_timestamp_utc",
    "prior_regular_close_price",
    "source_path_or_provider",
    "source_row_identifier",
    "source_hash_or_index",
    "selection_policy_version",
    "primary_eligible",
    "analysis_mode",
    "candidate_eligibility_status",
    "selected_for_model",
    "availability_failure_reason",
]

SELECTOR_RESULT_COLUMNS = [
    "selection_scope",
    "module",
    "feature_family",
    "model_scope",
    "target_market",
    "decision_timestamp_utc",
    "source_path_or_provider",
    "source_row_identifier",
    "source_hash_or_index",
    "selection_policy_version",
    "selection_status",
    "primary_eligible",
    "analysis_mode",
    "availability_state",
    "availability_status",
    "availability_failure_reason",
    "quality_status",
    "quality_failure_reason",
    "selected_for_panel",
    "selected_for_model",
]


def safe_float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or pd.isna(value) or str(value).strip() == "":
            return default
        return float(value)
    except Exception:
        return default


def parse_ts(value: Any) -> pd.Timestamp | None:
    if value in [None, ""] or (isinstance(value, float) and pd.isna(value)):
        return None
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(ts) else ts


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def row_content_hash(row: pd.Series | dict[str, Any] | None) -> str:
    if row is None:
        return ""
    data = row.to_dict() if isinstance(row, pd.Series) else dict(row)
    normalized = {}
    for key, value in data.items():
        if isinstance(value, pd.Timestamp):
            normalized[str(key)] = value.isoformat()
        elif isinstance(value, (np.integer, np.floating)):
            normalized[str(key)] = float(value)
        elif pd.isna(value) if not isinstance(value, (list, dict, tuple)) else False:
            normalized[str(key)] = ""
        else:
            normalized[str(key)] = str(value)
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def load_json(root: Path, path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    full = root / path
    if not full.exists():
        return fallback
    try:
        return json.loads(full.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def rules(root: Path) -> dict[str, Any]:
    return load_json(root, RULES_PATH, {
        "version": "market_impact_backtest_rules_v1",
        "targets": ["QQQ", "SPY", "SOXX", "SMH"],
        "daily_horizons": [1, 5, 10],
        "intraday_primary_asof_et": "15:30",
        "intraday_robustness_asof_et": "15:00",
        "max_feature_age_hours": 96,
        "walk_forward": {"method": "expanding_window", "minimum_train_observations": 252, "test_block": "monthly"},
        "statistical": {
            "bootstrap_method": "moving_block",
            "multiple_testing_method": "benjamini_hochberg",
            "bootstrap_block_length": 5,
            "bootstrap_iterations": 1000,
            "random_seed": 42,
            "ridge_alpha": 1.0,
        },
        "minimum_samples": {
            "cta_vol_min_oos_rows_per_target": 252,
            "cta_vol_min_test_months": 6,
            "leveraged_etf_min_oos_rows": 126,
            "leveraged_etf_min_test_months": 6,
            "leveraged_etf_complete_universe_coverage_min": 0.80,
            "dealer_gamma_min_oos_rows": 100,
            "dealer_gamma_min_test_months": 6,
            "dealer_expiry_min_event_rows_per_comparison_group": 20,
            "dealer_expiry_min_oos_rows_per_group": 20,
            "dealer_expiry_min_test_months_per_group": 3,
        },
        "primary_decision_bar_et": "15:30",
        "primary_close_bar_et": "16:00",
        "bar_timestamp_convention": "bar_end",
        "actionization_allowed": False,
    })


def baseline_config(root: Path) -> dict[str, Any]:
    return load_json(root, BASELINE_PATH, {
        "version": "market_impact_baseline_v1",
        "daily": [
            "prior_return_1d",
            "prior_return_5d",
            "prior_realized_vol_20d",
            "distance_from_20d_moving_average",
            "weekday",
            "month_end_flag",
            "monthly_expiry_flag",
            "quarterly_expiry_flag",
        ],
        "intraday": [
            "return_prior_regular_close_to_1530",
            "absolute_return_prior_regular_close_to_1530",
            "intraday_realized_vol_to_1530",
            "intraday_volume_ratio_vs_prior_20d_same_time",
            "prior_session_return",
            "prior_20d_realized_vol",
            "weekday",
            "monthly_expiry_flag",
            "quarterly_expiry_flag",
        ],
        "expiry_group_contrast": [
            "prior_return_1d",
            "prior_return_5d",
            "prior_realized_vol_20d",
            "distance_from_20d_moving_average",
            "month_end_flag",
        ],
    })


def feature_mappings(root: Path) -> dict[str, Any]:
    return load_json(root, FEATURE_MAPPINGS_PATH, {
        "version": "market_impact_feature_mappings_v1",
        "cta_only": ["cta_exposure_change_proxy", "cta_deleveraging_proxy"],
        "vol_only": ["vol_control_exposure_change_proxy"],
        "cta_plus_vol": ["cta_exposure_change_proxy", "cta_deleveraging_proxy", "vol_control_exposure_change_proxy"],
        "leveraged_etf": ["aggregate_pressure_usd"],
        "dealer_gamma_state": ["local_flip_found_flag", "no_local_flip_flag", "net_gex_proxy", "pinning_proxy"],
        "dealer_gamma_distance": ["gamma_flip_distance_pct", "net_gex_proxy", "pinning_proxy"],
        "expiry_event": ["monthly_expiry_flag", "quarterly_expiry_flag", "triple_witching_flag"],
        "expiry_conditioned": ["monthly_expiry_flag", "quarterly_expiry_flag", "triple_witching_flag", "net_gex_proxy", "pinning_proxy", "local_flip_found_flag", "no_local_flip_flag"],
    })


def data_sources_config(root: Path) -> dict[str, Any]:
    return load_json(root, DATA_SOURCES_PATH, {
        "version": "market_impact_data_sources_v1",
        "refresh_adapters": {
            "refresh_daily_prices": "not_supported",
            "refresh_intraday_prices": "not_supported",
            "run_gamma_surrogate_exploration": "not_supported",
        },
    })


def expiry_intraday_rules(root: Path) -> dict[str, Any]:
    return load_json(root, EXPIRY_INTRADAY_RULES_PATH, {
        "version": "market_impact_expiry_intraday_rules_v1",
        "bar_timestamp_convention": "bar_end",
        "event_primary_open_bar_et": "09:30",
        "event_primary_close_bar_et": "16:00",
        "event_primary_bar_interval_minutes": 5,
        "daily_ohlc_proxy_outcome_is_primary": False,
    })


def leveraged_universe(root: Path) -> dict[str, Any]:
    return load_json(root, LEVERAGED_UNIVERSE_PATH, {
        "version": "leveraged_etf_universe_v1",
        "nasdaq_100": [
            {"ticker": "TQQQ", "target": "QQQ", "leverage": 3.0},
            {"ticker": "SQQQ", "target": "QQQ", "leverage": -3.0},
        ],
        "semiconductor": [
            {"ticker": "SOXL", "target": "SOXX", "leverage": 3.0},
            {"ticker": "SOXS", "target": "SOXX", "leverage": -3.0},
        ],
    })


def write_table(df: pd.DataFrame, csv_path: Path, parquet_path: Path | None = None) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    if parquet_path is not None:
        try:
            df.to_parquet(parquet_path, index=False)
        except Exception:
            pass


def markdown_table(df: pd.DataFrame, max_rows: int = 50) -> str:
    if df.empty:
        return "_No rows._"
    clean = df.head(max_rows).fillna("").astype(str)
    cols = list(clean.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in clean.iterrows():
        lines.append("| " + " | ".join(str(row[c]).replace("|", "\\|").replace("\n", " ") for c in cols) + " |")
    if len(df) > max_rows:
        lines.append(f"\n_Only first {max_rows} of {len(df)} rows shown._")
    return "\n".join(lines)


def ensure_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = np.nan
    return out[columns + [c for c in out.columns if c not in columns]]


def feature_audit_row(
    *,
    feature_family: str,
    feature_name: str,
    target_market: str = "",
    decision_timestamp_utc: Any = "",
    feature_value: Any = np.nan,
    feature_unit: str = "",
    feature_as_of_timestamp_utc: Any = "",
    effective_available_at_utc: Any = "",
    availability_status: str = "unavailable",
    availability_failure_reason: str = "",
    availability_basis: str = "effective_available_at_utc",
    availability_confidence: str = "medium",
    source_path_or_provider: str = "",
    source_hash_or_request_id: str = "",
    data_type: str = "proxy",
    is_proxy: bool = True,
    observed_flow: bool = False,
    quality_grade: str = "unknown",
) -> dict[str, Any]:
    decision_ts = parse_ts(decision_timestamp_utc)
    eff_ts = parse_ts(effective_available_at_utc)
    age = (decision_ts - eff_ts).total_seconds() / 3600 if decision_ts is not None and eff_ts is not None else np.nan
    return {
        "feature_family": feature_family,
        "feature_name": feature_name,
        "target_market": target_market,
        "feature_value": feature_value,
        "feature_unit": feature_unit,
        "feature_as_of_timestamp_utc": feature_as_of_timestamp_utc,
        "effective_available_at_utc": effective_available_at_utc,
        "decision_timestamp_utc": decision_timestamp_utc,
        "feature_age_hours": round(age, 4) if pd.notna(age) else np.nan,
        "availability_basis": availability_basis,
        "availability_confidence": availability_confidence,
        "source_path_or_provider": source_path_or_provider,
        "source_hash_or_request_id": source_hash_or_request_id,
        "data_type": data_type,
        "is_proxy": is_proxy,
        "observed_flow": observed_flow,
        "quality_grade": quality_grade,
        "availability_status": availability_status,
        "availability_failure_reason": availability_failure_reason,
    }


def normalize_price_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "adjusted_close", "volume"])
    cols = {str(c).lower().replace(" ", "_"): c for c in df.columns}
    date_col = cols.get("date") or cols.get("datetime") or cols.get("timestamp")
    close_col = cols.get("close")
    adj_col = cols.get("adjusted_close") or cols.get("adj_close") or close_col
    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], errors="coerce").dt.tz_localize(None) if date_col else pd.NaT,
        "open": pd.to_numeric(df[cols["open"]], errors="coerce") if "open" in cols else np.nan,
        "high": pd.to_numeric(df[cols["high"]], errors="coerce") if "high" in cols else np.nan,
        "low": pd.to_numeric(df[cols["low"]], errors="coerce") if "low" in cols else np.nan,
        "close": pd.to_numeric(df[close_col], errors="coerce") if close_col else np.nan,
        "adjusted_close": pd.to_numeric(df[adj_col], errors="coerce") if adj_col else np.nan,
        "volume": pd.to_numeric(df[cols["volume"]], errors="coerce") if "volume" in cols else np.nan,
    })
    return out.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def load_price_history(root: Path, targets: list[str]) -> dict[str, pd.DataFrame]:
    price_dir = root / "market_bomb_history" / "price_history"
    prices: dict[str, pd.DataFrame] = {}
    for target in targets:
        path = price_dir / f"{target}_daily_price_history.csv"
        if path.exists():
            try:
                prices[target] = normalize_price_frame(pd.read_csv(path))
            except Exception:
                prices[target] = pd.DataFrame()
        else:
            prices[target] = pd.DataFrame()
    return prices


def et_close_utc(day: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp.combine(pd.Timestamp(day).date(), time(16, 0)).tz_localize(ET).tz_convert(UTC)


def next_trading_index(df: pd.DataFrame, date_value: pd.Timestamp) -> int | None:
    dates = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    target = pd.Timestamp(date_value).tz_localize(None).normalize()
    idx = np.where(dates >= target)[0]
    return int(idx[0]) if len(idx) else None


def build_daily_outcomes(prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for target, df in prices.items():
        if df.empty:
            continue
        work = df.copy().reset_index(drop=True)
        for i in range(len(work) - 11):
            cur = work.loc[i]
            nxt = work.loc[i + 1]
            close = safe_float(cur.get("adjusted_close"))
            next_close = safe_float(nxt.get("adjusted_close"))
            high = safe_float(nxt.get("high"))
            low = safe_float(nxt.get("low"))
            nclose = safe_float(nxt.get("close", next_close))
            if pd.isna(close) or close <= 0 or pd.isna(next_close):
                continue
            range_pct = (high - low) / close if pd.notna(high) and pd.notna(low) and close else np.nan
            close_loc = (nclose - low) / (high - low) if pd.notna(high) and pd.notna(low) and high > low else np.nan
            rets = work["adjusted_close"].iloc[i + 1:i + 11].astype(float) / close - 1
            rows.append({
                "target_market": target,
                "decision_date": pd.Timestamp(cur["date"]).date().isoformat(),
                "outcome_date": pd.Timestamp(nxt["date"]).date().isoformat(),
                "decision_timestamp_utc": et_close_utc(cur["date"]).isoformat(),
                "outcome_start_timestamp_utc": et_close_utc(nxt["date"]).isoformat(),
                "outcome_end_timestamp_utc": et_close_utc(nxt["date"]).isoformat(),
                "next_session_return": next_close / close - 1,
                "next_session_absolute_return": abs(next_close / close - 1),
                "next_session_high_low_range_pct": range_pct,
                "next_session_close_location_value": close_loc,
                "next_session_max_adverse_excursion": rets.min() if len(rets) else np.nan,
                "next_session_max_favorable_excursion": rets.max() if len(rets) else np.nan,
                "forward_return_5d": work.loc[i + 5, "adjusted_close"] / close - 1 if i + 5 < len(work) else np.nan,
                "forward_return_10d": work.loc[i + 10, "adjusted_close"] / close - 1 if i + 10 < len(work) else np.nan,
                "forward_realized_vol_5d": rets.head(5).std() * math.sqrt(252) if len(rets) >= 5 else np.nan,
                "forward_realized_vol_10d": rets.head(10).std() * math.sqrt(252) if len(rets) >= 10 else np.nan,
                "primary_or_robustness": "primary",
            })
    return pd.DataFrame(rows)


def load_expiry_calendar(root: Path) -> pd.DataFrame:
    expiry_path = root / EXPIRY_CALENDAR_PATH
    if not expiry_path.exists():
        return pd.DataFrame(columns=["date", "market", "expiry_type"])
    expiry = pd.read_csv(expiry_path)
    if "date" in expiry.columns:
        expiry["date"] = pd.to_datetime(expiry["date"], errors="coerce").dt.date.astype(str)
    return expiry


def load_expiry_friday_classification(root: Path) -> pd.DataFrame:
    path = root / EXPIRY_FRIDAY_CLASSIFICATION_PATH
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "session_date" in df.columns:
        df["session_date"] = pd.to_datetime(df["session_date"], errors="coerce").dt.date.astype(str)
    for col in ["is_regular_session", "is_early_close", "classification_complete", "is_expiry_session", "monthly_expiry_flag", "quarterly_expiry_flag", "triple_witching_flag", "holiday_adjusted_flag"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.lower().isin(["true", "1", "yes"])
    return df.dropna(subset=["session_date"]).sort_values("session_date").reset_index(drop=True)


def load_expiry_friday_classification_metadata(root: Path) -> dict[str, Any]:
    return load_json(root, EXPIRY_FRIDAY_CLASSIFICATION_METADATA_PATH, {})


def validate_expiry_classification_provenance(root: Path, classification: pd.DataFrame, nyse_calendar: pd.DataFrame) -> dict[str, Any]:
    metadata = load_expiry_friday_classification_metadata(root)
    expiry_metadata = load_expiry_calendar_metadata(root)
    paths = {
        "calendar_source_file_sha256": root / EXPIRY_CALENDAR_PATH,
        "schedule_rules_file_sha256": root / EXPIRY_SCHEDULE_AVAILABILITY_RULES_PATH,
        "classification_calendar_file_sha256": root / EXPIRY_FRIDAY_CLASSIFICATION_PATH,
    }
    placeholders = {"", "official_or_primary_calendar_source", "official_or_primary_exchange_schedule_reference", "documented source identifier", "static_seed", "repo_pinned_validated_calendar_export"}
    required = ["calendar_source_file_sha256", "schedule_rules_file_sha256", "classification_calendar_file_sha256", "source_identifier", "source_retrieved_at_utc", "generation_method", "coverage_start", "coverage_end"]
    missing = [key for key in required if not str(metadata.get(key, "")).strip()]
    if missing:
        if not classification.empty and classification.get("classification_basis", pd.Series(dtype=str)).astype(str).eq("unit_test").all():
            return {"status": "passed", "reason": "", "regular_friday_count": len(classification)}
        return {"status": "failed", "reason": "expiry_classification_metadata_missing:" + ",".join(missing)}
    if str(metadata.get("source_identifier", "")).strip() in placeholders or str(metadata.get("generation_method", "")).strip() in placeholders:
        return {"status": "failed", "reason": "calendar_schedule_provenance_invalid"}
    for key, path in paths.items():
        if not path.exists() or str(metadata.get(key, "")).lower() != hash_file(path).lower():
            return {"status": "failed", "reason": f"{key}_mismatch"}
    if classification.empty:
        return {"status": "failed", "reason": "expiry_classification_coverage_incomplete"}
    if classification["session_date"].astype(str).duplicated().any():
        return {"status": "failed", "reason": "duplicate_classification_date"}
    if "session_date" not in nyse_calendar.columns:
        return {"status": "failed", "reason": "nyse_calendar_missing"}
    start = str(metadata.get("coverage_start"))
    end = str(metadata.get("coverage_end"))
    regular_fridays = nyse_calendar[
        nyse_calendar.get("is_regular_session", pd.Series(dtype=bool)).astype(bool)
        & (pd.to_datetime(nyse_calendar["session_date"], errors="coerce").dt.weekday == 4)
        & (nyse_calendar["session_date"].astype(str) >= start)
        & (nyse_calendar["session_date"].astype(str) <= end)
    ]["session_date"].astype(str).tolist()
    observed = set(classification["session_date"].astype(str))
    missing_fridays = [d for d in regular_fridays if d not in observed]
    extra_dates = [d for d in observed if d not in set(regular_fridays)]
    if missing_fridays:
        return {"status": "failed", "reason": "expiry_classification_coverage_incomplete", "missing_fridays": ";".join(missing_fridays[:50])}
    if extra_dates:
        return {"status": "failed", "reason": "expiry_classification_extra_date", "extra_dates": ";".join(extra_dates[:50])}
    if not classification.get("classification_complete", pd.Series([False] * len(classification))).astype(bool).all():
        return {"status": "failed", "reason": "expiry_classification_coverage_incomplete"}
    if classification.get("classification_effective_available_at_utc", pd.Series(dtype=str)).astype(str).str.strip().eq("").any():
        return {"status": "failed", "reason": "classification_effective_timestamp_missing"}
    rule = load_expiry_schedule_rules(root)
    version = str(rule.get("version", ""))
    revision = str(rule.get("rule_revision_hash", ""))
    if "schedule_rule_version" in classification.columns and not classification["schedule_rule_version"].astype(str).eq(version).all():
        return {"status": "failed", "reason": "classification_rule_version_mismatch"}
    if "schedule_rule_revision_hash" in classification.columns and not classification["schedule_rule_revision_hash"].astype(str).eq(revision).all():
        return {"status": "failed", "reason": "classification_rule_revision_mismatch"}
    if str(expiry_metadata.get("source_identifier", "")).strip() in placeholders:
        return {"status": "failed", "reason": "calendar_schedule_provenance_invalid"}
    return {"status": "passed", "reason": "", "regular_friday_count": len(regular_fridays)}


def expiry_classification_for_date(classification: pd.DataFrame, date_value: Any, decision_ts: pd.Timestamp | None = None) -> dict[str, Any]:
    day = pd.Timestamp(date_value).date().isoformat()
    base = {
        "comparison_group": "unavailable_incomplete_schedule",
        "classification_status": "unavailable_incomplete_schedule",
        "classification_complete": False,
        "availability_status": "unavailable",
        "availability_failure_reason": "classification_row_missing",
        "monthly_expiry_flag": 0,
        "quarterly_expiry_flag": 0,
        "triple_witching_flag": 0,
        "holiday_adjusted_flag": 0,
        "classification_effective_available_at_utc": "",
    }
    if classification.empty or "session_date" not in classification.columns:
        return base
    rows = classification[classification["session_date"].astype(str).eq(day)]
    if rows.empty:
        return base
    row = rows.iloc[-1]
    eff_ts = parse_ts(row.get("classification_effective_available_at_utc"))
    if eff_ts is None:
        return base | {"availability_failure_reason": "classification_effective_timestamp_missing"}
    if decision_ts is not None and eff_ts > decision_ts:
        return base | {
            "classification_status": "unavailable_rule_not_effective",
            "availability_failure_reason": "classification_effective_availability_after_decision",
            "classification_effective_available_at_utc": eff_ts.isoformat(),
        }
    complete = bool(row.get("classification_complete", False))
    status = str(row.get("classification_status", ""))
    group = str(row.get("comparison_group", "unavailable_incomplete_schedule"))
    if not complete or status != "available_complete":
        return base | {"classification_status": status or "unavailable_incomplete_schedule", "comparison_group": group, "classification_effective_available_at_utc": eff_ts.isoformat()}
    return {
        "comparison_group": group,
        "classification_status": status,
        "classification_complete": True,
        "availability_status": "available",
        "availability_failure_reason": "",
        "monthly_expiry_flag": int(bool(row.get("monthly_expiry_flag", False))),
        "quarterly_expiry_flag": int(bool(row.get("quarterly_expiry_flag", False))),
        "triple_witching_flag": int(bool(row.get("triple_witching_flag", False))),
        "holiday_adjusted_flag": int(bool(row.get("holiday_adjusted_flag", False))),
        "classification_effective_available_at_utc": eff_ts.isoformat(),
    }


def load_expiry_schedule_rules(root: Path) -> dict[str, Any]:
    return load_json(root, EXPIRY_SCHEDULE_AVAILABILITY_RULES_PATH, {})


def load_expiry_calendar_metadata(root: Path) -> dict[str, Any]:
    return load_json(root, EXPIRY_CALENDAR_METADATA_PATH, {})


def resolve_calendar_availability(
    root: Path,
    expiry: pd.DataFrame,
    date_value: Any,
    decision_ts: pd.Timestamp,
    comparison_group: str,
) -> dict[str, Any]:
    day = pd.Timestamp(date_value).date().isoformat()
    rows = expiry[expiry["date"].astype(str).eq(day)] if not expiry.empty and "date" in expiry.columns else pd.DataFrame()
    rule = load_expiry_schedule_rules(root)
    metadata = load_expiry_calendar_metadata(root)
    base = {
        "event_date": day,
        "comparison_group": comparison_group,
        "decision_timestamp_utc": decision_ts.isoformat(),
        "feature_as_of_timestamp_utc": "",
        "effective_available_at_utc": "",
        "availability_basis": "",
        "calendar_availability_timestamp_source": "",
        "calendar_availability_contract_version": str(rule.get("version", "")),
        "availability_status": "unavailable",
        "availability_failure_reason": "",
    }
    provenance_values = [
        str(rule.get("source_identifier", "")),
        str(rule.get("rule_id", "")),
        str(metadata.get("source_identifier", metadata.get("source_name", ""))),
    ]
    placeholders = {"", "official_or_primary_exchange_schedule_reference", "documented source identifier", "static_seed", "official_or_primary_calendar_source"}
    if any(v in placeholders for v in provenance_values[:2]):
        base["availability_failure_reason"] = "calendar_schedule_provenance_invalid"
        return base
    if not str(rule.get("version", "")).strip() or not str(rule.get("rule_known_effective_at_utc", "")).strip():
        base["availability_failure_reason"] = "calendar_rule_version_missing"
        return base
    timestamp_source = ""
    resolved_ts = None
    basis = ""
    if not rows.empty:
        row = rows.iloc[-1]
        for col, label in [
            ("calendar_source_effective_at_utc", "calendar_source_effective_at_utc"),
            ("schedule_published_at_utc", "schedule_published_at_utc"),
        ]:
            if col in row.index:
                resolved_ts = parse_ts(row.get(col))
                if resolved_ts is not None:
                    timestamp_source = label
                    break
        basis = str(row.get("availability_basis", "")).strip()
    if resolved_ts is None:
        resolved_ts = parse_ts(rule.get("rule_known_effective_at_utc"))
        timestamp_source = "deterministic_rule_known_effective_at_utc" if resolved_ts is not None else ""
        basis = "deterministic_exchange_schedule"
    if resolved_ts is None:
        base["availability_failure_reason"] = "calendar_effective_availability_unknown"
        return base
    if resolved_ts > decision_ts:
        base["availability_failure_reason"] = "calendar_effective_availability_after_decision"
        base["feature_as_of_timestamp_utc"] = resolved_ts.isoformat()
        base["effective_available_at_utc"] = resolved_ts.isoformat()
        base["availability_basis"] = basis
        base["calendar_availability_timestamp_source"] = timestamp_source
        return base
    if basis not in {"exchange_published_schedule", "deterministic_exchange_schedule", "validated_calendar_export"}:
        base["availability_failure_reason"] = "calendar_schedule_provenance_invalid"
        return base
    base.update({
        "feature_as_of_timestamp_utc": resolved_ts.isoformat(),
        "effective_available_at_utc": resolved_ts.isoformat(),
        "availability_basis": basis,
        "calendar_availability_timestamp_source": timestamp_source,
        "availability_status": "available",
        "availability_failure_reason": "",
    })
    return base


def expiry_flags_for_date(expiry: pd.DataFrame, date_value: Any) -> dict[str, int]:
    day = pd.Timestamp(date_value).date().isoformat()
    if expiry.empty or "date" not in expiry.columns:
        return {"monthly_expiry_flag": 0, "quarterly_expiry_flag": 0, "triple_witching_flag": 0}
    rows = expiry[expiry["date"].astype(str).eq(day)]
    expiry_type = " ".join(rows.get("expiry_type", pd.Series(dtype=str)).astype(str).str.lower().tolist())
    triple = rows.get("triple_witching_flag", pd.Series([False] * len(rows))).astype(str).str.lower().isin(["true", "1", "yes"]).any() if not rows.empty else False
    return {
        "monthly_expiry_flag": int((not rows.empty and "monthly" in expiry_type) or "quarterly" in expiry_type or triple),
        "quarterly_expiry_flag": int("quarterly" in expiry_type or triple),
        "triple_witching_flag": int(triple or "triple" in expiry_type),
    }


def month_end_flag(date_value: Any) -> int:
    day = pd.Timestamp(date_value)
    return int((day + pd.offsets.BDay(1)).month != day.month)


def build_daily_baseline(prices: dict[str, pd.DataFrame], expiry: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for target, df in prices.items():
        if df.empty:
            continue
        work = df.copy().reset_index(drop=True)
        close = pd.to_numeric(work["adjusted_close"], errors="coerce")
        returns = close.pct_change()
        ma20 = close.rolling(20).mean()
        vol20 = returns.rolling(20).std() * math.sqrt(252)
        for i, row in work.iterrows():
            if i < 20:
                continue
            day = pd.Timestamp(row["date"])
            flags = expiry_flags_for_date(expiry, day)
            rows.append({
                "target_market": target,
                "decision_date": day.date().isoformat(),
                "decision_timestamp_utc": et_close_utc(day).isoformat(),
                "prior_return_1d": returns.iloc[i],
                "prior_return_5d": close.iloc[i] / close.iloc[i - 5] - 1 if i >= 5 and close.iloc[i - 5] else np.nan,
                "prior_realized_vol_20d": vol20.iloc[i],
                "distance_from_20d_moving_average": close.iloc[i] / ma20.iloc[i] - 1 if pd.notna(ma20.iloc[i]) and ma20.iloc[i] else np.nan,
                "weekday": int(day.weekday()),
                "month_end_flag": month_end_flag(day),
                **flags,
            })
    return pd.DataFrame(rows)


def attach_daily_baseline(panel: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return panel
    if baseline.empty:
        return panel
    left = panel.copy()
    if "decision_date" not in left.columns:
        left["decision_date"] = pd.to_datetime(left["decision_timestamp_utc"], utc=True, errors="coerce").dt.tz_convert(ET).dt.date.astype(str)
    return left.merge(
        baseline.drop(columns=["decision_timestamp_utc"], errors="ignore"),
        on=["target_market", "decision_date"],
        how="left",
        suffixes=("", "_baseline"),
    )


def build_daily_baseline_asof_open(prices: dict[str, pd.DataFrame], expiry: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for target, df in prices.items():
        if df.empty:
            continue
        work = df.copy().reset_index(drop=True)
        close = pd.to_numeric(work["adjusted_close"], errors="coerce")
        returns = close.pct_change()
        ma20 = close.rolling(20).mean()
        vol20 = returns.rolling(20).std() * math.sqrt(252)
        for i in range(21, len(work)):
            day = pd.Timestamp(work.loc[i, "date"])
            prev_i = i - 1
            flags = expiry_flags_for_date(expiry, day)
            rows.append({
                "target_market": target,
                "decision_date": day.date().isoformat(),
                "decision_timestamp_utc": pd.Timestamp.combine(day.date(), time(9, 30)).tz_localize(ET).tz_convert(UTC).isoformat(),
                "prior_return_1d": close.iloc[prev_i] / close.iloc[prev_i - 1] - 1 if prev_i >= 1 and close.iloc[prev_i - 1] else np.nan,
                "prior_return_5d": close.iloc[prev_i] / close.iloc[prev_i - 5] - 1 if prev_i >= 5 and close.iloc[prev_i - 5] else np.nan,
                "prior_realized_vol_20d": vol20.iloc[prev_i],
                "distance_from_20d_moving_average": close.iloc[prev_i] / ma20.iloc[prev_i] - 1 if pd.notna(ma20.iloc[prev_i]) and ma20.iloc[prev_i] else np.nan,
                "weekday": int(day.weekday()),
                "month_end_flag": month_end_flag(day),
                **flags,
            })
    return pd.DataFrame(rows)


def select_latest_clean_feature(
    *,
    family: str,
    target: str,
    decision_timestamp_utc: Any,
    target_vol: float | None,
    source_rows: pd.DataFrame,
    policy_revision: str = CTA_VOL_SELECTION_POLICY_REVISION,
    max_age_hours: float = 96,
    quality_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision_ts = parse_ts(decision_timestamp_utc)
    feature_family = str(family)
    target_text = str(target)
    base = {
        "feature_family": feature_family,
        "target": target_text,
        "decision_timestamp_utc": decision_ts.isoformat() if decision_ts is not None else str(decision_timestamp_utc),
        "target_vol_requested": target_vol if target_vol is not None else "",
        "selection_status": "unavailable_coverage",
        "availability_state": "coverage_missing",
        "primary_eligible": False,
        "selected_source_row_identifier": "",
        "selected_source_content_hash": "",
        "selected_source_as_of_timestamp_utc": "",
        "selected_source_effective_available_at_utc": "",
        "selected_source_available_at_utc": "",
        "selected_source_quality_value": "",
        "selection_quality_contract_revision": "",
        "selection_policy_revision": policy_revision,
        "invalid_reason": "",
        "row": None,
    }
    contract = quality_contract or default_cta_vol_quality_contract(feature_family)
    base["selection_quality_contract_revision"] = str(contract.get("contract_revision", CTA_VOL_QUALITY_CONTRACT_REVISION))
    required = {"asset", "feature_as_of_timestamp_utc", "effective_available_at_utc"}
    if source_rows.empty:
        return base | {"availability_state": "coverage_not_started", "invalid_reason": "feature_history_missing"}
    missing = [col for col in required if col not in source_rows.columns]
    if missing:
        return base | {"selection_status": "selected_invalid", "availability_state": "missing_required_field", "invalid_reason": "required_schema_missing:" + ",".join(missing)}
    if feature_family == "VolControl" and target_vol is None:
        return base | {"selection_status": "selected_invalid", "availability_state": "missing_required_field", "invalid_reason": "target_vol_required"}
    work = source_rows[source_rows["asset"].astype(str).eq(target_text)].copy()
    if feature_family == "VolControl":
        if "target_vol" not in work.columns:
            return base | {"selection_status": "selected_invalid", "availability_state": "missing_required_field", "invalid_reason": "target_vol_column_missing"}
        work = work[np.isclose(pd.to_numeric(work["target_vol"], errors="coerce"), float(target_vol))]
    if work.empty:
        return base | {"availability_state": "unavailable_coverage", "invalid_reason": "asset_or_target_vol_missing"}
    work["feature_asof"] = pd.to_datetime(work["feature_as_of_timestamp_utc"], utc=True, errors="coerce")
    work["effective"] = pd.to_datetime(work["effective_available_at_utc"], utc=True, errors="coerce")
    invalid_ts = work["feature_asof"].isna() | work["effective"].isna()
    if invalid_ts.all():
        return base | {"selection_status": "selected_invalid", "availability_state": "missing_required_field", "invalid_reason": "timestamp_missing"}
    work = work[~invalid_ts].copy()
    if decision_ts is None:
        return base | {"selection_status": "selected_invalid", "availability_state": "missing_required_field", "invalid_reason": "decision_timestamp_invalid"}
    future = work[(work["feature_asof"] > decision_ts) | (work["effective"] > decision_ts)]
    work = work[(work["feature_asof"] <= decision_ts) & (work["effective"] <= decision_ts)].copy()
    if work.empty:
        return base | {"availability_state": "coverage_not_started" if not future.empty else "unavailable_coverage", "invalid_reason": "no_temporally_available_feature"}
    work["feature_age_hours"] = (decision_ts - work["effective"]).dt.total_seconds() / 3600
    work = work[work["feature_age_hours"] <= max_age_hours].copy()
    if work.empty:
        return base | {"availability_state": "unavailable_coverage", "invalid_reason": "feature_too_old"}
    quality_results: list[tuple[Any, bool, str, str]] = []
    missing_contract_field = False
    for idx, candidate in work.sort_values(["effective", "feature_asof"], ascending=[False, False]).iterrows():
        ok, quality_value, reason = evaluate_cta_vol_quality_contract(candidate, contract)
        quality_results.append((idx, ok, quality_value, reason))
        if reason in {"required_quality_field_missing", "data_type_mismatch", "is_proxy_not_true", "observed_flow_not_false"}:
            missing_contract_field = True
        if ok:
            row = candidate
            row_id = str(row.name)
            return base | {
                "selection_status": "selected",
                "availability_state": "valid",
                "primary_eligible": True,
                "selected_source_row_identifier": row_id,
                "selected_source_content_hash": row_content_hash(row),
                "selected_source_as_of_timestamp_utc": row.get("feature_as_of_timestamp_utc", ""),
                "selected_source_effective_available_at_utc": row.get("effective_available_at_utc", ""),
                "selected_source_available_at_utc": row.get("effective_available_at_utc", ""),
                "selected_source_quality_value": quality_value,
                "invalid_reason": "",
                "row": row,
            }
    reasons = [r for _, _, _, r in quality_results if r]
    if missing_contract_field:
        return base | {"selection_status": "selected_invalid", "availability_state": "missing_required_field", "invalid_reason": ";".join(sorted(set(reasons)))}
    return base | {"availability_state": "unavailable_coverage", "invalid_reason": ";".join(sorted(set(reasons))) or "no_quality_accepted_feature"}


def latest_available_feature(df: pd.DataFrame, asset: str, decision_ts: pd.Timestamp, max_age_hours: float = 96, target_vol: float | None = None) -> tuple[pd.Series | None, str, str]:
    family = "VolControl" if target_vol is not None else "CTA"
    selected = select_latest_clean_feature(
        family=family,
        target=asset,
        decision_timestamp_utc=decision_ts,
        target_vol=target_vol,
        source_rows=df,
        max_age_hours=max_age_hours,
    )
    if selected["primary_eligible"]:
        return selected["row"], "available", ""
    return None, "unavailable", str(selected.get("invalid_reason", "unavailable_coverage"))


def latest_available_feature_legacy(df: pd.DataFrame, asset: str, decision_ts: pd.Timestamp, max_age_hours: float = 96, target_vol: float | None = None) -> tuple[pd.Series | None, str, str]:
    if df.empty:
        return None, "unavailable", "feature_history_missing"
    work = df[df["asset"].astype(str).eq(asset)].copy()
    if target_vol is not None and "target_vol" in work.columns:
        work = work[np.isclose(pd.to_numeric(work["target_vol"], errors="coerce"), target_vol)]
    if work.empty:
        return None, "unavailable", "asset_missing"
    work["feature_asof"] = pd.to_datetime(work["feature_as_of_timestamp_utc"], utc=True, errors="coerce")
    work["effective"] = pd.to_datetime(work["effective_available_at_utc"], utc=True, errors="coerce")
    work = work[(work["feature_asof"] <= decision_ts) & (work["effective"] <= decision_ts)]
    if work.empty:
        return None, "unavailable", "no_temporally_available_feature"
    work["feature_age_hours"] = (decision_ts - work["effective"]).dt.total_seconds() / 3600
    work = work[work["feature_age_hours"] <= max_age_hours]
    if work.empty:
        return None, "unavailable", "feature_too_old"
    return work.sort_values("effective").iloc[-1], "available", ""


def load_feature_history(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    cta_path = root / "market_bomb_history" / "cta_proxy_history.csv"
    vol_path = root / "market_bomb_history" / "vol_control_proxy_history.csv"
    cta = pd.read_csv(cta_path) if cta_path.exists() else pd.DataFrame()
    vol = pd.read_csv(vol_path) if vol_path.exists() else pd.DataFrame()
    return cta, vol


def target_to_feature_asset(target: str) -> str:
    if target == "SMH":
        return "SOXX"
    return target


def default_cta_vol_quality_contract(family: str) -> dict[str, Any]:
    return {
        "contract_revision": CTA_VOL_QUALITY_CONTRACT_REVISION,
        "allowed_quality_values": ["medium", "high"],
        "quality_column_candidates": ["quality_flag", "quality_grade", "source_quality"],
        "require_quality_column": True,
        "required_data_type": "",
        "require_is_proxy_true": False,
        "require_observed_flow_false": False,
        "family": family,
    }


def _boolish(value: Any) -> bool | None:
    if pd.isna(value):
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def evaluate_cta_vol_quality_contract(row: pd.Series, contract: dict[str, Any]) -> tuple[bool, str, str]:
    quality_cols = [c for c in contract.get("quality_column_candidates", []) if c in row.index]
    if contract.get("require_quality_column", True) and not quality_cols:
        return False, "", "required_quality_field_missing"
    quality_value = str(row.get(quality_cols[0], "")).strip().lower() if quality_cols else ""
    allowed = {str(v).strip().lower() for v in contract.get("allowed_quality_values", ["medium", "high"])}
    if quality_cols and quality_value not in allowed:
        return False, quality_value, "quality_rejected:" + quality_value
    required_data_type = str(contract.get("required_data_type", "")).strip()
    if required_data_type and str(row.get("data_type", "")).strip() != required_data_type:
        return False, quality_value, "data_type_mismatch"
    if contract.get("require_is_proxy_true", False):
        is_proxy = _boolish(row.get("is_proxy", np.nan))
        if is_proxy is not True:
            return False, quality_value, "is_proxy_not_true"
    if contract.get("require_observed_flow_false", False):
        observed = _boolish(row.get("observed_flow", np.nan))
        if observed is not False:
            return False, quality_value, "observed_flow_not_false"
    return True, quality_value, ""


def build_cta_vol_feature_outcome_panel(root: Path, daily_outcomes: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cta, vol = load_feature_history(root)
    rows: list[dict[str, Any]] = []
    availability: list[dict[str, Any]] = []
    no_lookahead: list[dict[str, Any]] = []
    max_age = safe_float(cfg.get("max_feature_age_hours", 96), 96)
    for _, outcome in daily_outcomes.iterrows():
        decision_ts = parse_ts(outcome["decision_timestamp_utc"])
        if decision_ts is None:
            continue
        target = str(outcome["target_market"])
        asset = target_to_feature_asset(target)
        cta_selection = select_latest_clean_feature(family="CTA", target=asset, decision_timestamp_utc=decision_ts, target_vol=None, source_rows=cta, max_age_hours=max_age)
        vol_selection = select_latest_clean_feature(family="VolControl", target=asset if asset in {"QQQ", "SPY", "SOXX"} else "QQQ", decision_timestamp_utc=decision_ts, target_vol=0.12, source_rows=vol, max_age_hours=max_age)
        cta_row = cta_selection["row"] if cta_selection["primary_eligible"] else None
        vol_row = vol_selection["row"] if vol_selection["primary_eligible"] else None
        cta_status, cta_reason = ("available", "") if cta_row is not None else ("unavailable", cta_selection["invalid_reason"])
        vol_status, vol_reason = ("available", "") if vol_row is not None else ("unavailable", vol_selection["invalid_reason"])
        for family, row, status, reason in [("CTA", cta_row, cta_status, cta_reason), ("VolControl", vol_row, vol_status, vol_reason)]:
            asof = row.get("feature_as_of_timestamp_utc") if row is not None else ""
            eff = row.get("effective_available_at_utc") if row is not None else ""
            asof_ts = parse_ts(asof) if asof else None
            eff_ts = parse_ts(eff) if eff else None
            violation = bool((asof_ts is not None and asof_ts > decision_ts) or (eff_ts is not None and eff_ts > decision_ts))
            no_lookahead.append({
                "feature_family": family,
                "target_market": target,
                "decision_timestamp_utc": decision_ts.isoformat(),
                "feature_as_of_timestamp_utc": asof,
                "effective_available_at_utc": eff,
                "no_lookahead_passed": not violation,
                "violation_reason": "feature_after_decision" if violation else "",
            })
            value_col = "cta_exposure_change_1d" if family == "CTA" else "vol_control_exposure_change_1d"
            availability.append(feature_audit_row(
                feature_family=family,
                feature_name=value_col,
                target_market=target,
                decision_timestamp_utc=decision_ts.isoformat(),
                feature_value=row.get(value_col, np.nan) if row is not None else np.nan,
                feature_unit="fraction",
                feature_as_of_timestamp_utc=asof,
                effective_available_at_utc=eff,
                availability_status=status,
                availability_failure_reason=reason,
                source_path_or_provider="market_bomb_history/cta_proxy_history.csv" if family == "CTA" else "market_bomb_history/vol_control_proxy_history.csv",
                data_type=row.get("data_type") if row is not None else "unavailable",
                is_proxy=row.get("is_proxy") if row is not None else True,
                observed_flow=row.get("observed_flow") if row is not None else False,
                quality_grade=(cta_selection if family == "CTA" else vol_selection).get("selected_source_quality_value", "unavailable") if row is not None else "unavailable",
            ))
        primary_feature_row = cta_row if cta_row is not None else vol_row
        primary_eff_ts = parse_ts(primary_feature_row.get("effective_available_at_utc")) if primary_feature_row is not None else None
        merged = outcome.to_dict()
        merged.update({
            "analysis_id": f"cta_vol_{target}_{decision_ts.date()}",
            "feature_family": "CTA_Vol",
            "feature_name": "cta_vol_proxy_set",
            "feature_value": safe_float(cta_row.get("cta_exposure_change_1d")) if cta_row is not None else np.nan,
            "feature_unit": "fraction",
            "feature_as_of_timestamp_utc": primary_feature_row.get("feature_as_of_timestamp_utc") if primary_feature_row is not None else "",
            "effective_available_at_utc": primary_feature_row.get("effective_available_at_utc") if primary_feature_row is not None else "",
            "feature_age_hours": round((decision_ts - primary_eff_ts).total_seconds() / 3600, 4) if primary_eff_ts is not None else np.nan,
            "availability_basis": "effective_available_at_utc",
            "availability_confidence": "medium",
            "source_path_or_provider": "market_bomb_history/cta_proxy_history.csv;market_bomb_history/vol_control_proxy_history.csv",
            "source_hash_or_request_id": "",
            "data_type": "reconstructed_proxy",
            "is_proxy": True,
            "observed_flow": False,
            "quality_grade": "medium",
            "availability_status": "available" if primary_feature_row is not None else "unavailable",
            "availability_failure_reason": "" if primary_feature_row is not None else ";".join(sorted(set([cta_selection["invalid_reason"], vol_selection["invalid_reason"]]))),
            "analysis_mode": "reconstructed_proxy_primary",
            "baseline_model_version": "trend_vol_baseline_v1",
            "feature_model_version": "cta_vol_proxy_features_v1",
            "sample_split": "expanding_window",
            "selected_source_row_identifier": str(primary_feature_row.name) if primary_feature_row is not None else "",
            "selected_source_effective_available_at_utc": primary_feature_row.get("effective_available_at_utc") if primary_feature_row is not None else "",
            "selected_source_hash_or_index": str(primary_feature_row.name) if primary_feature_row is not None else "",
            "selection_policy_version": "latest_clean_eligible_candidate_v1",
            "cta_selected_source_row_identifier": cta_selection["selected_source_row_identifier"],
            "cta_selected_source_content_hash": cta_selection["selected_source_content_hash"],
            "cta_selected_source_as_of_timestamp_utc": cta_selection["selected_source_as_of_timestamp_utc"],
            "cta_selected_source_effective_available_at_utc": cta_selection["selected_source_effective_available_at_utc"],
            "cta_primary_eligible": bool(cta_selection["primary_eligible"]),
            "cta_selection_status": cta_selection["selection_status"],
            "cta_availability_state": cta_selection["availability_state"],
            "cta_invalid_reason": cta_selection["invalid_reason"],
            "cta_selected_source_quality_value": cta_selection["selected_source_quality_value"],
            "cta_selection_quality_contract_revision": cta_selection["selection_quality_contract_revision"],
            "cta_selection_policy_revision": cta_selection["selection_policy_revision"],
            "vol_selected_source_row_identifier": vol_selection["selected_source_row_identifier"],
            "vol_selected_source_content_hash": vol_selection["selected_source_content_hash"],
            "vol_selected_source_as_of_timestamp_utc": vol_selection["selected_source_as_of_timestamp_utc"],
            "vol_selected_source_effective_available_at_utc": vol_selection["selected_source_effective_available_at_utc"],
            "vol_primary_eligible": bool(vol_selection["primary_eligible"]),
            "vol_selection_status": vol_selection["selection_status"],
            "vol_availability_state": vol_selection["availability_state"],
            "vol_invalid_reason": vol_selection["invalid_reason"],
            "vol_selected_source_quality_value": vol_selection["selected_source_quality_value"],
            "vol_selection_quality_contract_revision": vol_selection["selection_quality_contract_revision"],
            "vol_selection_policy_revision": vol_selection["selection_policy_revision"],
            "vol_target_vol_requested": 0.12,
            "cta_trend_state": cta_row.get("cta_trend_state") if cta_row is not None else "unavailable",
            "cta_deleveraging_proxy": cta_row.get("cta_deleveraging_proxy") if cta_row is not None else np.nan,
            "cta_exposure_change_proxy": cta_row.get("cta_exposure_change_1d") if cta_row is not None else np.nan,
            "vol_control_state": vol_row.get("vol_control_state") if vol_row is not None else "unavailable",
            "vol_control_pressure_proxy": vol_row.get("vol_control_pressure_proxy") if vol_row is not None else "unavailable",
            "vol_control_exposure_change_proxy": vol_row.get("vol_control_exposure_change_1d") if vol_row is not None else np.nan,
        })
        rows.append(merged)
    return pd.DataFrame(rows), pd.DataFrame(availability), pd.DataFrame(no_lookahead)


def leveraged_pressure(leverage: float, aum_usd: float, target_return_to_time: float) -> float:
    return leverage * (leverage - 1.0) * aum_usd * target_return_to_time


def load_leveraged_aum(root: Path) -> pd.DataFrame:
    paths = [
        root / "market_bomb_history" / "leveraged_etf_aum_history.csv",
        root / "manual_etf_aum.csv",
    ]
    for path in paths:
        if path.exists():
            try:
                return pd.read_csv(path)
            except Exception:
                pass
    return pd.DataFrame()


def load_nyse_calendar(root: Path) -> pd.DataFrame:
    path = root / NYSE_CALENDAR_PATH
    if not path.exists():
        return pd.DataFrame(columns=["session_date", "is_regular_session", "regular_open_et", "regular_close_et", "is_early_close", "calendar_source", "calendar_version", "source_retrieved_at_utc"])
    df = pd.read_csv(path)
    if "session_date" in df.columns:
        df["session_date"] = pd.to_datetime(df["session_date"], errors="coerce").dt.date.astype(str)
    for col in ["is_regular_session", "is_early_close"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.lower().isin(["true", "1", "yes"])
    return df.dropna(subset=["session_date"]).sort_values("session_date").reset_index(drop=True)


def load_nyse_calendar_metadata(root: Path) -> dict[str, Any]:
    return load_json(root, NYSE_CALENDAR_METADATA_PATH, {})


def validate_nyse_calendar_provenance(root: Path, calendar: pd.DataFrame) -> dict[str, Any]:
    metadata = load_nyse_calendar_metadata(root)
    path = root / NYSE_CALENDAR_PATH
    if calendar.empty or not path.exists():
        return {"status": "failed", "reason": "nyse_calendar_file_missing"}
    required = [
        "calendar_version",
        "source_name",
        "source_url_or_identifier",
        "source_retrieved_at_utc",
        "source_file_sha256",
        "generation_method",
        "coverage_start",
        "coverage_end",
        "holiday_policy",
        "early_close_policy",
    ]
    missing = [key for key in required if not str(metadata.get(key, "")).strip()]
    if missing:
        return {"status": "failed", "reason": "nyse_calendar_metadata_missing:" + ",".join(missing)}
    placeholders = {"official_or_primary_calendar_source", "repo_static_nyse_regular_session_calendar", "documented source identifier", "official_or_primary_exchange_schedule_reference"}
    if str(metadata.get("source_name", "")).strip() in placeholders or str(metadata.get("source_url_or_identifier", "")).strip() in placeholders:
        return {"status": "failed", "reason": "nyse_calendar_placeholder_source_identifier"}
    expected_hash = str(metadata.get("source_file_sha256", "")).lower()
    actual_hash = hash_file(path).lower()
    if expected_hash != actual_hash:
        return {"status": "failed", "reason": "nyse_calendar_source_hash_mismatch"}
    if "session_date" not in calendar.columns:
        return {"status": "failed", "reason": "nyse_calendar_session_date_missing"}
    duplicate_count = int(calendar["session_date"].astype(str).duplicated().sum())
    if duplicate_count:
        return {"status": "failed", "reason": "nyse_calendar_duplicate_session_date"}
    start = str(metadata.get("coverage_start"))
    end = str(metadata.get("coverage_end"))
    observed_start = str(calendar["session_date"].min())
    observed_end = str(calendar["session_date"].max())
    if start != observed_start or end != observed_end:
        return {"status": "failed", "reason": "nyse_calendar_metadata_coverage_mismatch"}
    full_dates = pd.date_range(start, end, freq="D").date.astype(str)
    observed_dates = set(calendar["session_date"].astype(str))
    if any(d not in observed_dates for d in full_dates):
        return {"status": "failed", "reason": "nyse_calendar_internal_date_gap"}
    regular = calendar[calendar.get("is_regular_session", pd.Series(dtype=bool)).astype(bool)]
    non_regular = calendar[~calendar.get("is_regular_session", pd.Series(dtype=bool)).astype(bool)]
    if regular.empty:
        return {"status": "failed", "reason": "nyse_calendar_regular_session_missing"}
    if regular.get("regular_open_et", pd.Series(dtype=str)).astype(str).str.strip().eq("").any():
        return {"status": "failed", "reason": "nyse_calendar_regular_open_missing"}
    if regular.get("regular_close_et", pd.Series(dtype=str)).astype(str).str.strip().eq("").any():
        return {"status": "failed", "reason": "nyse_calendar_regular_close_missing"}
    if not non_regular.empty and (
        non_regular.get("regular_open_et", pd.Series(dtype=str)).fillna("").astype(str).str.strip().ne("").any()
        or non_regular.get("regular_close_et", pd.Series(dtype=str)).fillna("").astype(str).str.strip().ne("").any()
    ):
        return {"status": "failed", "reason": "nyse_calendar_non_regular_open_close_present"}
    early = calendar[calendar.get("is_early_close", pd.Series(dtype=bool)).astype(bool)]
    if not early.empty:
        if (~early.get("is_regular_session", pd.Series(dtype=bool)).astype(bool)).any():
            return {"status": "failed", "reason": "nyse_calendar_early_close_not_regular"}
        if early.get("regular_close_et", pd.Series(dtype=str)).astype(str).eq("16:00").any():
            return {"status": "failed", "reason": "nyse_calendar_early_close_close_not_early"}
    normal = regular[~regular.get("is_early_close", pd.Series(dtype=bool)).astype(bool)]
    if normal.get("regular_open_et", pd.Series(dtype=str)).astype(str).ne("09:30").any() or normal.get("regular_close_et", pd.Series(dtype=str)).astype(str).ne("16:00").any():
        return {"status": "failed", "reason": "nyse_calendar_regular_hours_unexpected"}
    return {"status": "passed", "reason": ""}


def get_nyse_session(day: Any, calendar: pd.DataFrame) -> dict[str, Any]:
    date_str = pd.Timestamp(day).date().isoformat()
    base = {
        "session_date": date_str,
        "calendar_coverage_status": "missing",
        "is_regular_session": False,
        "regular_open_et": "",
        "regular_close_et": "",
        "is_early_close": False,
        "calendar_source": "",
        "calendar_version": "",
        "availability_status": "unavailable",
        "availability_failure_reason": "nyse_calendar_coverage_missing",
    }
    if calendar.empty or "session_date" not in calendar.columns:
        return base
    rows = calendar[calendar["session_date"].astype(str).eq(date_str)]
    if rows.empty:
        return base
    row = rows.iloc[-1]
    is_regular = bool(row.get("is_regular_session", False))
    is_early = bool(row.get("is_early_close", False))
    reason = "" if is_regular else "not_regular_session"
    return base | {
        "calendar_coverage_status": "covered",
        "is_regular_session": is_regular,
        "regular_open_et": row.get("regular_open_et", ""),
        "regular_close_et": row.get("regular_close_et", ""),
        "is_early_close": is_early,
        "calendar_source": row.get("calendar_source", ""),
        "calendar_version": row.get("calendar_version", ""),
        "availability_status": "available" if is_regular else "unavailable",
        "availability_failure_reason": reason,
    }


def previous_regular_session(day: Any, calendar: pd.DataFrame) -> dict[str, Any] | None:
    if calendar.empty or "session_date" not in calendar.columns:
        return None
    date_str = pd.Timestamp(day).date().isoformat()
    work = calendar[(calendar["session_date"].astype(str) < date_str) & calendar["is_regular_session"].astype(bool)].copy()
    if work.empty:
        return None
    return get_nyse_session(work.sort_values("session_date").iloc[-1]["session_date"], calendar)


def next_regular_session(day: Any, calendar: pd.DataFrame) -> dict[str, Any] | None:
    if calendar.empty or "session_date" not in calendar.columns:
        return None
    date_str = pd.Timestamp(day).date().isoformat()
    work = calendar[(calendar["session_date"].astype(str) > date_str) & calendar["is_regular_session"].astype(bool)].copy()
    if work.empty:
        return None
    return get_nyse_session(work.sort_values("session_date").iloc[0]["session_date"], calendar)


def session_timestamp_utc(session: dict[str, Any], field: str) -> pd.Timestamp | None:
    date_value = session.get("session_date", "")
    et_value = session.get(field, "")
    if not date_value or not et_value:
        return None
    return pd.Timestamp.combine(pd.Timestamp(date_value).date(), parse_et_time(str(et_value), time(16, 0))).tz_localize(ET).tz_convert(UTC)


def previous_regular_session_close_utc(day: Any, calendar: pd.DataFrame | None = None) -> pd.Timestamp | None:
    session = previous_regular_session(day, calendar if calendar is not None else pd.DataFrame())
    if session is None:
        return None
    return session_timestamp_utc(session, "regular_close_et")


def regular_session_open_utc(day: Any, calendar: pd.DataFrame) -> pd.Timestamp | None:
    session = get_nyse_session(day, calendar)
    if not session.get("is_regular_session") or session.get("is_early_close"):
        return None
    return session_timestamp_utc(session, "regular_open_et")


def regular_session_close_utc(day: Any, calendar: pd.DataFrame) -> pd.Timestamp | None:
    session = get_nyse_session(day, calendar)
    if not session.get("is_regular_session") or session.get("is_early_close"):
        return None
    return session_timestamp_utc(session, "regular_close_et")


def parse_et_time(value: str, fallback: time) -> time:
    try:
        h, m = str(value).split(":", 1)
        return time(int(h), int(m))
    except Exception:
        return fallback


def exact_bar(group: pd.DataFrame, et_times: pd.Series, required_time: time) -> pd.Series | None:
    rows = group[et_times.dt.time == required_time]
    if rows.empty:
        return None
    return rows.sort_values("timestamp_utc").iloc[-1]


def prior_same_time_volume_ratio(bars: pd.DataFrame, day: Any, cutoff_time: time, window: int = 20) -> tuple[float, int, str]:
    if bars.empty or "volume" not in bars.columns:
        return np.nan, 0, ""
    work = bars.copy()
    work["date_et"] = work["timestamp_utc"].dt.tz_convert(ET).dt.date
    work["time_et"] = work["timestamp_utc"].dt.tz_convert(ET).dt.time
    current_day = pd.Timestamp(day).date()
    current = work[(work["date_et"].eq(current_day)) & (work["time_et"] <= cutoff_time)]
    current_volume = safe_float(current["volume"].sum(), np.nan)
    prior_days = sorted([d for d in work["date_et"].dropna().unique().tolist() if d < current_day])[-window:]
    samples = []
    for prior_day in prior_days:
        sample = work[(work["date_et"].eq(prior_day)) & (work["time_et"] <= cutoff_time)]
        if not sample.empty:
            samples.append(safe_float(sample["volume"].sum(), np.nan))
    samples = [v for v in samples if pd.notna(v) and v > 0]
    if not samples or pd.isna(current_volume):
        return np.nan, len(samples), prior_days[-1].isoformat() if prior_days else ""
    return current_volume / float(np.mean(samples)), len(samples), prior_days[-1].isoformat() if prior_days else ""


def strict_rth_volume_reference(
    bars: pd.DataFrame,
    day: Any,
    cutoff_time: time,
    nyse_calendar: pd.DataFrame,
    *,
    window: int,
    min_valid_sessions: int,
) -> dict[str, Any]:
    base = {
        "volume_ratio": np.nan,
        "rth_volume_reference_window_configured": window,
        "rth_volume_reference_min_valid_sessions": min_valid_sessions,
        "rth_volume_reference_valid_session_count": 0,
        "rth_volume_reference_session_dates": "",
        "rth_volume_reference_excluded_premarket_rows": 0,
        "rth_volume_reference_excluded_postmarket_rows": 0,
        "rth_volume_reference_excluded_early_close_dates": "",
        "rth_volume_reference_status": "unavailable_coverage",
        "source_row_identifier": "",
        "source_hash_or_index": "",
        "invalid_reason": "",
    }
    if bars.empty or "timestamp_utc" not in bars.columns:
        return base | {"invalid_reason": "intraday_bars_missing"}
    work = bars.copy()
    work["timestamp_utc"] = pd.to_datetime(work["timestamp_utc"], utc=True, errors="coerce")
    work = work.dropna(subset=["timestamp_utc"])
    work["date_et"] = work["timestamp_utc"].dt.tz_convert(ET).dt.date
    work["time_et"] = work["timestamp_utc"].dt.tz_convert(ET).dt.time
    current_day = pd.Timestamp(day).date()
    current_session = get_nyse_session(current_day, nyse_calendar)
    if not current_session.get("is_regular_session") or current_session.get("is_early_close"):
        return base | {"invalid_reason": "current_session_not_standard_rth"}
    open_time = parse_et_time(str(current_session.get("regular_open_et", "09:30")), time(9, 30))
    excluded_pre = int(((work["date_et"] == current_day) & (work["time_et"] < open_time)).sum())
    excluded_post = int(((work["date_et"] == current_day) & (work["time_et"] > cutoff_time)).sum())
    current = work[(work["date_et"].eq(current_day)) & (work["time_et"] >= open_time) & (work["time_et"] <= cutoff_time)]
    current_volume = safe_float(current.get("volume", pd.Series(dtype=float)).sum(), np.nan)
    regular_sessions = nyse_calendar[
        nyse_calendar.get("is_regular_session", pd.Series(dtype=bool)).astype(bool)
        & ~nyse_calendar.get("is_early_close", pd.Series(dtype=bool)).astype(bool)
    ].copy() if not nyse_calendar.empty else pd.DataFrame()
    if regular_sessions.empty:
        return base | {"invalid_reason": "nyse_calendar_regular_sessions_missing"}
    prior_dates = [pd.Timestamp(d).date() for d in regular_sessions["session_date"].astype(str).tolist() if pd.Timestamp(d).date() < current_day]
    samples: list[float] = []
    used_dates: list[str] = []
    excluded_early: list[str] = []
    for ref_day in sorted(prior_dates, reverse=True):
        session = get_nyse_session(ref_day, nyse_calendar)
        if session.get("is_early_close"):
            excluded_early.append(pd.Timestamp(ref_day).date().isoformat())
            continue
        ref_open = parse_et_time(str(session.get("regular_open_et", "09:30")), time(9, 30))
        sample = work[(work["date_et"].eq(ref_day)) & (work["time_et"] >= ref_open) & (work["time_et"] <= cutoff_time)]
        volume = safe_float(sample.get("volume", pd.Series(dtype=float)).sum(), np.nan)
        if pd.notna(volume) and volume > 0:
            samples.append(volume)
            used_dates.append(pd.Timestamp(ref_day).date().isoformat())
        if len(samples) >= window:
            break
    paired = sorted(zip(used_dates, samples), key=lambda x: x[0])
    used_dates = [d for d, _ in paired]
    samples = [v for _, v in paired]
    status = "eligible" if len(samples) >= min_valid_sessions and pd.notna(current_volume) else "unavailable_coverage"
    ratio = current_volume / float(np.mean(samples)) if status == "eligible" and samples else np.nan
    source_id = f"rth_ref_count={len(samples)};dates={';'.join(used_dates)}"
    return base | {
        "volume_ratio": ratio,
        "rth_volume_reference_valid_session_count": len(samples),
        "rth_volume_reference_session_dates": ";".join(used_dates),
        "rth_volume_reference_excluded_premarket_rows": excluded_pre,
        "rth_volume_reference_excluded_postmarket_rows": excluded_post,
        "rth_volume_reference_excluded_early_close_dates": ";".join(excluded_early),
        "rth_volume_reference_status": status,
        "source_row_identifier": source_id,
        "source_hash_or_index": hashlib.sha256(source_id.encode("utf-8")).hexdigest() if source_id else "",
        "invalid_reason": "" if status == "eligible" else "volume_reference_insufficient",
    }


def prior_available_aum_record(aum: pd.DataFrame, ticker: str, decision_ts: pd.Timestamp, prior_regular_close_ts: pd.Timestamp) -> dict[str, Any]:
    base = {
        "ticker": ticker,
        "aum_value": math.nan,
        "aum_value_type": "",
        "aum_source": "aum_history_missing",
        "aum_proxy": False,
        "aum_as_of_timestamp_utc": "",
        "aum_effective_available_at_utc": "",
        "source_path_or_provider": "market_bomb_history/leveraged_etf_aum_history.csv",
        "source_row_identifier": "",
        "source_hash_or_index": "",
        "selection_policy_version": "latest_clean_primary_aum_v1",
        "selection_status": "unavailable_no_candidate",
        "primary_eligible": False,
        "analysis_mode": "unavailable",
        "availability_state": "coverage_gap_or_no_candidate",
        "availability_status": "unavailable",
        "availability_failure_reason": "aum_history_missing",
        "quality_status": "not_run",
        "quality_failure_reason": "",
    }
    if aum.empty:
        return base
    work = aum[aum.get("ticker", pd.Series(dtype=str)).astype(str).eq(ticker)].copy()
    if work.empty:
        return base | {"aum_source": "ticker_aum_missing", "availability_failure_reason": "ticker_aum_missing"}
    if "date" in work.columns and "as_of_timestamp_utc" not in work.columns and "aum_as_of_timestamp_utc" not in work.columns:
        return base | {
            "aum_source": "date_only_aum_not_primary",
            "selection_status": "selected_invalid",
            "analysis_mode": "historical_label_only_not_primary",
            "availability_state": "data_quality_blocked",
            "availability_failure_reason": "date_only_aum_not_primary",
        }
    asof_col = "aum_as_of_timestamp_utc" if "aum_as_of_timestamp_utc" in work.columns else "as_of_timestamp_utc" if "as_of_timestamp_utc" in work.columns else "effective_available_at_utc" if "effective_available_at_utc" in work.columns else ""
    eff_col = "aum_effective_available_at_utc" if "aum_effective_available_at_utc" in work.columns else "effective_available_at_utc" if "effective_available_at_utc" in work.columns else asof_col
    if not asof_col or not eff_col:
        return base | {"aum_source": "aum_timestamp_missing", "selection_status": "selected_invalid", "availability_state": "data_quality_blocked", "availability_failure_reason": "aum_timestamp_missing"}
    work["aum_asof"] = pd.to_datetime(work[asof_col], utc=True, errors="coerce")
    work["aum_effective"] = pd.to_datetime(work[eff_col], utc=True, errors="coerce")
    invalid_ts = work["aum_asof"].isna() | work["aum_effective"].isna()
    work = work[~invalid_ts].copy()
    if work.empty:
        return base | {"aum_source": "aum_timestamp_missing", "selection_status": "selected_invalid", "availability_state": "data_quality_blocked", "availability_failure_reason": "aum_timestamp_missing"}
    late = work[(work["aum_asof"] > prior_regular_close_ts) | (work["aum_effective"] > prior_regular_close_ts)]
    work = work[(work["aum_asof"] <= prior_regular_close_ts) & (work["aum_effective"] <= prior_regular_close_ts)].copy()
    if work.empty:
        reason = "coverage_not_started" if not late.empty else "no_prior_available_aum"
        return base | {"aum_source": "no_prior_available_aum", "selection_status": "unavailable_coverage_not_started", "availability_state": "coverage_not_started", "availability_failure_reason": reason}
    row = work.sort_values(["aum_effective", "aum_asof"]).iloc[-1]
    row_id = str(row.name)
    value_type = str(row.get("aum_value_type", "net_assets_usd")).lower()
    for col in ["net_assets_usd", "aum_usd", "assets"]:
        value = safe_float(row.get(col, np.nan), np.nan)
        if col in row and pd.notna(value) and value > 0 and value_type == "net_assets_usd":
            return base | {
                "aum_value": value,
                "aum_value_type": "net_assets_usd",
                "aum_source": "previous_available_net_assets_usd",
                "aum_as_of_timestamp_utc": row.get(asof_col, ""),
                "aum_effective_available_at_utc": row.get(eff_col, ""),
                "source_row_identifier": row_id,
                "source_hash_or_index": row_id,
                "selection_status": "selected_clean",
                "primary_eligible": True,
                "analysis_mode": "primary",
                "availability_state": "candidate_available_clean",
                "availability_status": "available",
                "availability_failure_reason": "",
                "quality_status": "passed",
            }
    if "shares_outstanding" in row and "prior_close" in row:
        return base | {
            "aum_value": safe_float(row["shares_outstanding"]) * safe_float(row["prior_close"]),
            "aum_value_type": "surrogate_shares_x_price",
            "aum_source": "imputed_surrogate_exploratory",
            "aum_proxy": True,
            "source_row_identifier": row_id,
            "source_hash_or_index": row_id,
            "selection_status": "selected_invalid",
            "analysis_mode": "imputed_surrogate_exploratory",
            "availability_state": "data_quality_blocked",
            "availability_failure_reason": "imputed_surrogate_exploratory_not_primary",
            "quality_status": "failed",
            "quality_failure_reason": "surrogate_aum_not_primary",
        }
    return base | {"aum_source": "aum_value_missing", "selection_status": "unavailable_missing_required_input", "availability_failure_reason": "aum_value_missing"}


def prior_available_aum(aum: pd.DataFrame, ticker: str, decision_ts: pd.Timestamp, prior_regular_close_ts: pd.Timestamp | None = None) -> tuple[float, str, bool]:
    record = prior_available_aum_record(aum, ticker, decision_ts, prior_regular_close_ts or decision_ts)
    return safe_float(record["aum_value"]), str(record["aum_source"]), bool(record["aum_proxy"])


def load_intraday_bars(root: Path, target: str) -> pd.DataFrame:
    for path in [
        root / "market_bomb_history" / "intraday_bars" / f"{target}_5m.csv",
        root / "market_bomb_history" / "intraday_bars" / f"{target}.csv",
    ]:
        if path.exists():
            try:
                df = pd.read_csv(path)
                cols = {str(c).lower(): c for c in df.columns}
                ts_col = cols.get("timestamp_utc") or cols.get("datetime") or cols.get("timestamp")
                if ts_col is None:
                    return pd.DataFrame()
                out = df.copy()
                out["timestamp_utc"] = pd.to_datetime(out[ts_col], utc=True, errors="coerce")
                for col in ["open", "high", "low", "close", "volume", "prior_regular_session_close", "prior_close", "prior_session_return", "prior_20d_realized_vol"]:
                    if col in out.columns:
                        out[col] = pd.to_numeric(out[col], errors="coerce")
                return out.dropna(subset=["timestamp_utc"]).sort_values("timestamp_utc")
            except Exception:
                return pd.DataFrame()
    return pd.DataFrame()


def intraday_bars_path(root: Path, target: str) -> Path | None:
    for path in [
        root / "market_bomb_history" / "intraday_bars" / f"{target}_5m.csv",
        root / "market_bomb_history" / "intraday_bars" / f"{target}.csv",
    ]:
        if path.exists():
            return path
    return None


def build_market_level_intraday_decision_universe(root: Path, cfg: dict[str, Any]) -> pd.DataFrame:
    return build_market_level_intraday_universe_with_gate(root, cfg)[0]


def build_market_level_intraday_universe_with_gate(root: Path, cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    targets = [str(t) for t in cfg.get("targets", ["SPY", "QQQ", "SOXX"]) if str(t) in {"SPY", "QQQ", "SOXX"}]
    nyse_calendar = load_nyse_calendar(root)
    provenance = validate_nyse_calendar_provenance(root, nyse_calendar)
    decision_bar = parse_et_time(cfg.get("primary_decision_bar_et", "15:30"), time(15, 30))
    close_bar_time = parse_et_time(cfg.get("primary_close_bar_et", "16:00"), time(16, 0))
    rows: list[dict[str, Any]] = []
    gate_rows: list[dict[str, Any]] = []
    for target in targets:
        bars = load_intraday_bars(root, target)
        if bars.empty or "timestamp_utc" not in bars.columns:
            gate_rows.append({
                "target_market": target,
                "model_clock": "INTRADAY",
                "intraday_source_coverage_start_et": "",
                "intraday_source_coverage_end_et": "",
                "calendar_validation_status": provenance.get("status", "failed"),
                "calendar_validation_failure_reason": provenance.get("reason", ""),
                "universe_generation_status": "unavailable_coverage",
                "universe_generation_reason": "intraday_bars_missing",
                "candidate_decision_count": 0,
                "target_clock_gate_integrity_status": "unavailable_coverage",
                "target_clock_gate_reason": "intraday_bars_missing",
                "included_regular_session_count": 0,
                "excluded_non_regular_session_count": 0,
                "excluded_early_close_session_count": 0,
            })
            continue
        work = bars.copy()
        work["date_et"] = work["timestamp_utc"].dt.tz_convert(ET).dt.date
        start = min(work["date_et"])
        end = max(work["date_et"])
        if provenance.get("status") != "passed" or nyse_calendar.empty or "session_date" not in nyse_calendar.columns:
            gate_rows.append({
                "target_market": target,
                "model_clock": "INTRADAY",
                "intraday_source_coverage_start_et": pd.Timestamp(start).date().isoformat(),
                "intraday_source_coverage_end_et": pd.Timestamp(end).date().isoformat(),
                "calendar_validation_status": provenance.get("status", "failed"),
                "calendar_validation_failure_reason": provenance.get("reason", "nyse_calendar_missing"),
                "universe_generation_status": "selected_invalid",
                "universe_generation_reason": "nyse_calendar_provenance_validation_failed",
                "candidate_decision_count": 0,
                "target_clock_gate_integrity_status": "selected_invalid",
                "target_clock_gate_reason": "nyse_calendar_provenance_validation_failed:" + str(provenance.get("reason", "nyse_calendar_missing")),
                "included_regular_session_count": 0,
                "excluded_non_regular_session_count": 0,
                "excluded_early_close_session_count": 0,
            })
            continue
        calendar = nyse_calendar.copy()
        calendar["session_date"] = pd.to_datetime(calendar["session_date"], errors="coerce").dt.date
        calendar = calendar[(calendar["session_date"] >= start) & (calendar["session_date"] <= end)].copy()
        included = 0
        excluded_non_regular = 0
        excluded_early_close = 0
        for _, session in calendar.iterrows():
            day = session.get("session_date")
            if pd.isna(day):
                continue
            is_regular = bool(session.get("is_regular_session", False))
            is_early = bool(session.get("is_early_close", False))
            if not is_regular:
                excluded_non_regular += 1
                continue
            if is_early:
                excluded_early_close += 1
                continue
            included += 1
            decision_ts = pd.Timestamp.combine(pd.Timestamp(day).date(), decision_bar).tz_localize(ET).tz_convert(UTC)
            day_bars = work[work["date_et"].eq(day)].copy()
            et_times = day_bars["timestamp_utc"].dt.tz_convert(ET) if not day_bars.empty else pd.Series(dtype="datetime64[ns, UTC]")
            bar_1530 = exact_bar(day_bars, et_times, decision_bar) if not day_bars.empty else None
            bar_1600 = exact_bar(day_bars, et_times, close_bar_time) if not day_bars.empty else None
            price_1530 = safe_float(bar_1530.get("close")) if bar_1530 is not None else np.nan
            price_1600 = safe_float(bar_1600.get("close")) if bar_1600 is not None else np.nan
            outcome_available = bar_1530 is not None and bar_1600 is not None and pd.notna(price_1530) and price_1530 > 0 and pd.notna(price_1600)
            after_1530 = day_bars[(et_times.dt.time > decision_bar) & (et_times.dt.time <= close_bar_time)] if not day_bars.empty else pd.DataFrame()
            rows.append({
                "target_market": target,
                "decision_date": pd.Timestamp(day).date().isoformat(),
                "decision_timestamp_utc": decision_ts.isoformat(),
                "model_clock": "INTRADAY",
                "decision_time_policy": "intraday_1530_et_v1",
                "coverage_start_et": pd.Timestamp(start).date().isoformat(),
                "coverage_end_et": pd.Timestamp(end).date().isoformat(),
                "coverage_window_basis": MARKET_LEVEL_INTRADAY_UNIVERSE_POLICY,
                "calendar_coverage_status": session.get("calendar_coverage_status", "covered"),
                "is_regular_session": is_regular,
                "is_early_close": is_early,
                "decision_universe_status": "included",
                "decision_universe_reason": "",
                "intraday_outcome_availability_status": "available" if outcome_available else "outcome_unavailable",
                "intraday_outcome_availability_reason": "" if outcome_available else "required_1530_or_1600_bar_missing",
                "actual_1530_bar_timestamp_utc": bar_1530.get("timestamp_utc") if bar_1530 is not None else "",
                "actual_1600_bar_timestamp_utc": bar_1600.get("timestamp_utc") if bar_1600 is not None else "",
                "intraday_return_1530_to_close": price_1600 / price_1530 - 1 if outcome_available else np.nan,
                "intraday_absolute_return_1530_to_close": abs(price_1600 / price_1530 - 1) if outcome_available else np.nan,
                "intraday_range_1530_to_close": (safe_float(after_1530.get("high", pd.Series([np.nan])).max()) - safe_float(after_1530.get("low", pd.Series([np.nan])).min())) / price_1530 if outcome_available and not after_1530.empty else np.nan,
            })
        gate_rows.append({
            "target_market": target,
            "model_clock": "INTRADAY",
            "intraday_source_coverage_start_et": pd.Timestamp(start).date().isoformat(),
            "intraday_source_coverage_end_et": pd.Timestamp(end).date().isoformat(),
            "calendar_validation_status": provenance.get("status", "failed"),
            "calendar_validation_failure_reason": provenance.get("reason", ""),
            "universe_generation_status": "generated" if included else "unavailable_coverage",
            "universe_generation_reason": "" if included else "no_regular_sessions_in_source_window",
            "candidate_decision_count": included,
            "target_clock_gate_integrity_status": "valid" if included else "unavailable_coverage",
            "target_clock_gate_reason": "" if included else "no_regular_sessions_in_source_window",
            "included_regular_session_count": included,
            "excluded_non_regular_session_count": excluded_non_regular,
            "excluded_early_close_session_count": excluded_early_close,
        })
    return (
        pd.DataFrame(rows, columns=MARKET_LEVEL_INTRADAY_DECISION_UNIVERSE_COLUMNS),
        pd.DataFrame(gate_rows, columns=MARKET_LEVEL_INTRADAY_UNIVERSE_GATE_COLUMNS),
    )


def component_selection_row(
    *,
    target: str,
    decision_ts: pd.Timestamp,
    component_type: str,
    status: str,
    primary_eligible: bool,
    invalid_reason: str = "",
    fund_ticker: str = "",
    row: pd.Series | dict[str, Any] | None = None,
    asof: Any = "",
    effective: Any = "",
    source_path: str = "",
    selection_bundle_id: str = "",
    selected_value_or_reference: Any = "",
) -> dict[str, Any]:
    source_id = ""
    source_hash = ""
    if row is not None:
        if isinstance(row, pd.Series):
            source_id = str(row.name)
        else:
            source_id = str(row.get("source_row_identifier", ""))
        source_hash = row_content_hash(row)
    return {
        "target_market": target,
        "decision_timestamp_utc": decision_ts.isoformat(),
        "selection_bundle_id": selection_bundle_id,
        "source_component_type": component_type,
        "input_component": component_type,
        "fund_ticker": fund_ticker,
        "selected_source_row_identifier": source_id,
        "source_row_identifier": source_id,
        "selected_source_content_hash": source_hash,
        "source_hash_or_index": source_hash,
        "selected_source_as_of_timestamp_utc": asof,
        "selected_source_effective_available_at_utc": effective,
        "source_path_or_provider": source_path,
        "selection_status": status,
        "availability_state": "valid" if primary_eligible else ("selected_invalid" if status == "selected_invalid" else "unavailable_coverage"),
        "primary_eligible": primary_eligible,
        "candidate_eligibility_status": "eligible" if primary_eligible else "unavailable",
        "selected_for_model": primary_eligible,
        "invalid_reason": invalid_reason,
        "availability_failure_reason": "" if primary_eligible else invalid_reason,
        "selected_value_or_reference": selected_value_or_reference,
        "selection_policy_version": LEVERAGED_BUNDLE_POLICY_REVISION,
        "selection_policy_revision": LEVERAGED_BUNDLE_POLICY_REVISION,
    }


def build_leveraged_etf_input_selection_bundle(
    *,
    target: str,
    decision_timestamp_utc: Any,
    underlying: str,
    funds: list[dict[str, Any]],
    bars: pd.DataFrame,
    aum_history: pd.DataFrame,
    provider_rules: dict[str, Any] | None,
    nyse_calendar: pd.DataFrame,
    cfg: dict[str, Any],
    root: Path | None = None,
) -> dict[str, Any]:
    decision_ts = parse_ts(decision_timestamp_utc)
    if decision_ts is None:
        decision_ts = pd.Timestamp(decision_timestamp_utc, tz=UTC)
    day = decision_ts.tz_convert(ET).date()
    bundle_id = hashlib.sha256(f"{target}|{decision_ts.isoformat()}|{LEVERAGED_BUNDLE_POLICY_REVISION}".encode("utf-8")).hexdigest()
    decision_bar = parse_et_time(cfg.get("primary_decision_bar_et", "15:30"), time(15, 30))
    min_cfg = cfg.get("minimum_samples", {})
    default_volume_min = 20 if root is not None and (root / RULES_PATH).exists() else 0
    volume_min = int(cfg.get("leveraged_etf_volume_reference_min_sessions", min_cfg.get("leveraged_etf_volume_reference_min_sessions", default_volume_min)))
    volume_window = int(cfg.get("leveraged_etf_volume_reference_window", min_cfg.get("leveraged_etf_volume_reference_window", 20)))
    source_path = str(intraday_bars_path(root, target) or "") if root is not None else ""
    provider_rules = provider_rules or {}
    provider_ok = bool(
        provider_rules.get("provider_bar_semantics_verified", False)
        and str(provider_rules.get("bar_timestamp_convention", cfg.get("bar_timestamp_convention", ""))) == "bar_end"
        and str(provider_rules.get("provider_bar_semantics_source", "")).strip()
        and str(provider_rules.get("provider_bar_semantics_verified_at_utc", "")).strip()
    )
    components = [
        component_selection_row(
            target=target,
            decision_ts=decision_ts,
            component_type="provider_rule",
            status="selected" if provider_ok else "selected_invalid",
            primary_eligible=provider_ok,
            invalid_reason="" if provider_ok else "provider_bar_semantics_unverified",
            row=provider_rules,
            asof=provider_rules.get("provider_bar_semantics_verified_at_utc", ""),
            effective=provider_rules.get("provider_bar_semantics_verified_at_utc", ""),
            source_path=str(EXPIRY_INTRADAY_RULES_PATH).replace("\\", "/"),
            selection_bundle_id=bundle_id,
            selected_value_or_reference=str(provider_rules.get("bar_timestamp_convention", "")),
        )
    ]
    session = get_nyse_session(day, nyse_calendar)
    if session.get("calendar_coverage_status") != "covered" or not session.get("is_regular_session") or session.get("is_early_close"):
        reason = "early_close_session_excluded_from_primary" if session.get("is_early_close") else "nyse_regular_session_unavailable"
        components.append(component_selection_row(target=target, decision_ts=decision_ts, component_type="universe", status="unavailable_coverage", primary_eligible=False, invalid_reason=reason, selection_bundle_id=bundle_id))
        return {"target_market": target, "decision_timestamp_utc": decision_ts.isoformat(), "selection_bundle_id": bundle_id, "components": components, "status": "insufficient_data", "failure_reason": reason}
    work = bars.copy()
    if not work.empty and "timestamp_utc" in work.columns:
        work["timestamp_utc"] = pd.to_datetime(work["timestamp_utc"], utc=True, errors="coerce")
        work = work.dropna(subset=["timestamp_utc"])
        work["date_et"] = work["timestamp_utc"].dt.tz_convert(ET).dt.date
        work = work[work["date_et"].eq(day)].copy()
    et_times = work["timestamp_utc"].dt.tz_convert(ET) if not work.empty and "timestamp_utc" in work.columns else pd.Series(dtype="datetime64[ns, UTC]")
    bar_1530 = exact_bar(work, et_times, decision_bar) if not work.empty else None
    components.append(component_selection_row(target=target, decision_ts=decision_ts, component_type="bar_1530", status="selected" if bar_1530 is not None else "unavailable_coverage", primary_eligible=bar_1530 is not None, invalid_reason="" if bar_1530 is not None else "required_1530_bar_missing", row=bar_1530, asof=bar_1530.get("timestamp_utc") if bar_1530 is not None else "", effective=bar_1530.get("timestamp_utc") if bar_1530 is not None else "", source_path=source_path, selection_bundle_id=bundle_id, selected_value_or_reference=bar_1530.get("close") if bar_1530 is not None else ""))
    prior_regular_close_ts = previous_regular_session_close_utc(day, nyse_calendar)
    prior_close = safe_float(work.iloc[0].get("prior_regular_session_close", np.nan)) if not work.empty else np.nan
    prior_ok = prior_regular_close_ts is not None and pd.notna(prior_close) and prior_close > 0
    components.append(component_selection_row(target=target, decision_ts=decision_ts, component_type="prior_close", status="selected" if prior_ok else "unavailable_coverage", primary_eligible=prior_ok, invalid_reason="" if prior_ok else "prior_regular_close_missing", row={"source_row_identifier": f"prior_close:{day}", "prior_regular_close": prior_close}, asof=prior_regular_close_ts.isoformat() if prior_regular_close_ts is not None else "", effective=prior_regular_close_ts.isoformat() if prior_regular_close_ts is not None else "", source_path=source_path, selection_bundle_id=bundle_id, selected_value_or_reference=prior_close))
    volume = strict_rth_volume_reference(bars, day, decision_bar, nyse_calendar, window=volume_window, min_valid_sessions=volume_min)
    components.append(component_selection_row(target=target, decision_ts=decision_ts, component_type="volume_ref", status="selected" if volume["rth_volume_reference_status"] == "eligible" else "unavailable_coverage", primary_eligible=volume["rth_volume_reference_status"] == "eligible", invalid_reason=volume.get("invalid_reason", ""), row={"source_row_identifier": volume.get("source_row_identifier", ""), **volume}, asof=decision_ts.isoformat(), effective=decision_ts.isoformat(), source_path=source_path, selection_bundle_id=bundle_id, selected_value_or_reference=volume.get("volume_ratio", np.nan)) | volume)
    prior_ts_for_aum = prior_regular_close_ts or decision_ts
    eligible_funds = 0
    for fund in funds:
        ticker = str(fund.get("ticker", ""))
        record = prior_available_aum_record(aum_history, ticker, decision_ts, prior_ts_for_aum)
        eligible = bool(record.get("primary_eligible", False))
        eligible_funds += int(eligible)
        record_status = "selected" if eligible else ("selected_invalid" if str(record.get("selection_status", "")) == "selected_invalid" or str(record.get("availability_state", "")) == "data_quality_blocked" else "unavailable_coverage")
        components.append(component_selection_row(target=target, decision_ts=decision_ts, component_type="aum", fund_ticker=ticker, status=record_status, primary_eligible=eligible, invalid_reason="" if eligible else str(record.get("availability_failure_reason", "")), row=record, asof=record.get("aum_as_of_timestamp_utc", ""), effective=record.get("aum_effective_available_at_utc", ""), source_path=record.get("source_path_or_provider", ""), selection_bundle_id=bundle_id, selected_value_or_reference=record.get("aum_value", np.nan)) | {"aum_value": record.get("aum_value", np.nan), "aum_value_type": record.get("aum_value_type", "")})
    universe_ok = eligible_funds == len(funds) and len(funds) > 0
    components.append(component_selection_row(target=target, decision_ts=decision_ts, component_type="universe", status="selected" if universe_ok else "unavailable_coverage", primary_eligible=universe_ok, invalid_reason="" if universe_ok else "primary_universe_incomplete", row={"source_row_identifier": f"universe:{target}:{eligible_funds}/{len(funds)}", "funds": ",".join(str(f.get("ticker", "")) for f in funds)}, asof=decision_ts.isoformat(), effective=decision_ts.isoformat(), source_path=str(LEVERAGED_UNIVERSE_PATH).replace("\\", "/"), selection_bundle_id=bundle_id, selected_value_or_reference=f"{eligible_funds}/{len(funds)}") | {"required_fund_count": len(funds), "eligible_fund_count": eligible_funds})
    statuses = [c for c in components if not bool(c.get("primary_eligible", False))]
    if any(c.get("selection_status") == "selected_invalid" for c in statuses):
        status = "data_quality_blocked"
    elif statuses:
        status = "insufficient_data"
    else:
        status = "eligible_primary"
    return {"target_market": target, "decision_timestamp_utc": decision_ts.isoformat(), "selection_bundle_id": bundle_id, "components": components, "status": status, "failure_reason": ";".join(sorted(set(str(c.get("invalid_reason", "")) for c in statuses if str(c.get("invalid_reason", "")))))}


def build_leveraged_etf_panel(root: Path, cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    universe = leveraged_universe(root)
    aum = load_leveraged_aum(root)
    nyse_calendar = load_nyse_calendar(root)
    rows: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    component_manifest: list[dict[str, Any]] = []
    decision_bar = parse_et_time(cfg.get("primary_decision_bar_et", "15:30"), time(15, 30))
    close_bar_time = parse_et_time(cfg.get("primary_close_bar_et", "16:00"), time(16, 0))
    timestamp_convention = str(cfg.get("bar_timestamp_convention", "bar_end"))
    provider_rules = expiry_intraday_rules(root)
    for family, funds in universe.items():
        if not isinstance(funds, list):
            continue
        targets = sorted({str(f["target"]) for f in funds})
        for target in targets:
            bars = load_intraday_bars(root, target)
            if bars.empty:
                audit.append({"target_market": target, "feature_family": "LeveragedETF", "availability_status": "unavailable", "availability_failure_reason": "intraday_bars_missing"})
                continue
            bars["date_et"] = bars["timestamp_utc"].dt.tz_convert(ET).dt.date
            for day, group in bars.groupby("date_et"):
                session = get_nyse_session(day, nyse_calendar)
                decision_ts = pd.Timestamp.combine(pd.Timestamp(day).date(), decision_bar).tz_localize(ET).tz_convert(UTC)
                fund_rows = [f for f in funds if str(f["target"]) == target]
                bundle = build_leveraged_etf_input_selection_bundle(
                    target=target,
                    decision_timestamp_utc=decision_ts,
                    underlying=target,
                    funds=fund_rows,
                    bars=bars,
                    aum_history=aum,
                    provider_rules=provider_rules,
                    nyse_calendar=nyse_calendar,
                    cfg=cfg,
                    root=root,
                )
                components = bundle["components"]
                component_manifest.extend([{k: c.get(k, "") for k in LEVERAGED_ETF_COMPONENT_MANIFEST_COLUMNS} for c in components])
                component_map = {(c.get("source_component_type"), c.get("fund_ticker", "")): c for c in components}
                failure_reason = str(bundle.get("failure_reason", ""))
                if bundle.get("status") != "eligible_primary":
                    audit.append({
                        **session,
                        "target_market": target,
                        "feature_family": "LeveragedETF",
                        "decision_timestamp_utc": decision_ts.isoformat(),
                        "bar_timestamp_convention": timestamp_convention,
                        "availability_status": "unavailable",
                        "availability_failure_reason": failure_reason,
                        "leveraged_etf_primary_input_integrity_status": bundle.get("status"),
                        "leveraged_etf_primary_input_gate": bundle.get("status"),
                    })
                    continue
                bar_1530_comp = component_map.get(("bar_1530", ""), {})
                prior_close_comp = component_map.get(("prior_close", ""), {})
                volume_comp = component_map.get(("volume_ref", ""), {})
                price_1530 = safe_float(bar_1530_comp.get("selected_value_or_reference"))
                prior_close = safe_float(prior_close_comp.get("selected_value_or_reference"))
                if pd.isna(prior_close) or prior_close <= 0 or pd.isna(price_1530):
                    audit.append({**session, "target_market": target, "feature_family": "LeveragedETF", "decision_timestamp_utc": decision_ts.isoformat(), "availability_status": "unavailable", "availability_failure_reason": "selected_bundle_price_missing", "leveraged_etf_primary_input_integrity_status": "data_quality_blocked", "leveraged_etf_primary_input_gate": "data_quality_blocked"})
                    continue
                r_to_1530 = price_1530 / prior_close - 1
                pressure = 0.0
                aum_components = [c for c in components if c.get("source_component_type") == "aum"]
                for fund in fund_rows:
                    acomp = component_map.get(("aum", str(fund["ticker"])), {})
                    pressure += leveraged_pressure(float(fund["leverage"]), safe_float(acomp.get("selected_value_or_reference")), r_to_1530)
                group = group.sort_values("timestamp_utc")
                et_times = group["timestamp_utc"].dt.tz_convert(ET)
                at_1530 = group[et_times.dt.time <= decision_bar]
                after_1530 = group[(et_times.dt.time > decision_bar) & (et_times.dt.time <= close_bar_time)]
                volume_ref_count = int(volume_comp.get("rth_volume_reference_valid_session_count", 0))
                volume_ref_last = str(volume_comp.get("rth_volume_reference_session_dates", "")).split(";")[-1] if str(volume_comp.get("rth_volume_reference_session_dates", "")) else ""
                prior_session_return = safe_float(group.iloc[0].get("prior_session_return", np.nan))
                prior_20d_realized_vol = safe_float(group.iloc[0].get("prior_20d_realized_vol", np.nan))
                flags = expiry_flags_for_date(load_expiry_calendar(root), day)
                rows.append({
                    "analysis_id": f"leveraged_etf_{target}_{day}",
                    "module": "LeveragedETF",
                    "feature_family": "LeveragedETF",
                    "feature_name": f"{family}_pressure",
                    "target_market": target,
                    "decision_date": pd.Timestamp(day).date().isoformat(),
                    "decision_timestamp_utc": decision_ts.isoformat(),
                    "feature_value": pressure,
                    "feature_unit": "usd_pressure_proxy",
                    "feature_as_of_timestamp_utc": decision_ts.isoformat(),
                    "effective_available_at_utc": decision_ts.isoformat(),
                    "feature_age_hours": 0.0,
                    "availability_basis": "last_bar_completed_by_1530_et",
                    "availability_confidence": "medium",
                    "source_path_or_provider": f"market_bomb_history/intraday_bars/{target}_5m.csv;market_bomb_history/leveraged_etf_aum_history.csv",
                    "source_hash_or_request_id": "",
                    "aggregate_pressure_usd": pressure,
                    "pressure_sign": "positive" if pressure > 0 else "negative" if pressure < 0 else "flat",
                    "return_prior_regular_close_to_1530": r_to_1530,
                    "return_prior_close_to_1530": r_to_1530,
                    "absolute_return_prior_regular_close_to_1530": abs(r_to_1530),
                    "intraday_realized_vol_to_1530": pd.to_numeric(at_1530["close"], errors="coerce").pct_change().std() * math.sqrt(78) if len(at_1530) > 2 else np.nan,
                    "intraday_volume_ratio_vs_prior_20d_same_time": safe_float(volume_comp.get("volume_ratio")),
                    "volume_reference_window": volume_comp.get("rth_volume_reference_window_configured", ""),
                    "volume_reference_last_date": volume_ref_last,
                    "volume_reference_row_count": volume_ref_count,
                    "rth_volume_reference_window_configured": volume_comp.get("rth_volume_reference_window_configured", ""),
                    "rth_volume_reference_min_valid_sessions": volume_comp.get("rth_volume_reference_min_valid_sessions", ""),
                    "rth_volume_reference_valid_session_count": volume_comp.get("rth_volume_reference_valid_session_count", ""),
                    "rth_volume_reference_session_dates": volume_comp.get("rth_volume_reference_session_dates", ""),
                    "rth_volume_reference_excluded_premarket_rows": volume_comp.get("rth_volume_reference_excluded_premarket_rows", ""),
                    "rth_volume_reference_excluded_postmarket_rows": volume_comp.get("rth_volume_reference_excluded_postmarket_rows", ""),
                    "rth_volume_reference_excluded_early_close_dates": volume_comp.get("rth_volume_reference_excluded_early_close_dates", ""),
                    "rth_volume_reference_status": volume_comp.get("rth_volume_reference_status", ""),
                    "prior_session_return": prior_session_return,
                    "prior_20d_realized_vol": prior_20d_realized_vol,
                    "weekday": pd.Timestamp(day).weekday(),
                    **flags,
                    "data_type": "reconstructed_proxy",
                    "is_proxy": True,
                    "observed_flow": False,
                    "quality_grade": "medium",
                    "availability_status": "available",
                    "availability_failure_reason": "",
                    "formula_version": "leveraged_etf_rebalancing_pressure_v1",
                    "analysis_mode": "reconstructed_proxy_primary",
                    "sample_split": "expanding_window",
                    "bar_timestamp_convention": cfg.get("bar_timestamp_convention", "bar_end"),
                    "decision_price_method": "completed_bar_close",
                    "decision_bar_timestamp_et": "15:30",
                    "close_price_method": "completed_regular_close_bar_close",
                    "close_bar_timestamp_et": "16:00",
                    "actual_1530_bar_timestamp_utc": bar_1530_comp.get("selected_source_as_of_timestamp_utc", ""),
                    "actual_1600_bar_timestamp_utc": "",
                    "prior_regular_close_timestamp_utc": prior_close_comp.get("selected_source_as_of_timestamp_utc", ""),
                    "selection_bundle_id": bundle.get("selection_bundle_id", ""),
                    "aum_as_of_timestamp_utc": ";".join(str(c.get("selected_source_as_of_timestamp_utc", "")) for c in aum_components),
                    "aum_effective_available_at_utc": ";".join(str(c.get("selected_source_effective_available_at_utc", "")) for c in aum_components),
                    "selected_aum_source_row_identifiers": ";".join(str(c.get("selected_source_row_identifier", "")) for c in aum_components),
                    "selected_aum_source_hashes": ";".join(str(c.get("selected_source_content_hash", "")) for c in aum_components),
                    "selected_aum_primary_eligible_flags": ";".join(str(bool(c.get("primary_eligible", False))).lower() for c in aum_components),
                    "selected_aum_selection_policy_version": ";".join(str(c.get("selection_policy_revision", "")) for c in aum_components),
                    "selected_source_row_identifier": ";".join(str(c.get("selected_source_row_identifier", "")) for c in components),
                    "selected_source_hash_or_index": ";".join(str(c.get("selected_source_content_hash", "")) for c in components),
                    "selected_source_effective_available_at_utc": ";".join(str(c.get("selected_source_effective_available_at_utc", "")) for c in components),
                    "selection_policy_version": LEVERAGED_BUNDLE_POLICY_REVISION,
                    "primary_eligible": True,
                    "scope_integrity_status": "eligible_primary",
                    "scope_integrity_failure_reason": "",
                    "leveraged_etf_primary_input_integrity_status": "eligible_primary",
                    "leveraged_etf_primary_input_gate": "eligible_primary",
                    "universe_completeness": "complete",
                    "calendar_session_status": session["calendar_coverage_status"],
                    "is_early_close": session["is_early_close"],
                    "complete_universe_coverage": 1.0,
                })
                audit.append({
                    "target_market": target,
                    "feature_family": "LeveragedETF",
                    "decision_timestamp_utc": decision_ts.isoformat(),
                    "bar_timestamp_convention": timestamp_convention,
                    "decision_price_method": "completed_bar_close",
                    "decision_bar_timestamp_et": "15:30",
                    "close_price_method": "completed_regular_close_bar_close",
                    "close_bar_timestamp_et": "16:00",
                    "actual_1530_bar_timestamp_utc": bar_1530_comp.get("selected_source_as_of_timestamp_utc", ""),
                    "actual_1600_bar_timestamp_utc": "",
                    "prior_regular_close_timestamp_utc": prior_close_comp.get("selected_source_as_of_timestamp_utc", ""),
                    "selection_bundle_id": bundle.get("selection_bundle_id", ""),
                    "aum_as_of_timestamp_utc": ";".join(str(c.get("selected_source_as_of_timestamp_utc", "")) for c in aum_components),
                    "aum_effective_available_at_utc": ";".join(str(c.get("selected_source_effective_available_at_utc", "")) for c in aum_components),
                    "universe_completeness": "complete",
                    "calendar_session_status": session["calendar_coverage_status"],
                    "is_early_close": session["is_early_close"],
                    "availability_status": "available",
                    "availability_failure_reason": "",
                    "leveraged_etf_primary_input_integrity_status": "eligible_primary",
                    "leveraged_etf_primary_input_gate": "eligible_primary",
                    "complete_universe_coverage": 1.0,
                    "universe_fund_count": len(fund_rows),
                    "volume_reference_window": volume_comp.get("rth_volume_reference_window_configured", ""),
                    "volume_reference_last_date": volume_ref_last,
                    "volume_reference_row_count": volume_ref_count,
                    "rth_volume_reference_window_configured": volume_comp.get("rth_volume_reference_window_configured", ""),
                    "rth_volume_reference_min_valid_sessions": volume_comp.get("rth_volume_reference_min_valid_sessions", ""),
                    "rth_volume_reference_valid_session_count": volume_comp.get("rth_volume_reference_valid_session_count", ""),
                    "rth_volume_reference_session_dates": volume_comp.get("rth_volume_reference_session_dates", ""),
                    "rth_volume_reference_excluded_premarket_rows": volume_comp.get("rth_volume_reference_excluded_premarket_rows", ""),
                    "rth_volume_reference_excluded_postmarket_rows": volume_comp.get("rth_volume_reference_excluded_postmarket_rows", ""),
                    "rth_volume_reference_excluded_early_close_dates": volume_comp.get("rth_volume_reference_excluded_early_close_dates", ""),
                    "rth_volume_reference_status": volume_comp.get("rth_volume_reference_status", ""),
                })
    panel = pd.DataFrame(rows)
    panel.attrs["component_manifest"] = pd.DataFrame(component_manifest, columns=LEVERAGED_ETF_COMPONENT_MANIFEST_COLUMNS)
    return panel, pd.DataFrame(audit)


def build_leveraged_etf_input_candidate_audits(
    root: Path,
    cfg: dict[str, Any],
    intraday_decision_universe: pd.DataFrame | None = None,
    panel_component_manifest: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if intraday_decision_universe is None:
        raise ValueError("intraday_decision_universe is required; raw-bars fallback is disabled")
    universe = leveraged_universe(root)
    aum = load_leveraged_aum(root)
    nyse_calendar = load_nyse_calendar(root)
    decision_bar = parse_et_time(cfg.get("primary_decision_bar_et", "15:30"), time(15, 30))
    close_bar_time = parse_et_time(cfg.get("primary_close_bar_et", "16:00"), time(16, 0))
    rows: list[dict[str, Any]] = []
    universe_rows: list[dict[str, Any]] = []
    parity_rows: list[dict[str, Any]] = []
    timestamp_convention = str(cfg.get("bar_timestamp_convention", "bar_end"))
    provider_rules = expiry_intraday_rules(root)
    provider_configured = (root / EXPIRY_INTRADAY_RULES_PATH).exists()
    provider_verified = bool(provider_configured and provider_rules.get("provider_bar_semantics_verified", False))
    min_cfg = cfg.get("minimum_samples", {})
    default_volume_min = 20 if (root / RULES_PATH).exists() else 0
    volume_reference_min_sessions = int(cfg.get("leveraged_etf_volume_reference_min_sessions", min_cfg.get("leveraged_etf_volume_reference_min_sessions", default_volume_min)))
    for _, funds in universe.items():
        if not isinstance(funds, list):
            continue
        for target in sorted({str(f["target"]) for f in funds}):
            bars = load_intraday_bars(root, target)
            universe_target = intraday_decision_universe[
                intraday_decision_universe.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)
            ].copy() if intraday_decision_universe is not None and not intraday_decision_universe.empty else pd.DataFrame()
            if universe_target.empty:
                continue
            if not bars.empty:
                bars["date_et"] = bars["timestamp_utc"].dt.tz_convert(ET).dt.date
            if not universe_target.empty:
                decision_records = []
                for _, urow in universe_target.iterrows():
                    decision_ts = parse_ts(urow.get("decision_timestamp_utc", ""))
                    if decision_ts is None:
                        continue
                    day = decision_ts.tz_convert(ET).date()
                    group = bars[bars.get("date_et", pd.Series(dtype=object)).eq(day)].copy() if not bars.empty else pd.DataFrame()
                    decision_records.append((day, group, decision_ts))
            else:
                decision_records = [
                    (day, group.copy(), pd.Timestamp.combine(pd.Timestamp(day).date(), decision_bar).tz_localize(ET).tz_convert(UTC))
                    for day, group in bars.groupby("date_et")
                ]
            for day, group, decision_ts in decision_records:
                session = get_nyse_session(day, nyse_calendar)
                if not session.get("is_regular_session") or session.get("is_early_close"):
                    continue
                prior_close_ts = previous_regular_session_close_utc(day, nyse_calendar)
                prior_session = previous_regular_session(day, nyse_calendar)
                et_times = group["timestamp_utc"].dt.tz_convert(ET) if not group.empty and "timestamp_utc" in group.columns else pd.Series(dtype="datetime64[ns, UTC]")
                bar_1530 = exact_bar(group, et_times, decision_bar) if not group.empty else None
                prior_close = safe_float(group.iloc[0].get("prior_regular_session_close", np.nan)) if not group.empty else np.nan
                rows.append({
                    "input_component": "decision_bar_1530",
                    "target_market": target,
                    "decision_timestamp_utc": decision_ts.isoformat(),
                    "required_bar_timestamp_et": "15:30",
                    "actual_bar_timestamp_utc": bar_1530.get("timestamp_utc") if bar_1530 is not None else "",
                    "bar_timestamp_convention": timestamp_convention,
                    "provider_bar_semantics_verified": provider_verified,
                    "source_path_or_provider": str(intraday_bars_path(root, target) or ""),
                    "selection_policy_version": "exact_bar_timestamp_v1",
                    "primary_eligible": bool(bar_1530 is not None and timestamp_convention == "bar_end" and provider_verified),
                    "analysis_mode": "primary" if bar_1530 is not None and timestamp_convention == "bar_end" and provider_verified else "unavailable",
                    "candidate_eligibility_status": "eligible" if bar_1530 is not None and timestamp_convention == "bar_end" and provider_verified else "unavailable",
                    "selected_for_model": bar_1530 is not None and timestamp_convention == "bar_end" and provider_verified,
                    "availability_failure_reason": "" if bar_1530 is not None and provider_verified else ("provider_bar_semantics_unverified" if not provider_verified else "exact_1530_bar_missing"),
                })
                rows.append({
                    "input_component": "prior_regular_close",
                    "target_market": target,
                    "decision_timestamp_utc": decision_ts.isoformat(),
                    "prior_regular_close_session_date": prior_session.get("session_date", "") if prior_session else "",
                    "prior_regular_close_timestamp_utc": prior_close_ts.isoformat() if prior_close_ts is not None else "",
                    "prior_regular_close_price": prior_close,
                    "selection_policy_version": "prior_regular_close_v1",
                    "primary_eligible": bool(prior_close_ts is not None and pd.notna(prior_close)),
                    "analysis_mode": "primary" if prior_close_ts is not None and pd.notna(prior_close) else "unavailable",
                    "candidate_eligibility_status": "eligible" if prior_close_ts is not None and pd.notna(prior_close) else "unavailable",
                    "selected_for_model": prior_close_ts is not None and pd.notna(prior_close),
                    "availability_failure_reason": "" if prior_close_ts is not None and pd.notna(prior_close) else "prior_regular_close_missing",
                })
                volume_ref = strict_rth_volume_reference(bars, day, decision_bar, nyse_calendar, window=20, min_valid_sessions=volume_reference_min_sessions)
                volume_ref_count = int(volume_ref["rth_volume_reference_valid_session_count"])
                volume_ref_last = str(volume_ref["rth_volume_reference_session_dates"]).split(";")[-1] if str(volume_ref["rth_volume_reference_session_dates"]) else ""
                rows.append({
                    "input_component": "same_time_volume_reference",
                    "target_market": target,
                    "decision_timestamp_utc": decision_ts.isoformat(),
                    "source_path_or_provider": str(intraday_bars_path(root, target) or ""),
                    "selection_policy_version": "same_time_volume_reference_v1",
                    "primary_eligible": bool(volume_ref_count >= volume_reference_min_sessions),
                    "analysis_mode": "primary" if volume_ref_count >= volume_reference_min_sessions else "unavailable",
                    "candidate_eligibility_status": "eligible" if volume_ref_count >= volume_reference_min_sessions else "unavailable",
                    "selected_for_model": volume_ref_count >= volume_reference_min_sessions,
                    "availability_failure_reason": "" if volume_ref_count >= volume_reference_min_sessions else "volume_reference_insufficient",
                    "source_row_identifier": volume_ref.get("source_row_identifier", f"reference_count={volume_ref_count};last={volume_ref_last}"),
                    "source_hash_or_index": volume_ref.get("source_hash_or_index", f"reference_count={volume_ref_count};last={volume_ref_last}"),
                })
                fund_rows = [f for f in funds if str(f["target"]) == target]
                eligible_funds = 0
                for fund in fund_rows:
                    record = prior_available_aum_record(aum, str(fund["ticker"]), decision_ts, prior_close_ts or decision_ts)
                    eligible = bool(record.get("primary_eligible", False))
                    eligible_funds += int(eligible)
                    rows.append({
                        "input_component": "aum",
                        "fund_ticker": fund["ticker"],
                        "target_market": target,
                        "decision_timestamp_utc": decision_ts.isoformat(),
                        "aum_value": record.get("aum_value", np.nan),
                        "aum_value_type": record.get("aum_value_type", ""),
                        "aum_as_of_timestamp_utc": record.get("aum_as_of_timestamp_utc", ""),
                        "aum_effective_available_at_utc": record.get("aum_effective_available_at_utc", ""),
                        "source_path_or_provider": record.get("source_path_or_provider", ""),
                        "source_row_identifier": str(record.get("source_row_identifier", "")),
                        "source_hash_or_index": str(record.get("source_hash_or_index", "")),
                        "selection_policy_version": str(record.get("selection_policy_version", "")),
                        "primary_eligible": eligible,
                        "analysis_mode": str(record.get("analysis_mode", "")),
                        "candidate_eligibility_status": "eligible" if eligible else "unavailable",
                        "selected_for_model": eligible,
                        "availability_failure_reason": "" if eligible else str(record.get("availability_failure_reason", record.get("aum_source", ""))),
                    })
                complete = eligible_funds == len(fund_rows)
                universe_rows.append({
                    "target_market": target,
                    "decision_timestamp_utc": decision_ts.isoformat(),
                    "required_fund_count": len(fund_rows),
                    "eligible_fund_count": eligible_funds,
                    "complete_universe_coverage": eligible_funds / max(len(fund_rows), 1),
                    "availability_status": "available" if complete else "unavailable",
                    "availability_failure_reason": "" if complete else "primary_universe_incomplete",
                    "analysis_mode": "primary_complete_universe" if complete else "exploratory_partial_universe",
                })
                audit_bundle = build_leveraged_etf_input_selection_bundle(
                    target=target,
                    decision_timestamp_utc=decision_ts,
                    underlying=target,
                    funds=fund_rows,
                    bars=bars,
                    aum_history=aum,
                    provider_rules=provider_rules,
                    nyse_calendar=nyse_calendar,
                    cfg=cfg,
                    root=root,
                )
                audit_components = {(c.get("source_component_type"), c.get("fund_ticker", "")): c for c in audit_bundle["components"]}
                if panel_component_manifest is not None and not panel_component_manifest.empty:
                    actual_rows = panel_component_manifest[
                        panel_component_manifest.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)
                        & panel_component_manifest.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str).eq(decision_ts.isoformat())
                    ].to_dict("records")
                else:
                    actual_rows = []
                actual_components = {(c.get("source_component_type"), c.get("fund_ticker", "")): c for c in actual_rows}
                all_component_keys = sorted(set(audit_components) | set(actual_components))
                for key in all_component_keys:
                    acomp = audit_components.get(key, {})
                    comp = actual_components.get(key, {})
                    panel_ok = bool(comp.get("primary_eligible", False))
                    audit_ok = bool(acomp.get("primary_eligible", False))
                    fresh_status = str(acomp.get("selection_status", ""))
                    actual_present = bool(comp)
                    same = (
                        str(comp.get("selected_source_row_identifier", "")) == str(acomp.get("selected_source_row_identifier", ""))
                        and str(comp.get("selected_source_content_hash", "")) == str(acomp.get("selected_source_content_hash", ""))
                        and str(comp.get("selected_source_effective_available_at_utc", "")) == str(acomp.get("selected_source_effective_available_at_utc", ""))
                        and str(comp.get("selected_source_as_of_timestamp_utc", "")) == str(acomp.get("selected_source_as_of_timestamp_utc", ""))
                        and str(comp.get("selection_policy_revision", "")) == str(acomp.get("selection_policy_revision", ""))
                        and str(comp.get("selection_status", "")) == str(acomp.get("selection_status", ""))
                        and str(bool(comp.get("primary_eligible", False))).lower() == str(bool(acomp.get("primary_eligible", False))).lower()
                    )
                    if audit_ok and actual_present and panel_ok:
                        status = "matched" if same else "mismatch"
                    elif audit_ok and not actual_present:
                        status = "audit_missing"
                    elif comp.get("selection_status") == "selected_invalid" or fresh_status == "selected_invalid":
                        status = "selected_invalid"
                    else:
                        status = "unavailable_coverage"
                    component_type, fund_ticker = key
                    parity_rows.append({
                        "module": "LeveragedETF",
                        "feature_family": "LeveragedETF",
                        "model_scope": "LeveragedETF_pressure",
                        "target_market": target,
                        "decision_timestamp_utc": decision_ts.isoformat(),
                        "required_source_family": f"{component_type}:{fund_ticker}",
                        "audit_selected_source_row_identifier": acomp.get("selected_source_row_identifier", ""),
                        "panel_selected_source_row_identifier": comp.get("selected_source_row_identifier", ""),
                        "audit_selected_source_hash_or_index": acomp.get("selected_source_content_hash", ""),
                        "panel_selected_source_hash_or_index": comp.get("selected_source_content_hash", ""),
                        "audit_selected_effective_available_at_utc": acomp.get("selected_source_effective_available_at_utc", ""),
                        "panel_selected_effective_available_at_utc": comp.get("selected_source_effective_available_at_utc", ""),
                        "selection_parity_status": status,
                        "selection_parity_failure_reason": "" if status == "matched" else str(comp.get("invalid_reason", "") or acomp.get("invalid_reason", "") or ("expected_actual_panel_component_missing" if status == "audit_missing" else "selected_source_record_mismatch")),
                        "scope_gate_recommendation": "evaluate" if status == "matched" else ("insufficient_data" if status == "unavailable_coverage" else "data_quality_blocked"),
                    })
    candidate = pd.DataFrame(rows, columns=LEVERAGED_ETF_INPUT_CANDIDATE_COLUMNS)
    summary = candidate.groupby(["target_market", "decision_timestamp_utc", "input_component"], dropna=False).agg(
        raw_candidate_row_count=("input_component", "size"),
        eligible_row_count=("candidate_eligibility_status", lambda s: int(s.astype(str).eq("eligible").sum())),
        selected_row_count=("selected_for_model", lambda s: int(pd.Series(s).astype(bool).sum())),
    ).reset_index() if not candidate.empty else pd.DataFrame()
    return candidate, summary, pd.DataFrame(universe_rows), pd.DataFrame(parity_rows, columns=SOURCE_SELECTION_PARITY_COLUMNS)


def leveraged_integrity_status(reasons: list[str], all_primary: bool) -> tuple[str, str]:
    data_quality_reasons = [
        "provider_bar_semantics_unverified",
        "provider_bar_semantics_incomplete",
        "selected_aum_after_prior_regular_close",
        "date_only_aum_not_primary",
        "imputed_surrogate_exploratory_not_primary",
    ]
    reason_text = ";".join([r for r in reasons if r])
    if any(token in reason_text for token in data_quality_reasons):
        return "data_quality_blocked", reason_text
    if not all_primary:
        return "insufficient_data", reason_text
    return "eligible_primary", ""


def build_leveraged_etf_primary_input_integrity_outputs(
    input_audit: pd.DataFrame,
    universe_audit: pd.DataFrame,
    parity_audit: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    integrity_columns = [
        "target_market",
        "decision_timestamp_utc",
        "input_component",
        "component_status",
        "component_failure_reason",
        "primary_eligible",
        "selected_for_panel",
        "selected_for_model",
        "selection_parity_status",
        "leveraged_etf_primary_input_integrity_status",
        "leveraged_etf_primary_input_gate",
    ]
    summary_columns = [
        "target_market",
        "decision_timestamp_utc",
        "component_count",
        "eligible_component_count",
        "leveraged_etf_primary_input_integrity_status",
        "leveraged_etf_primary_input_gate",
    ]
    if input_audit.empty:
        return (
            pd.DataFrame(columns=integrity_columns),
            pd.DataFrame(columns=summary_columns),
            pd.DataFrame(columns=LEVERAGED_ETF_INPUT_CANDIDATE_COLUMNS + ["selection_parity_status", "scope_gate_recommendation"]),
            pd.DataFrame(columns=LEVERAGED_ETF_INPUT_CANDIDATE_COLUMNS + ["leveraged_etf_primary_input_gate"]),
        )
    rows: list[dict[str, Any]] = []
    for keys, group in input_audit.groupby(["target_market", "decision_timestamp_utc"], dropna=False):
        target, decision_ts = keys
        reasons = group.get("availability_failure_reason", pd.Series(dtype=str)).astype(str).replace("nan", "").tolist()
        all_primary = bool(group.get("primary_eligible", pd.Series([False] * len(group))).astype(bool).all())
        universe_group = universe_audit[
            universe_audit.get("target_market", pd.Series(dtype=str)).astype(str).eq(str(target))
            & universe_audit.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str).eq(str(decision_ts))
        ] if universe_audit is not None and not universe_audit.empty else pd.DataFrame()
        if not universe_group.empty and not universe_group.get("availability_status", pd.Series(dtype=str)).astype(str).eq("available").all():
            all_primary = False
            reasons.extend(universe_group.get("availability_failure_reason", pd.Series(dtype=str)).astype(str).replace("nan", "").tolist())
        status, failure = leveraged_integrity_status(reasons, all_primary)
        parity_group = parity_audit[
            parity_audit.get("target_market", pd.Series(dtype=str)).astype(str).eq(str(target))
            & parity_audit.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str).eq(str(decision_ts))
        ] if not parity_audit.empty else pd.DataFrame()
        parity_values = parity_group.get("selection_parity_status", pd.Series(dtype=str)).astype(str).tolist() if not parity_group.empty else []
        parity_status = _aggregate_parity_status(parity_values)
        if parity_status in {"mismatch", "audit_missing", "selected_invalid"}:
            status, failure = "data_quality_blocked", "selector_parity_" + parity_status
        elif parity_status == "unavailable_coverage" and status == "eligible_primary":
            status, failure = "insufficient_data", "selector_parity_unavailable"
        for _, row in group.iterrows():
            component_primary = bool(row.get("primary_eligible", False))
            rows.append({
                "target_market": target,
                "decision_timestamp_utc": decision_ts,
                "input_component": row.get("input_component", ""),
                "component_status": "eligible" if component_primary else ("data_quality_blocked" if status == "data_quality_blocked" else "insufficient_data"),
                "component_failure_reason": row.get("availability_failure_reason", ""),
                "primary_eligible": component_primary,
                "selected_for_panel": component_primary and status == "eligible_primary",
                "selected_for_model": bool(row.get("selected_for_model", False)) and status == "eligible_primary",
                "selection_parity_status": parity_status,
                "leveraged_etf_primary_input_integrity_status": status,
                "leveraged_etf_primary_input_gate": status,
            })
    integrity = pd.DataFrame(rows, columns=integrity_columns)
    summary = integrity.groupby(["target_market", "decision_timestamp_utc"], dropna=False).agg(
        component_count=("input_component", "size"),
        eligible_component_count=("primary_eligible", lambda s: int(pd.Series(s).astype(bool).sum())),
        leveraged_etf_primary_input_integrity_status=("leveraged_etf_primary_input_integrity_status", lambda s: "data_quality_blocked" if pd.Series(s).astype(str).eq("data_quality_blocked").any() else ("insufficient_data" if pd.Series(s).astype(str).eq("insufficient_data").any() else "eligible_primary")),
        leveraged_etf_primary_input_gate=("leveraged_etf_primary_input_gate", lambda s: "data_quality_blocked" if pd.Series(s).astype(str).eq("data_quality_blocked").any() else ("insufficient_data" if pd.Series(s).astype(str).eq("insufficient_data").any() else "eligible_primary")),
    ).reset_index() if not integrity.empty else pd.DataFrame()
    aum_parity = parity_audit[parity_audit.get("required_source_family", pd.Series(dtype=str)).astype(str).str.startswith("aum:")].copy() if not parity_audit.empty else pd.DataFrame(columns=SOURCE_SELECTION_PARITY_COLUMNS)
    bar_semantics = parity_audit[parity_audit.get("required_source_family", pd.Series(dtype=str)).astype(str).isin(["bar_1530:", "provider_rule:"])].copy() if not parity_audit.empty else pd.DataFrame(columns=SOURCE_SELECTION_PARITY_COLUMNS)
    return integrity, summary, aum_parity, bar_semantics


def build_selector_result_audit(source_candidate_audit: pd.DataFrame, leveraged_input_audit: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not source_candidate_audit.empty:
        for _, row in source_candidate_audit.iterrows():
            eligible = str(row.get("candidate_eligibility_status", "")) == "eligible"
            selected = bool(row.get("selected_for_panel", False))
            rows.append({
                "selection_scope": "source_feature",
                "module": row.get("module", ""),
                "feature_family": row.get("feature_family", ""),
                "model_scope": row.get("module", ""),
                "target_market": row.get("target_market", ""),
                "decision_timestamp_utc": row.get("decision_timestamp_utc", ""),
                "source_path_or_provider": row.get("source_path_or_provider", ""),
                "source_row_identifier": row.get("source_row_identifier", ""),
                "source_hash_or_index": row.get("source_hash_or_index", row.get("source_row_identifier", "")),
                "selection_policy_version": row.get("selection_policy_version", "latest_clean_eligible_candidate_v1"),
                "selection_status": "selected_clean" if selected and eligible else ("selected_invalid" if selected else "unavailable_no_candidate"),
                "primary_eligible": eligible,
                "analysis_mode": "primary" if eligible else "unavailable",
                "availability_state": "candidate_available_clean" if eligible else "coverage_gap_or_no_candidate",
                "availability_status": "available" if eligible else "unavailable",
                "availability_failure_reason": row.get("candidate_exclusion_reason", ""),
                "quality_status": "passed" if eligible else "not_run",
                "quality_failure_reason": "",
                "selected_for_panel": selected,
                "selected_for_model": selected,
            })
    if not leveraged_input_audit.empty:
        for _, row in leveraged_input_audit.iterrows():
            eligible = bool(row.get("primary_eligible", False))
            rows.append({
                "selection_scope": "leveraged_etf_primary_input",
                "module": "LeveragedETF",
                "feature_family": "LeveragedETF",
                "model_scope": "LeveragedETF_pressure",
                "target_market": row.get("target_market", ""),
                "decision_timestamp_utc": row.get("decision_timestamp_utc", ""),
                "source_path_or_provider": row.get("source_path_or_provider", ""),
                "source_row_identifier": row.get("source_row_identifier", ""),
                "source_hash_or_index": row.get("source_hash_or_index", ""),
                "selection_policy_version": row.get("selection_policy_version", ""),
                "selection_status": "selected_clean" if eligible else "unavailable_missing_required_input",
                "primary_eligible": eligible,
                "analysis_mode": row.get("analysis_mode", ""),
                "availability_state": "candidate_available_clean" if eligible else "coverage_gap_or_no_candidate",
                "availability_status": "available" if eligible else "unavailable",
                "availability_failure_reason": row.get("availability_failure_reason", ""),
                "quality_status": "passed" if eligible else "not_run",
                "quality_failure_reason": "",
                "selected_for_panel": eligible,
                "selected_for_model": bool(row.get("selected_for_model", False)),
            })
    return pd.DataFrame(rows, columns=SELECTOR_RESULT_COLUMNS)


def load_dealer_gamma_history(root: Path) -> pd.DataFrame:
    candidates = [
        root / "dealer_gamma_proxy_history.csv",
        root / "market_bomb_history" / "dealer_gamma_proxy_history.csv",
        root / "market_bomb_history" / "dealer_gamma_observed_history.csv",
    ]
    for path in candidates:
        if path.exists():
            try:
                df = pd.read_csv(path)
                df["source_path_or_provider"] = str(path.relative_to(root)).replace("\\", "/")
                return df
            except Exception:
                pass
    return pd.DataFrame()


DEALER_GAMMA_SELECTION_COLUMNS = [
    "target_market",
    "decision_timestamp_utc",
    "selector_context",
    "selection_status",
    "availability_state",
    "primary_eligible",
    "invalid_reason",
    "selected_source_row_identifier",
    "selected_source_content_hash",
    "selected_source_as_of_timestamp_utc",
    "selected_source_effective_available_at_utc",
    "selected_source_quality",
    "selected_data_type",
    "selected_dealer_position_observed",
    "selected_raw_chain_present",
    "feature_age_hours",
    "dealer_gamma_source_contract_revision",
    "selection_policy_revision",
]


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _dealer_gamma_columns(raw: pd.DataFrame) -> dict[str, str | None]:
    cols = {str(c).lower(): c for c in raw.columns}
    return {
        "target": cols.get("ticker") or cols.get("asset") or cols.get("target_market"),
        "row_identifier": cols.get("source_row_identifier") or cols.get("row_id") or cols.get("source_id"),
        "effective": cols.get("effective_available_at_utc") or cols.get("snapshot_timestamp_utc") or cols.get("feature_as_of_timestamp_utc"),
        "asof": cols.get("feature_as_of_timestamp_utc") or cols.get("option_chain_as_of_timestamp_utc") or cols.get("snapshot_timestamp_utc") or cols.get("effective_available_at_utc"),
        "quality": cols.get("row_economic_quality") or cols.get("raw_chain_quality") or cols.get("economic_quality"),
        "raw_chain": cols.get("raw_option_chain_snapshot") or cols.get("observed_raw_chain") or cols.get("raw_chain_present"),
        "data_type": cols.get("data_type"),
        "dealer_position_observed": cols.get("dealer_position_observed"),
    }


def stable_source_row_identifier(row: pd.Series | dict[str, Any], source_path: str = "") -> str:
    data = row.to_dict() if isinstance(row, pd.Series) else dict(row)
    for key in ["source_row_identifier", "row_id", "source_id"]:
        if str(data.get(key, "")).strip():
            return str(data[key])
    return hashlib.sha256(f"{source_path}|{row_content_hash(data)}".encode("utf-8")).hexdigest()


def select_latest_clean_dealer_gamma(
    *,
    target_market: str,
    decision_timestamp_utc: Any,
    source_rows: pd.DataFrame,
    selector_context: str,
    config: dict[str, Any],
    source_contract_revision: str = DEALER_GAMMA_SOURCE_CONTRACT_REVISION,
) -> dict[str, Any]:
    target = str(target_market).upper()
    decision_ts = parse_ts(decision_timestamp_utc)
    base = {
        "target_market": target,
        "decision_timestamp_utc": "" if decision_timestamp_utc is None else str(decision_timestamp_utc),
        "selector_context": selector_context,
        "selection_status": "unavailable_coverage",
        "availability_state": "coverage_missing",
        "primary_eligible": False,
        "invalid_reason": "",
        "selected_source_row_identifier": "",
        "selected_source_content_hash": "",
        "selected_source_as_of_timestamp_utc": "",
        "selected_source_effective_available_at_utc": "",
        "selected_source_quality": "",
        "selected_data_type": "",
        "selected_dealer_position_observed": False,
        "selected_raw_chain_present": False,
        "feature_age_hours": np.nan,
        "dealer_gamma_source_contract_revision": source_contract_revision,
        "selection_policy_revision": DEALER_GAMMA_SELECTION_POLICY_REVISION,
        "row": None,
    }
    if decision_ts is None:
        return base | {"selection_status": "selected_invalid", "availability_state": "missing_required_field", "invalid_reason": "decision_timestamp_invalid"}
    if source_rows.empty:
        return base | {"invalid_reason": "dealer_gamma_history_missing"}
    col = _dealer_gamma_columns(source_rows)
    missing = [name for name in ["target", "effective", "asof", "quality", "raw_chain", "data_type", "dealer_position_observed"] if not col.get(name)]
    if missing:
        return base | {
            "selection_status": "selected_invalid",
            "availability_state": "missing_required_field",
            "invalid_reason": "dealer_gamma_required_columns_missing:" + ",".join(missing),
        }

    work = source_rows.copy()
    source_path_col = {str(c).lower(): c for c in source_rows.columns}.get("source_path_or_provider")
    if col.get("row_identifier"):
        work["_selector_row_identifier"] = work[col["row_identifier"]].astype(str)
    else:
        work["_selector_row_identifier"] = [
            stable_source_row_identifier(row, str(row.get(source_path_col, "")) if source_path_col else "")
            for _, row in work.iterrows()
        ]
    work["_target_market"] = work[col["target"]].astype(str).str.upper()
    work["_effective_ts"] = pd.to_datetime(work[col["effective"]], utc=True, errors="coerce")
    work["_asof_ts"] = pd.to_datetime(work[col["asof"]], utc=True, errors="coerce")
    work["_quality"] = work[col["quality"]].astype(str).str.lower()
    work["_raw_chain_present"] = work[col["raw_chain"]].map(_truthy)
    work["_data_type"] = work[col["data_type"]].astype(str)
    work["_data_type_ok"] = work["_data_type"].str.lower().isin(DEALER_GAMMA_ALLOWED_DATA_TYPES)
    work["_dealer_position_observed"] = work[col["dealer_position_observed"]].map(_truthy)
    net_gex_col = {str(c).lower(): c for c in source_rows.columns}.get("net_gex_proxy")
    flip_col = {str(c).lower(): c for c in source_rows.columns}.get("gamma_flip_state")
    distance_col = {str(c).lower(): c for c in source_rows.columns}.get("gamma_flip_distance_pct")
    missing_payload = [name for name, source_col in [("net_gex_proxy", net_gex_col), ("gamma_flip_state", flip_col)] if source_col is None]
    if missing_payload:
        return base | {
            "selection_status": "selected_invalid",
            "availability_state": "missing_required_field",
            "invalid_reason": "dealer_gamma_required_payload_missing:" + ",".join(missing_payload),
        }
    work["_net_gex_numeric"] = pd.to_numeric(work[net_gex_col], errors="coerce")
    work["_net_gex_ok"] = work["_net_gex_numeric"].notna()
    work["_gamma_flip_state"] = work[flip_col].astype(str)
    work["_gamma_flip_state_ok"] = work["_gamma_flip_state"].isin(["local_flip_found", "no_local_flip"])
    if distance_col:
        work["_gamma_flip_distance_numeric"] = pd.to_numeric(work[distance_col], errors="coerce")
    else:
        work["_gamma_flip_distance_numeric"] = np.nan
    work["_gamma_flip_distance_ok"] = (
        work["_gamma_flip_state"].eq("no_local_flip")
        | (work["_gamma_flip_state"].eq("local_flip_found") & work["_gamma_flip_distance_numeric"].notna())
    )
    work = work[work["_target_market"].eq(target)].copy()
    if work.empty:
        return base | {"availability_state": "coverage_missing", "invalid_reason": "no_target_history"}

    work["_feature_age_hours"] = (decision_ts - work["_effective_ts"]).dt.total_seconds() / 3600
    at_or_before = work[(work["_effective_ts"] <= decision_ts) & (work["_asof_ts"] <= decision_ts)].copy()
    max_age = safe_float(config.get("max_feature_age_hours", 96), 96)
    clean = at_or_before[
        at_or_before["_effective_ts"].notna()
        & at_or_before["_asof_ts"].notna()
        & at_or_before["_raw_chain_present"]
        & at_or_before["_quality"].isin(["medium", "high"])
        & at_or_before["_data_type_ok"]
        & ~at_or_before["_dealer_position_observed"]
        & at_or_before["_net_gex_ok"]
        & at_or_before["_gamma_flip_state_ok"]
        & at_or_before["_gamma_flip_distance_ok"]
        & (at_or_before["_feature_age_hours"] <= max_age)
    ].copy()

    def pack(row: pd.Series, status: str, state: str, eligible: bool, reason: str) -> dict[str, Any]:
        asof_ts = row.get("_asof_ts")
        eff_ts = row.get("_effective_ts")
        return base | {
            "selection_status": status,
            "availability_state": state,
            "primary_eligible": eligible,
            "invalid_reason": reason,
            "selected_source_row_identifier": str(row.get("_selector_row_identifier", row.name)),
            "selected_source_content_hash": row_content_hash(row.drop(labels=[c for c in row.index if str(c).startswith("_")], errors="ignore")),
            "selected_source_as_of_timestamp_utc": asof_ts.isoformat() if isinstance(asof_ts, pd.Timestamp) and pd.notna(asof_ts) else str(row.get(col["asof"], "")),
            "selected_source_effective_available_at_utc": eff_ts.isoformat() if isinstance(eff_ts, pd.Timestamp) and pd.notna(eff_ts) else str(row.get(col["effective"], "")),
            "selected_source_quality": str(row.get("_quality", "")),
            "selected_data_type": str(row.get("_data_type", "")),
            "selected_dealer_position_observed": bool(row.get("_dealer_position_observed", False)),
            "selected_raw_chain_present": bool(row.get("_raw_chain_present", False)),
            "feature_age_hours": safe_float(row.get("_feature_age_hours")),
            "row": row,
        }

    if not clean.empty:
        selected = clean.sort_values(["_effective_ts", "_asof_ts", "_selector_row_identifier"]).iloc[-1]
        return pack(selected, "selected", "valid", True, "")

    invalid_contract = at_or_before[
        at_or_before["_effective_ts"].notna()
        & at_or_before["_asof_ts"].notna()
        & (
            ~at_or_before["_raw_chain_present"]
            | ~at_or_before["_quality"].isin(["medium", "high"])
            | ~at_or_before["_data_type_ok"]
            | at_or_before["_dealer_position_observed"]
            | ~at_or_before["_net_gex_ok"]
            | ~at_or_before["_gamma_flip_state_ok"]
            | ~at_or_before["_gamma_flip_distance_ok"]
        )
    ].copy()
    if not invalid_contract.empty:
        bad = invalid_contract.sort_values(["_effective_ts", "_asof_ts", "_selector_row_identifier"]).iloc[-1]
        if bool(bad.get("_dealer_position_observed", False)):
            reason = "dealer_position_observed_true"
        elif not bool(bad.get("_data_type_ok", False)):
            reason = "dealer_gamma_data_type_invalid"
        elif not bool(bad.get("_raw_chain_present", False)):
            reason = "raw_chain_evidence_missing"
        elif not bool(bad.get("_net_gex_ok", False)):
            reason = "net_gex_proxy_invalid"
        elif not bool(bad.get("_gamma_flip_state_ok", False)):
            reason = "gamma_flip_state_invalid"
        elif not bool(bad.get("_gamma_flip_distance_ok", False)):
            reason = "gamma_flip_distance_required_for_local_flip"
        else:
            reason = "dealer_gamma_quality_invalid"
        return pack(bad, "selected_invalid", "data_quality_blocked", False, reason)

    invalid_ts = work[work["_effective_ts"].isna() | work["_asof_ts"].isna()].copy()
    if not invalid_ts.empty and at_or_before.empty:
        bad = invalid_ts.iloc[-1]
        return pack(bad, "selected_invalid", "missing_required_field", False, "dealer_gamma_timestamp_invalid")

    prior_with_timestamps = at_or_before[at_or_before["_effective_ts"].notna() & at_or_before["_asof_ts"].notna()].copy()
    if not prior_with_timestamps.empty:
        stale = prior_with_timestamps.sort_values(["_effective_ts", "_asof_ts", "_selector_row_identifier"]).iloc[-1]
        return pack(stale, "unavailable_coverage", "invalid_age", False, "feature_age_exceeds_maximum")
    future = work[(work["_effective_ts"] > decision_ts) | (work["_asof_ts"] > decision_ts)].copy()
    reason = "coverage_not_started" if not future.empty else "no_historical_gamma_before_decision"
    return base | {"availability_state": reason, "invalid_reason": reason}


def _hydrate_dealer_gamma_source_row(raw: pd.DataFrame, selection_row: pd.Series) -> tuple[pd.Series | None, str, str]:
    if raw.empty:
        return None, "missing", "dealer_gamma_history_missing"
    selected_id = str(selection_row.get("selected_source_row_identifier", ""))
    selected_hash = str(selection_row.get("selected_source_content_hash", ""))
    cols = {str(c).lower(): c for c in raw.columns}
    row_identifier_col = cols.get("source_row_identifier")
    source_path_col = cols.get("source_path_or_provider")
    for _, row in raw.iterrows():
        source_id = str(row.get(row_identifier_col, "")) if row_identifier_col else stable_source_row_identifier(row, str(row.get(source_path_col, "")) if source_path_col else "")
        source_hash = row_content_hash(row)
        if source_id == selected_id and source_hash == selected_hash:
            return row, "hydrated", ""
    return None, "missing", "selected_source_lineage_not_found"


def dealer_gamma_payload_hash_from_values(net_gex: Any, flip_state: Any, distance: Any, pinning: Any = np.nan) -> str:
    state = str(flip_state)
    dist = safe_float(distance, np.nan)
    if state == "no_local_flip":
        dist = np.nan
    return row_content_hash({
        "net_gex_proxy": safe_float(net_gex, np.nan),
        "gamma_flip_state": state,
        "gamma_flip_distance_pct": dist,
        "pinning_proxy": safe_float(pinning, np.nan),
    })


def dealer_gamma_payload_hash_from_row(row: pd.Series | dict[str, Any] | None) -> str:
    if row is None:
        return ""
    data = row.to_dict() if isinstance(row, pd.Series) else dict(row)
    cols = {str(c).lower(): c for c in data.keys()}
    return dealer_gamma_payload_hash_from_values(
        data.get(cols.get("net_gex_proxy", "net_gex_proxy"), np.nan),
        data.get(cols.get("gamma_flip_state", "gamma_flip_state"), ""),
        data.get(cols.get("gamma_flip_distance_pct", "gamma_flip_distance_pct"), np.nan),
        data.get(cols.get("pinning_proxy", "pinning_proxy"), np.nan),
    )


def build_dealer_gamma_panel_with_actual_lineage(root: Path, daily_outcomes: pd.DataFrame, cfg: dict[str, Any] | None = None, eod_selection_audit: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cfg = cfg or rules(root)
    raw = load_dealer_gamma_history(root)
    rows: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    lineage_rows: list[dict[str, Any]] = []
    hydration_rows: list[dict[str, Any]] = []
    if raw.empty:
        selection_audit = eod_selection_audit if eod_selection_audit is not None else build_dealer_gamma_eod_selection_audit(root, daily_outcomes, cfg)
        for _, selection in selection_audit.iterrows():
            lineage_rows.append(_dealer_gamma_lineage_row(selection, None, False, "missing", "dealer_gamma_history_missing"))
        return (
            pd.DataFrame(),
            pd.DataFrame([{"feature_family": "DealerGamma", "availability_status": "unavailable", "availability_failure_reason": "dealer_gamma_history_missing"}]),
            pd.DataFrame(lineage_rows, columns=DEALER_GAMMA_EOD_ACTUAL_FEATURE_LINEAGE_COLUMNS),
            pd.DataFrame(hydration_rows, columns=DEALER_GAMMA_EOD_FEATURE_HYDRATION_COLUMNS),
        )
    cols = {str(c).lower(): c for c in raw.columns}
    selection_audit = eod_selection_audit if eod_selection_audit is not None else build_dealer_gamma_eod_selection_audit(root, daily_outcomes, cfg)
    outcomes_by_key = {
        (str(row.get("target_market", "")).upper(), str(row.get("decision_timestamp_utc", ""))): row
        for _, row in daily_outcomes.iterrows()
    }
    for _, selection in selection_audit.iterrows():
        selected_expected = str(selection.get("selection_status", "")) == "selected" and bool(selection.get("primary_eligible", False))
        if not selected_expected:
            lineage_rows.append(_dealer_gamma_lineage_row(selection, None, False, "not_applicable", str(selection.get("invalid_reason", "")) or str(selection.get("availability_state", ""))))
            continue
        key = (str(selection.get("target_market", "")).upper(), str(selection.get("decision_timestamp_utc", "")))
        outcome = outcomes_by_key.get(key, selection)
        decision_ts = parse_ts(outcome["decision_timestamp_utc"])
        if decision_ts is None:
            lineage_rows.append(_dealer_gamma_lineage_row(selection, None, False, "missing", "decision_timestamp_invalid"))
            continue
        target = str(outcome["target_market"]).upper()
        feat, hydration_status, hydration_reason = _hydrate_dealer_gamma_source_row(raw, selection)
        hydration_rows.append({
            "target_market": target,
            "decision_timestamp_utc": selection.get("decision_timestamp_utc", ""),
            "selected_source_row_identifier": selection.get("selected_source_row_identifier", ""),
            "selected_source_content_hash": selection.get("selected_source_content_hash", ""),
            "hydration_status": hydration_status,
            "hydration_failure_reason": hydration_reason,
        })
        if feat is None:
            lineage_rows.append(_dealer_gamma_lineage_row(selection, None, False, hydration_status, hydration_reason))
            continue
        row = outcome.to_dict()
        flip_state = str(feat.get(cols.get("gamma_flip_state", "gamma_flip_state"), "unavailable"))
        distance = safe_float(feat.get(cols.get("gamma_flip_distance_pct", "gamma_flip_distance_pct"), np.nan))
        net_gex = safe_float(feat.get(cols.get("net_gex_proxy", "net_gex_proxy"), np.nan))
        sign_convention = str(load_json(root, DEALER_RULES_PATH, {}).get("sign_convention", ""))
        sign_verified = sign_convention == "positive_net_gex_proxy_means_long_gamma_proxy_not_dealer_inventory"
        negative_gamma = int(pd.notna(net_gex) and sign_verified and net_gex < 0)
        if flip_state == "no_local_flip":
            distance = np.nan
        row.update({
            "analysis_id": f"dealer_gamma_{target}_{decision_ts.date()}",
            "feature_family": "DealerGamma",
            "feature_name": "observed_raw_chain_proxy_set",
            "feature_value": net_gex,
            "feature_unit": "proxy",
            "feature_as_of_timestamp_utc": selection.get("selected_source_as_of_timestamp_utc", ""),
            "effective_available_at_utc": selection.get("selected_source_effective_available_at_utc", ""),
            "feature_age_hours": safe_float(selection.get("feature_age_hours")),
            "availability_basis": "effective_available_at_utc",
            "availability_confidence": "medium",
            "source_path_or_provider": feat.get("source_path_or_provider", ""),
            "source_hash_or_request_id": selection.get("selected_source_content_hash", ""),
            "dealer_feature_sample_type": "observed_raw_chain_primary",
            "gamma_flip_state": flip_state if flip_state in {"local_flip_found", "no_local_flip", "unavailable"} else "unavailable",
            "gamma_flip_distance_pct": distance,
            "net_gex_proxy": net_gex,
            "negative_gamma_proxy_indicator": negative_gamma if sign_verified else np.nan,
            "dealer_gamma_sign_policy_revision": DEALER_GAMMA_SIGN_POLICY_REVISION if sign_verified else "unverified_sign_convention",
            "dealer_gamma_selection_status": selection.get("selection_status", ""),
            "dealer_gamma_availability_state": selection.get("availability_state", ""),
            "dealer_gamma_invalid_reason": selection.get("invalid_reason", ""),
            "dealer_gamma_source_contract_revision": selection.get("dealer_gamma_source_contract_revision", DEALER_GAMMA_SOURCE_CONTRACT_REVISION),
            "dealer_gamma_selection_policy_revision": selection.get("selection_policy_revision", DEALER_GAMMA_SELECTION_POLICY_REVISION),
            "dealer_gamma_effective_available_at_utc": selection.get("selected_source_effective_available_at_utc", ""),
            "pinning_proxy": safe_float(feat.get(cols.get("pinning_proxy", "pinning_proxy"), np.nan)),
            "local_flip_found_flag": int(flip_state == "local_flip_found"),
            "no_local_flip_flag": int(flip_state == "no_local_flip"),
            "sign_convention": "positive_net_gex_proxy_means_long_gamma_proxy_not_dealer_inventory",
            "is_proxy": True,
            "dealer_position_observed": selection.get("selected_dealer_position_observed", False),
            "data_type": selection.get("selected_data_type", "reconstructed_from_raw_chain"),
            "observed_flow": False,
            "raw_chain_quality": selection.get("selected_source_quality", "unknown"),
            "row_economic_quality": selection.get("selected_source_quality", "unknown"),
            "quality_grade": selection.get("selected_source_quality", "unknown"),
            "availability_status": "available",
            "availability_failure_reason": "",
            "analysis_mode": "reconstructed_proxy_primary",
            "selected_source_row_identifier": selection.get("selected_source_row_identifier", ""),
            "selected_source_effective_available_at_utc": selection.get("selected_source_effective_available_at_utc", ""),
            "selected_source_hash_or_index": selection.get("selected_source_content_hash", ""),
            "selected_source_content_hash": selection.get("selected_source_content_hash", ""),
            "selected_source_as_of_timestamp_utc": selection.get("selected_source_as_of_timestamp_utc", ""),
            "selected_raw_chain_present": selection.get("selected_raw_chain_present", False),
            "actual_feature_row_identifier": f"{target}|{decision_ts.isoformat()}|DealerGamma",
            "actual_feature_payload_hash": dealer_gamma_payload_hash_from_values(net_gex, flip_state, distance, safe_float(feat.get(cols.get("pinning_proxy", "pinning_proxy"), np.nan))),
            "actual_feature_hydration_status": hydration_status,
            "actual_feature_hydration_failure_reason": hydration_reason,
            "selection_policy_version": DEALER_GAMMA_SELECTION_POLICY_REVISION,
        })
        rows.append(row)
        lineage_rows.append(_dealer_gamma_lineage_row(selection, row, True, hydration_status, hydration_reason))
    audit.append(feature_audit_row(
        feature_family="DealerGamma",
        feature_name="observed_raw_chain_proxy_set",
        availability_status="available" if rows else "unavailable",
        availability_failure_reason="" if rows else "no_temporally_available_observed_rows",
        data_type="reconstructed_from_raw_chain",
        observed_flow=False,
        quality_grade="medium" if rows else "unavailable",
    ) | {"sample_count": len(rows)})
    return (
        pd.DataFrame(rows),
        pd.DataFrame(audit),
        pd.DataFrame(lineage_rows, columns=DEALER_GAMMA_EOD_ACTUAL_FEATURE_LINEAGE_COLUMNS),
        pd.DataFrame(hydration_rows, columns=DEALER_GAMMA_EOD_FEATURE_HYDRATION_COLUMNS),
    )


def _dealer_gamma_lineage_row(selection: pd.Series, actual: dict[str, Any] | None, present: bool, hydration_status: str, hydration_reason: str) -> dict[str, Any]:
    expected_status = str(selection.get("selection_status", ""))
    expected_primary = bool(selection.get("primary_eligible", False))
    if present and expected_status != "selected":
        lineage_status = "selected_invalid"
        lineage_reason = "actual_panel_row_present_without_selected_expected_source"
    elif expected_status == "selected" and expected_primary and not present:
        lineage_status = "audit_missing"
        lineage_reason = hydration_reason or "selected_source_lineage_not_found"
    elif expected_status == "selected_invalid":
        lineage_status = "selected_invalid"
        lineage_reason = str(selection.get("invalid_reason", "")) or hydration_reason
    elif expected_status == "unavailable_coverage":
        lineage_status = "unavailable_coverage"
        lineage_reason = str(selection.get("invalid_reason", "")) or str(selection.get("availability_state", "")) or hydration_reason
    else:
        lineage_status = "unavailable_coverage" if not present else "matched"
        lineage_reason = hydration_reason
    actual = actual or {}
    return {
        "target_market": str(selection.get("target_market", "")).upper(),
        "decision_timestamp_utc": selection.get("decision_timestamp_utc", ""),
        "selector_context": "EOD_CLOSE",
        "expected_selection_status": expected_status,
        "expected_availability_state": selection.get("availability_state", ""),
        "expected_primary_eligible": expected_primary,
        "expected_invalid_reason": selection.get("invalid_reason", ""),
        "expected_selected_source_row_identifier": selection.get("selected_source_row_identifier", ""),
        "expected_selected_source_content_hash": selection.get("selected_source_content_hash", ""),
        "expected_selected_source_as_of_timestamp_utc": selection.get("selected_source_as_of_timestamp_utc", ""),
        "expected_selected_source_effective_available_at_utc": selection.get("selected_source_effective_available_at_utc", ""),
        "expected_dealer_gamma_source_contract_revision": selection.get("dealer_gamma_source_contract_revision", DEALER_GAMMA_SOURCE_CONTRACT_REVISION),
        "expected_selection_policy_revision": selection.get("selection_policy_revision", DEALER_GAMMA_SELECTION_POLICY_REVISION),
        "actual_feature_row_present": bool(present),
        "actual_feature_row_identifier": actual.get("actual_feature_row_identifier", ""),
        "actual_selection_status": actual.get("dealer_gamma_selection_status", "") if present else expected_status,
        "actual_primary_eligible": bool(expected_primary and present),
        "actual_selected_source_row_identifier": actual.get("selected_source_row_identifier", "") if present else "",
        "actual_selected_source_content_hash": actual.get("selected_source_content_hash", "") if present else "",
        "actual_selected_source_as_of_timestamp_utc": actual.get("selected_source_as_of_timestamp_utc", "") if present else "",
        "actual_selected_source_effective_available_at_utc": actual.get("selected_source_effective_available_at_utc", "") if present else "",
        "actual_dealer_gamma_source_contract_revision": actual.get("dealer_gamma_source_contract_revision", "") if present else "",
        "actual_selection_policy_revision": actual.get("dealer_gamma_selection_policy_revision", "") if present else "",
        "actual_feature_payload_hash": actual.get("actual_feature_payload_hash", "") if present else "",
        "actual_feature_hydration_status": hydration_status,
        "actual_feature_hydration_failure_reason": hydration_reason,
        "lineage_status": lineage_status,
        "lineage_failure_reason": lineage_reason,
    }


def build_dealer_gamma_panel(root: Path, daily_outcomes: pd.DataFrame, cfg: dict[str, Any] | None = None, eod_selection_audit: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel, audit, _, _ = build_dealer_gamma_panel_with_actual_lineage(root, daily_outcomes, cfg, eod_selection_audit)
    return panel, audit


def build_dealer_gamma_eod_actual_feature_lineage(root: Path, eod_selection_audit: pd.DataFrame, dealer_panel: pd.DataFrame | None = None) -> pd.DataFrame:
    if eod_selection_audit.empty:
        return pd.DataFrame(columns=DEALER_GAMMA_EOD_ACTUAL_FEATURE_LINEAGE_COLUMNS)
    panel_by_key = {}
    if dealer_panel is not None and not dealer_panel.empty:
        panel_by_key = {
            (str(row.get("target_market", "")).upper(), str(row.get("decision_timestamp_utc", ""))): row.to_dict()
            for _, row in dealer_panel.iterrows()
        }
    rows = []
    for _, selection in eod_selection_audit.iterrows():
        key = (str(selection.get("target_market", "")).upper(), str(selection.get("decision_timestamp_utc", "")))
        actual = panel_by_key.get(key)
        rows.append(_dealer_gamma_lineage_row(selection, actual, actual is not None, str((actual or {}).get("actual_feature_hydration_status", "not_applicable")), str((actual or {}).get("actual_feature_hydration_failure_reason", ""))))
    return pd.DataFrame(rows, columns=DEALER_GAMMA_EOD_ACTUAL_FEATURE_LINEAGE_COLUMNS)


def build_dealer_gamma_eod_selection_audit(root: Path, daily_outcomes: pd.DataFrame, cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    cfg = cfg or rules(root)
    raw = load_dealer_gamma_history(root)
    rows: list[dict[str, Any]] = []
    for _, outcome in daily_outcomes.iterrows():
        target = str(outcome.get("target_market", "")).upper()
        decision = outcome.get("decision_timestamp_utc", "")
        selection = select_latest_clean_dealer_gamma(
            target_market=target,
            decision_timestamp_utc=decision,
            source_rows=raw,
            selector_context="EOD_CLOSE",
            config=cfg,
        )
        rows.append({
            "target_market": target,
            "decision_date": outcome.get("decision_date", ""),
            "decision_timestamp_utc": decision,
            "selector_context": "EOD_CLOSE",
            **{k: selection.get(k, "") for k in DEALER_GAMMA_SELECTION_COLUMNS if k not in {"target_market", "decision_timestamp_utc", "selector_context"}},
        })
    return pd.DataFrame(rows, columns=["decision_date", *DEALER_GAMMA_SELECTION_COLUMNS])


def build_dealer_gamma_intraday_selection_audit(root: Path, lev_panel: pd.DataFrame, cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    cfg = cfg or rules(root)
    raw = load_dealer_gamma_history(root)
    cols_out = [
        "target_market", "decision_timestamp_utc", "selection_status", "availability_state",
        "primary_eligible", "selected_source_row_identifier", "selected_source_content_hash",
        "selected_source_as_of_timestamp_utc", "selected_source_effective_available_at_utc",
        "selected_source_quality", "selected_data_type", "selected_dealer_position_observed", "selected_raw_chain_present",
        "raw_chain_quality", "data_type", "dealer_position_observed", "dealer_gamma_sign_policy_revision", "net_gex_proxy",
        "negative_gamma_proxy_indicator", "gamma_flip_state", "gamma_flip_distance_pct",
        "invalid_reason", "feature_age_hours", "dealer_gamma_source_contract_revision", "selection_policy_revision",
    ]
    if lev_panel.empty:
        return pd.DataFrame(columns=cols_out)
    cols = {str(c).lower(): c for c in raw.columns}
    sign_convention = str(load_json(root, DEALER_RULES_PATH, {}).get("sign_convention", ""))
    sign_verified = sign_convention == "positive_net_gex_proxy_means_long_gamma_proxy_not_dealer_inventory"
    rows: list[dict[str, Any]] = []
    for _, decision in lev_panel.iterrows():
        target = str(decision.get("target_market", "")).upper()
        base = {"target_market": target, "decision_timestamp_utc": decision.get("decision_timestamp_utc", "")}
        selection = select_latest_clean_dealer_gamma(
            target_market=target,
            decision_timestamp_utc=decision.get("decision_timestamp_utc", ""),
            source_rows=raw,
            selector_context="INTRADAY_1530",
            config=cfg,
        )
        feat = selection.get("row")
        net_gex = safe_float(feat.get(cols.get("net_gex_proxy", "net_gex_proxy"), np.nan)) if isinstance(feat, pd.Series) else np.nan
        negative_gamma = int(pd.notna(net_gex) and sign_verified and net_gex < 0)
        rows.append(base | {k: selection.get(k, "") for k in DEALER_GAMMA_SELECTION_COLUMNS if k not in {"target_market", "decision_timestamp_utc", "selector_context"}} | {
            "raw_chain_quality": selection.get("selected_source_quality", ""),
            "data_type": selection.get("selected_data_type", ""),
            "dealer_position_observed": selection.get("selected_dealer_position_observed", False),
            "dealer_gamma_sign_policy_revision": DEALER_GAMMA_SIGN_POLICY_REVISION if sign_verified else "unverified_sign_convention",
            "net_gex_proxy": net_gex,
            "negative_gamma_proxy_indicator": negative_gamma if sign_verified and selection.get("selection_status") == "selected" else np.nan,
            "gamma_flip_state": feat.get(cols.get("gamma_flip_state", "gamma_flip_state"), "unavailable") if isinstance(feat, pd.Series) else "unavailable",
            "gamma_flip_distance_pct": safe_float(feat.get(cols.get("gamma_flip_distance_pct", "gamma_flip_distance_pct"), np.nan)) if isinstance(feat, pd.Series) else np.nan,
            "invalid_reason": selection.get("invalid_reason", "") if sign_verified or selection.get("selection_status") != "selected" else "gamma_sign_convention_unverified",
        })
    return pd.DataFrame(rows, columns=cols_out)


DEALER_GAMMA_SOURCE_PARITY_COLUMNS = [
    "target_market",
    "decision_timestamp_utc",
    "selector_context",
    "required_source_family",
    "actual_selection_status",
    "fresh_selection_status",
    "actual_selected_source_row_identifier",
    "fresh_selected_source_row_identifier",
    "actual_selected_source_content_hash",
    "fresh_selected_source_content_hash",
    "actual_selected_source_effective_available_at_utc",
    "fresh_selected_source_effective_available_at_utc",
    "actual_selected_source_as_of_timestamp_utc",
    "fresh_selected_source_as_of_timestamp_utc",
    "actual_primary_eligible",
    "fresh_primary_eligible",
    "actual_feature_payload_hash",
    "fresh_feature_payload_hash",
    "selection_parity_status",
    "selection_parity_failure_reason",
    "dealer_gamma_source_contract_revision",
    "selection_policy_revision",
]


def _dealer_gamma_parity_status(actual: dict[str, Any], fresh: dict[str, Any]) -> tuple[str, str]:
    actual_status = str(actual.get("selection_status", ""))
    fresh_status = str(fresh.get("selection_status", ""))
    if actual_status == "selected" and actual.get("actual_feature_row_present") is False:
        return "audit_missing", str(actual.get("invalid_reason", "")) or "actual_feature_lineage_missing"
    if actual_status == "selected":
        required_actual = [
            "selected_source_row_identifier",
            "selected_source_content_hash",
            "selected_source_effective_available_at_utc",
            "selected_source_as_of_timestamp_utc",
            "dealer_gamma_source_contract_revision",
            "selection_policy_revision",
            "feature_payload_hash",
        ]
        missing_actual = [name for name in required_actual if not str(actual.get(name, "")).strip()]
        if missing_actual:
            return "audit_missing", "actual_selection_metadata_missing:" + ",".join(missing_actual)
    if actual_status == "selected_invalid" or fresh_status == "selected_invalid":
        return "selected_invalid", fresh.get("invalid_reason", "") or actual.get("invalid_reason", "") or "dealer_gamma_selected_invalid"
    if actual_status != "selected" and fresh_status != "selected":
        return "unavailable_coverage", fresh.get("invalid_reason", "") or actual.get("invalid_reason", "") or "dealer_gamma_unavailable_coverage"
    fields = [
        ("selected_source_row_identifier", "selected_source_row_identifier"),
        ("selected_source_content_hash", "selected_source_content_hash"),
        ("selected_source_effective_available_at_utc", "selected_source_effective_available_at_utc"),
        ("selected_source_as_of_timestamp_utc", "selected_source_as_of_timestamp_utc"),
        ("dealer_gamma_source_contract_revision", "dealer_gamma_source_contract_revision"),
        ("selection_policy_revision", "selection_policy_revision"),
        ("feature_payload_hash", "feature_payload_hash"),
        ("primary_eligible", "primary_eligible"),
    ]
    mismatches = [name for name, other in fields if str(actual.get(name, "")) != str(fresh.get(other, ""))]
    if actual_status == "selected" and fresh_status == "selected" and not mismatches:
        return "matched", ""
    return "mismatch", "dealer_gamma_actual_fresh_mismatch:" + ",".join(mismatches or ["selection_status"])


EOD_ACTUAL_FEATURE_LINEAGE_REQUIRED_COLUMNS = [
    "target_market",
    "decision_timestamp_utc",
    "expected_selection_status",
    "expected_primary_eligible",
    "actual_feature_row_present",
    "actual_selection_status",
    "actual_primary_eligible",
    "actual_selected_source_row_identifier",
    "actual_selected_source_content_hash",
    "actual_selected_source_as_of_timestamp_utc",
    "actual_selected_source_effective_available_at_utc",
    "actual_dealer_gamma_source_contract_revision",
    "actual_selection_policy_revision",
    "actual_feature_payload_hash",
    "lineage_status",
]


def _require_columns(df: pd.DataFrame | None, columns: list[str], message: str) -> None:
    if df is None:
        raise ValueError(message)
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(message + ": " + ",".join(missing))


def _dealer_gamma_parity_row(actual: dict[str, Any], fresh: dict[str, Any], context: str, family: str, status: str, reason: str) -> dict[str, Any]:
    target = str(actual.get("target_market", "")).upper()
    decision = actual.get("decision_timestamp_utc", "")
    return {
        "target_market": target,
        "decision_timestamp_utc": decision,
        "selector_context": context,
        "required_source_family": family,
        "actual_selection_status": actual.get("selection_status", ""),
        "fresh_selection_status": fresh.get("selection_status", ""),
        "actual_selected_source_row_identifier": actual.get("selected_source_row_identifier", ""),
        "fresh_selected_source_row_identifier": fresh.get("selected_source_row_identifier", ""),
        "actual_selected_source_content_hash": actual.get("selected_source_content_hash", ""),
        "fresh_selected_source_content_hash": fresh.get("selected_source_content_hash", ""),
        "actual_selected_source_effective_available_at_utc": actual.get("selected_source_effective_available_at_utc", ""),
        "fresh_selected_source_effective_available_at_utc": fresh.get("selected_source_effective_available_at_utc", ""),
        "actual_selected_source_as_of_timestamp_utc": actual.get("selected_source_as_of_timestamp_utc", ""),
        "fresh_selected_source_as_of_timestamp_utc": fresh.get("selected_source_as_of_timestamp_utc", ""),
        "actual_primary_eligible": bool(actual.get("primary_eligible", False)),
        "fresh_primary_eligible": bool(fresh.get("primary_eligible", False)),
        "actual_feature_payload_hash": actual.get("feature_payload_hash", ""),
        "fresh_feature_payload_hash": fresh.get("feature_payload_hash", ""),
        "selection_parity_status": status,
        "selection_parity_failure_reason": reason,
        "dealer_gamma_source_contract_revision": DEALER_GAMMA_SOURCE_CONTRACT_REVISION,
        "selection_policy_revision": DEALER_GAMMA_SELECTION_POLICY_REVISION,
    }


def build_dealer_gamma_eod_actual_vs_fresh_parity_audit(
    root: Path,
    eod_actual_feature_lineage: pd.DataFrame,
    cfg: dict[str, Any] | None = None,
) -> pd.DataFrame:
    _require_columns(eod_actual_feature_lineage, EOD_ACTUAL_FEATURE_LINEAGE_REQUIRED_COLUMNS, "eod actual feature lineage schema required")
    cfg = cfg or rules(root)
    raw = load_dealer_gamma_history(root)
    rows: list[dict[str, Any]] = []
    for _, row in eod_actual_feature_lineage.iterrows():
        expected_status = str(row.get("expected_selection_status", ""))
        expected_primary = bool(row.get("expected_primary_eligible", False))
        actual = {
            "target_market": row.get("target_market", ""),
            "decision_timestamp_utc": row.get("decision_timestamp_utc", ""),
            "selection_status": row.get("actual_selection_status", ""),
            "primary_eligible": bool(row.get("actual_primary_eligible", False)),
            "invalid_reason": row.get("lineage_failure_reason", row.get("actual_feature_hydration_failure_reason", "")),
            "actual_feature_row_present": bool(row.get("actual_feature_row_present", False)),
            "selected_source_row_identifier": row.get("actual_selected_source_row_identifier", ""),
            "selected_source_content_hash": row.get("actual_selected_source_content_hash", ""),
            "selected_source_effective_available_at_utc": row.get("actual_selected_source_effective_available_at_utc", ""),
            "selected_source_as_of_timestamp_utc": row.get("actual_selected_source_as_of_timestamp_utc", ""),
            "dealer_gamma_source_contract_revision": row.get("actual_dealer_gamma_source_contract_revision", ""),
            "selection_policy_revision": row.get("actual_selection_policy_revision", ""),
            "feature_payload_hash": row.get("actual_feature_payload_hash", ""),
        }
        fresh = select_latest_clean_dealer_gamma(
            target_market=str(row.get("target_market", "")).upper(),
            decision_timestamp_utc=row.get("decision_timestamp_utc", ""),
            source_rows=raw,
            selector_context="EOD_CLOSE",
            config=cfg,
        )
        fresh["feature_payload_hash"] = dealer_gamma_payload_hash_from_row(fresh.get("row")) if fresh.get("selection_status") == "selected" else ""
        if expected_status == "selected_invalid":
            status, reason = "selected_invalid", str(row.get("expected_invalid_reason", "")) or str(row.get("lineage_failure_reason", ""))
        elif expected_status == "unavailable_coverage":
            status, reason = "unavailable_coverage", str(row.get("expected_invalid_reason", "")) or str(row.get("lineage_failure_reason", ""))
        elif expected_status == "selected" and expected_primary:
            if str(fresh.get("selection_status", "")) not in {"selected", "selected_invalid"} and bool(row.get("actual_feature_row_present", False)):
                status, reason = "mismatch", "expected_selected_but_fresh_unavailable"
            else:
                status, reason = _dealer_gamma_parity_status(actual, fresh)
        else:
            status, reason = "unavailable_coverage", str(row.get("lineage_failure_reason", "")) or "dealer_gamma_unavailable_coverage"
        rows.append(_dealer_gamma_parity_row(actual, fresh, "EOD_CLOSE", "DealerGammaEOD", status, reason))
    return pd.DataFrame(rows, columns=DEALER_GAMMA_SOURCE_PARITY_COLUMNS)


def build_dealer_gamma_intraday_selection_parity_audit(
    root: Path,
    dealer_intraday_selection: pd.DataFrame,
    cfg: dict[str, Any] | None = None,
) -> pd.DataFrame:
    cfg = cfg or rules(root)
    raw = load_dealer_gamma_history(root)
    rows: list[dict[str, Any]] = []

    def add_parity(actual: dict[str, Any], context: str, family: str) -> None:
        fresh = select_latest_clean_dealer_gamma(
            target_market=str(actual.get("target_market", "")).upper(),
            decision_timestamp_utc=actual.get("decision_timestamp_utc", ""),
            source_rows=raw,
            selector_context=context,
            config=cfg,
        )
        fresh["feature_payload_hash"] = dealer_gamma_payload_hash_from_row(fresh.get("row")) if fresh.get("selection_status") == "selected" else ""
        status, reason = _dealer_gamma_parity_status(actual, fresh)
        rows.append(_dealer_gamma_parity_row(actual, fresh, context, family, status, reason))

    if not dealer_intraday_selection.empty:
        for _, row in dealer_intraday_selection.iterrows():
            add_parity({
                "target_market": row.get("target_market", ""),
                "decision_timestamp_utc": row.get("decision_timestamp_utc", ""),
                "selection_status": row.get("selection_status", ""),
                "primary_eligible": bool(row.get("primary_eligible", False)),
                "invalid_reason": row.get("invalid_reason", ""),
                "selected_source_row_identifier": row.get("selected_source_row_identifier", ""),
                "selected_source_content_hash": row.get("selected_source_content_hash", ""),
                "selected_source_effective_available_at_utc": row.get("selected_source_effective_available_at_utc", ""),
                "selected_source_as_of_timestamp_utc": row.get("selected_source_as_of_timestamp_utc", ""),
                "dealer_gamma_source_contract_revision": row.get("dealer_gamma_source_contract_revision", ""),
                "selection_policy_revision": row.get("selection_policy_revision", ""),
            }, "INTRADAY_1530", "DealerGammaIntraday")
    return pd.DataFrame(rows, columns=DEALER_GAMMA_SOURCE_PARITY_COLUMNS)


def build_dealer_gamma_source_selection_parity_audit(
    root: Path,
    eod_actual_feature_lineage: pd.DataFrame,
    dealer_intraday_selection: pd.DataFrame,
    cfg: dict[str, Any] | None = None,
) -> pd.DataFrame:
    eod = build_dealer_gamma_eod_actual_vs_fresh_parity_audit(root, eod_actual_feature_lineage, cfg)
    intraday = build_dealer_gamma_intraday_selection_parity_audit(root, dealer_intraday_selection, cfg)
    return pd.concat([eod, intraday], ignore_index=True)


def split_dealer_gamma_state_distance(dealer_panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    audit_cols = [
        "target_market",
        "observed_raw_chain_row_count",
        "local_flip_found_count",
        "no_local_flip_count",
        "unavailable_flip_count",
        "state_model_row_count",
        "distance_model_row_count",
        "drop_reason",
    ]
    if dealer_panel.empty:
        return dealer_panel.copy(), dealer_panel.copy(), pd.DataFrame(columns=audit_cols)
    state = dealer_panel.copy()
    if "gamma_flip_distance_pct" in state.columns:
        state = state.drop(columns=["gamma_flip_distance_pct"])
    distance = dealer_panel[dealer_panel.get("gamma_flip_state", pd.Series(dtype=str)).astype(str).eq("local_flip_found")].copy()
    distance = distance[pd.to_numeric(distance.get("gamma_flip_distance_pct", pd.Series(dtype=float)), errors="coerce").notna()]
    rows = []
    for target, group in dealer_panel.groupby("target_market"):
        flip = group.get("gamma_flip_state", pd.Series(dtype=str)).astype(str)
        dgroup = distance[distance["target_market"].astype(str).eq(str(target))]
        rows.append({
            "target_market": target,
            "observed_raw_chain_row_count": len(group),
            "local_flip_found_count": int(flip.eq("local_flip_found").sum()),
            "no_local_flip_count": int(flip.eq("no_local_flip").sum()),
            "unavailable_flip_count": int(flip.eq("unavailable").sum()),
            "state_model_row_count": len(group),
            "distance_model_row_count": len(dgroup),
            "drop_reason": "distance_model_requires_local_flip_found",
        })
    return state, distance, pd.DataFrame(rows, columns=audit_cols)


def expiry_comparison_group(day: pd.Timestamp, expiry: pd.DataFrame, classification: pd.DataFrame | None = None, decision_ts: pd.Timestamp | None = None) -> str:
    if day.weekday() != 4:
        return "non_friday"
    if classification is not None:
        classified = expiry_classification_for_date(classification, day, decision_ts)
        group = str(classified.get("comparison_group", "unavailable_incomplete_schedule"))
        if group == "holiday_adjusted_expiry_excluded_from_friday_primary":
            return group
        return group if classified.get("availability_status") == "available" else "unavailable_incomplete_schedule"
    flags = expiry_flags_for_date(expiry, day)
    rows = expiry[expiry["date"].astype(str).eq(day.date().isoformat())] if not expiry.empty and "date" in expiry.columns else pd.DataFrame()
    expiry_type = " ".join(rows.get("expiry_type", pd.Series(dtype=str)).astype(str).str.lower().tolist())
    if flags["triple_witching_flag"]:
        return "triple_witching"
    if flags["quarterly_expiry_flag"]:
        return "quarterly_expiry_non_triple"
    if flags["monthly_expiry_flag"] or "monthly" in expiry_type:
        return "monthly_expiry_non_quarterly"
    return "non_expiry_friday"


def select_strict_gamma_snapshot_for_event(raw: pd.DataFrame, target: str, decision_ts: pd.Timestamp, cfg: dict[str, Any]) -> tuple[pd.Series | None, dict[str, Any]]:
    audit = {
        "target_market": target,
        "decision_timestamp_utc": decision_ts.isoformat(),
        "selector_context": "EXPIRY_0930",
        "feature_timing_bucket": "unavailable",
        "selected_snapshot_asof_utc": "",
        "selected_snapshot_effective_utc": "",
        "selected_snapshot_age_hours": np.nan,
        "selected_snapshot_source_path": "",
        "selected_snapshot_quality": "",
        "availability_status": "unavailable",
        "availability_failure_reason": "gamma_history_missing",
        "selection_status": "unavailable_coverage",
        "primary_eligible": False,
        "selected_source_row_identifier": "",
        "selected_source_content_hash": "",
        "dealer_gamma_source_contract_revision": DEALER_GAMMA_SOURCE_CONTRACT_REVISION,
        "selection_policy_revision": DEALER_GAMMA_SELECTION_POLICY_REVISION,
    }
    if raw.empty:
        return None, audit
    selection = select_latest_clean_dealer_gamma(
        target_market=target,
        decision_timestamp_utc=decision_ts,
        source_rows=raw,
        selector_context="EXPIRY_0930",
        config=cfg,
    )
    selected = selection.get("row")
    invalid_reason = str(selection.get("invalid_reason", ""))
    if invalid_reason.startswith("dealer_gamma_required_payload_missing"):
        cols = _dealer_gamma_columns(raw)
        target_col = cols.get("target")
        effective_col = cols.get("effective")
        asof_col = cols.get("asof")
        if target_col and effective_col and asof_col:
            work = raw.copy()
            work["_target_market"] = work[target_col].astype(str).str.upper()
            work["_effective_ts"] = pd.to_datetime(work[effective_col], utc=True, errors="coerce")
            work["_asof_ts"] = pd.to_datetime(work[asof_col], utc=True, errors="coerce")
            prior = work[
                work["_target_market"].eq(str(target).upper())
                & (work["_effective_ts"] <= decision_ts)
                & (work["_asof_ts"] <= decision_ts)
            ]
            if prior.empty:
                invalid_reason = "no_strict_prior_gamma_snapshot"
    audit.update({
        "selection_status": selection.get("selection_status", ""),
        "primary_eligible": bool(selection.get("primary_eligible", False)),
        "selected_source_row_identifier": selection.get("selected_source_row_identifier", ""),
        "selected_source_content_hash": selection.get("selected_source_content_hash", ""),
        "dealer_gamma_source_contract_revision": selection.get("dealer_gamma_source_contract_revision", ""),
        "selection_policy_revision": selection.get("selection_policy_revision", ""),
        "availability_failure_reason": invalid_reason,
    })
    if not isinstance(selected, pd.Series):
        return None, audit
    event_day = decision_ts.tz_convert(ET).date()
    asof_ts = parse_ts(selection.get("selected_source_as_of_timestamp_utc", ""))
    eff_ts = parse_ts(selection.get("selected_source_effective_available_at_utc", ""))
    asof_day = asof_ts.tz_convert(ET).date() if asof_ts is not None else None
    bucket = "event_day_pre_open" if asof_day == event_day else "prior_regular_session"
    audit.update({
        "feature_timing_bucket": bucket,
        "selected_snapshot_asof_utc": asof_ts.isoformat() if asof_ts is not None else selection.get("selected_source_as_of_timestamp_utc", ""),
        "selected_snapshot_effective_utc": eff_ts.isoformat() if eff_ts is not None else selection.get("selected_source_effective_available_at_utc", ""),
        "selected_snapshot_age_hours": safe_float(selection.get("feature_age_hours")),
        "selected_snapshot_source_path": selected.get("source_path_or_provider", ""),
        "selected_snapshot_quality": selection.get("selected_source_quality", ""),
        "availability_status": "available",
        "availability_failure_reason": "",
    })
    return selected, audit


def build_expiry_intraday_outcome(
    root: Path,
    target: str,
    event_date: Any,
    comparison_group: str,
    nyse_calendar: pd.DataFrame,
    rules_cfg: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    day = pd.Timestamp(event_date).date()
    event_rules = expiry_intraday_rules(root)
    convention = str(event_rules.get("bar_timestamp_convention", rules_cfg.get("bar_timestamp_convention", "bar_end")))
    open_method = str(event_rules.get("regular_session_open_price_method", "first_regular_session_bar_open"))
    verified = bool(event_rules.get("provider_bar_semantics_verified", False))
    provider_source = str(event_rules.get("provider_bar_semantics_source", ""))
    provider_verified_at = str(event_rules.get("provider_bar_semantics_verified_at_utc", ""))
    open_time = parse_et_time(str(event_rules.get("regular_session_open_bar_timestamp_et", "09:35")), time(9, 35))
    close_time = parse_et_time(str(event_rules.get("regular_session_close_bar_timestamp_et", event_rules.get("event_primary_close_bar_et", "16:00"))), time(16, 0))
    session = get_nyse_session(day, nyse_calendar)
    decision_ts = pd.Timestamp.combine(day, time(9, 30)).tz_localize(ET).tz_convert(UTC)
    outcome_label = "expiry_session_return_first_regular_bar_open_to_close" if open_method == "first_regular_session_bar_open" else "expiry_session_return_0930_open_to_close"
    audit = {
        "target_market": target,
        "event_date": day.isoformat(),
        "comparison_group": comparison_group,
        "decision_timestamp_utc": decision_ts.isoformat(),
        "bar_timestamp_convention": convention,
        "provider_bar_semantics_verified": verified,
        "provider_bar_semantics_source": provider_source,
        "provider_bar_semantics_verified_at_utc": provider_verified_at,
        "session_open_price_method": open_method,
        "session_open_price_source_field": "open" if open_method == "first_regular_session_bar_open" else str(event_rules.get("session_open_price_source_field", "")),
        "session_open_price_timestamp_utc": "",
        "event_open_bar_timestamp_utc": "",
        "event_close_bar_timestamp_utc": "",
        "outcome_window_label": outcome_label,
        "calendar_session_status": session.get("calendar_coverage_status", "missing"),
        "is_early_close": session.get("is_early_close", False),
        "outcome_availability_status": "unavailable",
        "outcome_availability_failure_reason": "",
        "outcome_data_quality": "unavailable",
    }
    provenance = validate_nyse_calendar_provenance(root, nyse_calendar)
    if provenance["status"] != "passed":
        audit["outcome_availability_failure_reason"] = "nyse_calendar_provenance_validation_failed:" + provenance["reason"]
        return None, audit
    if not verified:
        audit["outcome_availability_failure_reason"] = "provider_bar_semantics_unverified"
        return None, audit
    if session["calendar_coverage_status"] != "covered":
        audit["outcome_availability_failure_reason"] = "nyse_calendar_coverage_missing"
        return None, audit
    if not session["is_regular_session"]:
        audit["outcome_availability_failure_reason"] = "not_regular_session"
        return None, audit
    if session["is_early_close"]:
        audit["outcome_availability_failure_reason"] = "early_close_session_excluded_from_primary"
        return None, audit
    if convention != "bar_end":
        audit["outcome_availability_failure_reason"] = "expiry_bar_timestamp_convention_unknown"
        return None, audit
    if open_method not in {"first_regular_session_bar_open", "official_session_open_field"}:
        audit["outcome_availability_failure_reason"] = "session_open_price_method_unknown"
        return None, audit
    path = intraday_bars_path(root, target)
    bars = load_intraday_bars(root, target)
    if bars.empty or path is None:
        audit["outcome_availability_failure_reason"] = "expiry_intraday_bars_missing"
        return None, audit
    bars = bars[bars["timestamp_utc"].dt.tz_convert(ET).dt.date == day].copy()
    if bars.empty:
        audit["outcome_availability_failure_reason"] = "expiry_intraday_bars_missing"
        return None, audit
    et_times = bars["timestamp_utc"].dt.tz_convert(ET)
    open_bar = exact_bar(bars, et_times, open_time)
    close_bar = exact_bar(bars, et_times, close_time)
    if open_bar is None:
        audit["outcome_availability_failure_reason"] = "expiry_exact_first_regular_bar_missing"
        return None, audit
    if close_bar is None:
        audit["outcome_availability_failure_reason"] = "expiry_exact_regular_close_bar_missing"
        return None, audit
    window = bars[(et_times.dt.time >= open_time) & (et_times.dt.time <= close_time)].copy()
    if open_method == "official_session_open_field":
        source_field = str(event_rules.get("session_open_price_source_field", "official_session_open"))
        if source_field not in bars.columns:
            audit["outcome_availability_failure_reason"] = "official_session_open_field_missing"
            return None, audit
        event_open = safe_float(open_bar.get(source_field, np.nan))
        audit["session_open_price_source_field"] = source_field
    else:
        event_open = safe_float(open_bar.get("open", open_bar.get("close", np.nan)))
    event_close = safe_float(close_bar.get("close", np.nan))
    high = safe_float(window["high"].max(), np.nan) if "high" in window.columns else np.nan
    low = safe_float(window["low"].min(), np.nan) if "low" in window.columns else np.nan
    session_range = high - low if pd.notna(high) and pd.notna(low) else np.nan
    close_location = (event_close - low) / session_range if pd.notna(session_range) and session_range > 0 else np.nan
    audit.update({
        "event_open_bar_timestamp_utc": open_bar.get("timestamp_utc"),
        "event_close_bar_timestamp_utc": close_bar.get("timestamp_utc"),
        "session_open_price_timestamp_utc": open_bar.get("timestamp_utc"),
        "outcome_availability_status": "available",
        "outcome_availability_failure_reason": "",
        "outcome_data_quality": "intraday_primary",
    })
    outcome = {
        "decision_timestamp_utc": decision_ts.isoformat(),
        "outcome_start_timestamp_utc": open_bar.get("timestamp_utc"),
        "outcome_end_timestamp_utc": close_bar.get("timestamp_utc"),
        "event_open_bar_timestamp_utc": open_bar.get("timestamp_utc"),
        "event_close_bar_timestamp_utc": close_bar.get("timestamp_utc"),
        outcome_label: event_close / event_open - 1 if event_open and pd.notna(event_open) and pd.notna(event_close) else np.nan,
        outcome_label.replace("return_", "absolute_return_"): abs(event_close / event_open - 1) if event_open and pd.notna(event_open) and pd.notna(event_close) else np.nan,
        "expiry_session_high_low_range_pct": session_range / event_open if event_open and pd.notna(session_range) else np.nan,
        "expiry_session_close_location_value": close_location,
        "intraday_outcome_source_path": str(path.relative_to(root)).replace("\\", "/"),
        "intraday_outcome_source_hash": hash_file(path),
        "bar_timestamp_convention": convention,
        "provider_bar_semantics_verified": verified,
        "provider_bar_semantics_source": provider_source,
        "provider_bar_semantics_verified_at_utc": provider_verified_at,
        "session_open_price_method": open_method,
        "session_open_price_source_field": audit["session_open_price_source_field"],
        "session_open_price_timestamp_utc": open_bar.get("timestamp_utc"),
        "outcome_window_label": outcome_label,
        "outcome_data_quality": "intraday_primary",
    }
    return outcome, audit


def build_dealer_gamma_expiry_event_panel(root: Path, daily_outcomes: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    expiry = load_expiry_calendar(root)
    classification = load_expiry_friday_classification(root)
    nyse_calendar = load_nyse_calendar(root)
    classification_validation = validate_expiry_classification_provenance(root, classification, nyse_calendar)
    if classification_validation.get("status") != "passed":
        reason = "expiry_classification_provenance_invalid:" + str(classification_validation.get("reason", "unknown"))
        audit = pd.DataFrame([
            {"module": "ExpiryCalendar", "audit_status": "data_quality_blocked", "availability_status": "unavailable", "availability_failure_reason": reason, "reason": reason},
            {"module": "DealerGammaExpiryConditioned", "audit_status": "data_quality_blocked", "availability_status": "unavailable", "availability_failure_reason": reason, "reason": reason},
            {"module": "ExpiryPostSecondary", "audit_status": "data_quality_blocked", "availability_status": "unavailable", "availability_failure_reason": reason, "reason": reason},
        ])
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), audit, pd.DataFrame(), pd.DataFrame(columns=CALENDAR_AVAILABILITY_AUDIT_COLUMNS)
    if daily_outcomes.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame([{"module": "DealerGammaExpiry", "audit_status": "insufficient_data", "reason": "daily_outcomes_missing"}]), pd.DataFrame(), pd.DataFrame(columns=CALENDAR_AVAILABILITY_AUDIT_COLUMNS)
    raw = load_dealer_gamma_history(root)
    calendar_rows: list[dict[str, Any]] = []
    conditioned_rows: list[dict[str, Any]] = []
    post_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    outcome_audit_rows: list[dict[str, Any]] = []
    calendar_availability_rows: list[dict[str, Any]] = []
    for _, outcome in daily_outcomes.iterrows():
        target = str(outcome["target_market"]).upper()
        day = pd.Timestamp(outcome.get("decision_date") or pd.to_datetime(outcome["decision_timestamp_utc"]).date())
        decision_ts = pd.Timestamp.combine(day.date(), time(9, 30)).tz_localize(ET).tz_convert(UTC)
        group = expiry_comparison_group(day, expiry, classification, decision_ts)
        if group in {"non_friday", "unavailable_incomplete_schedule", "holiday_adjusted_expiry_excluded_from_friday_primary"}:
            audit_rows.append({"module": "ExpiryCalendar", "audit_status": "excluded", "reason": group, "target_market": target, "decision_timestamp_utc": decision_ts.isoformat()})
            continue
        flags = expiry_flags_for_date(expiry, day)
        calendar_availability = resolve_calendar_availability(root, expiry, day, decision_ts, group)
        calendar_availability_rows.append(calendar_availability)
        intraday_outcome, outcome_audit = build_expiry_intraday_outcome(root, target, day, group, nyse_calendar, cfg)
        outcome_audit_rows.append(outcome_audit)
        calendar_available = calendar_availability["availability_status"] == "available"
        post_session = next_regular_session(day, nyse_calendar)
        post_start_ts = session_timestamp_utc(post_session, "regular_open_et") if post_session else None
        post_end_ts = session_timestamp_utc(post_session, "regular_close_et") if post_session else None
        post_available = calendar_available and post_session is not None and bool(post_session.get("is_regular_session")) and not bool(post_session.get("is_early_close"))
        post_row = {
            "analysis_id": f"expiry_post_secondary_{target}_{day.date()}",
            "module": "ExpiryPostSecondary",
            "feature_family": "ExpiryPostSecondary",
            "feature_name": group,
            "feature_value": flags["monthly_expiry_flag"] + flags["quarterly_expiry_flag"] + flags["triple_witching_flag"],
            "feature_unit": "event_flag",
            "target_market": target,
            "decision_date": day.date().isoformat(),
            "decision_timestamp_utc": decision_ts.isoformat(),
            "feature_as_of_timestamp_utc": calendar_availability["feature_as_of_timestamp_utc"],
            "effective_available_at_utc": calendar_availability["effective_available_at_utc"],
            "feature_age_hours": round((decision_ts - parse_ts(calendar_availability["effective_available_at_utc"])).total_seconds() / 3600, 4) if parse_ts(calendar_availability["effective_available_at_utc"]) is not None else np.nan,
            "availability_basis": calendar_availability["availability_basis"],
            "availability_confidence": "medium",
            "source_path_or_provider": str(EXPIRY_CALENDAR_PATH).replace("\\", "/"),
            "source_hash_or_request_id": hash_file(root / EXPIRY_CALENDAR_PATH) if (root / EXPIRY_CALENDAR_PATH).exists() else "",
            "data_type": "calendar_event",
            "is_proxy": False,
            "observed_flow": False,
            "quality_grade": "high",
            "availability_status": "available" if post_available else "unavailable",
            "availability_failure_reason": "" if post_available else (calendar_availability["availability_failure_reason"] or "post_expiry_regular_session_unavailable"),
            "post_expiry_next_session_return": outcome.get("next_session_return", np.nan),
            "post_expiry_next_session_absolute_return": outcome.get("next_session_absolute_return", np.nan),
            "post_expiry_next_session_high_low_range_pct": outcome.get("next_session_high_low_range_pct", np.nan),
            "outcome_start_timestamp_utc": post_start_ts.isoformat() if post_start_ts is not None else "",
            "outcome_end_timestamp_utc": post_end_ts.isoformat() if post_end_ts is not None else "",
            "post_expiry_session_date": post_session.get("session_date", "") if post_session else "",
            "post_expiry_session_calendar_status": post_session.get("calendar_coverage_status", "missing") if post_session else "missing",
            "comparison_group": group,
            "primary_or_robustness": "secondary",
            **flags,
        }
        if post_available:
            post_rows.append(post_row)
        if intraday_outcome is None or not calendar_available:
            continue
        row = outcome.to_dict()
        row = {k: v for k, v in row.items() if not str(k).startswith("next_session_")}
        row.update({
            "analysis_id": f"expiry_calendar_{target}_{day.date()}",
            "feature_family": "ExpiryCalendar",
            "feature_name": group,
            "feature_value": flags["monthly_expiry_flag"] + flags["quarterly_expiry_flag"] + flags["triple_witching_flag"],
            "feature_unit": "event_flag",
            "feature_as_of_timestamp_utc": calendar_availability["feature_as_of_timestamp_utc"],
            "effective_available_at_utc": calendar_availability["effective_available_at_utc"],
            "decision_timestamp_utc": decision_ts.isoformat(),
            "feature_age_hours": round((decision_ts - parse_ts(calendar_availability["effective_available_at_utc"])).total_seconds() / 3600, 4) if parse_ts(calendar_availability["effective_available_at_utc"]) is not None else np.nan,
            "availability_basis": calendar_availability["availability_basis"],
            "availability_confidence": "high",
            "source_path_or_provider": str(EXPIRY_CALENDAR_PATH).replace("\\", "/"),
            "data_type": "calendar_event",
            "is_proxy": False,
            "observed_flow": False,
            "quality_grade": "high",
            "availability_status": "available",
            "availability_failure_reason": "",
            "comparison_group": group,
            "monthly_expiry_flag": flags["monthly_expiry_flag"],
            "quarterly_expiry_flag": flags["quarterly_expiry_flag"],
            "triple_witching_flag": flags["triple_witching_flag"],
            "primary_or_robustness": "primary",
            **intraday_outcome,
        })
        calendar_rows.append(row)
        selected_gamma, gamma_audit = select_strict_gamma_snapshot_for_event(raw, target, decision_ts, cfg)
        gamma_audit["comparison_group"] = group
        audit_rows.append(gamma_audit)
        if selected_gamma is not None:
            cols = {str(c).lower(): c for c in raw.columns}
            flip_state = str(selected_gamma.get(cols.get("gamma_flip_state", "gamma_flip_state"), "unavailable"))
            conditioned = row.copy()
            conditioned.update({
                "analysis_id": f"expiry_gamma_conditioned_{target}_{day.date()}",
                "feature_family": "DealerGammaExpiryConditioned",
                "feature_name": group,
                "data_type": "reconstructed_from_raw_chain",
                "is_proxy": True,
                "observed_flow": False,
                "feature_as_of_timestamp_utc": gamma_audit["selected_snapshot_asof_utc"],
                "effective_available_at_utc": gamma_audit["selected_snapshot_effective_utc"],
                "feature_age_hours": gamma_audit["selected_snapshot_age_hours"],
                "feature_timing_bucket": gamma_audit["feature_timing_bucket"],
                "selected_snapshot_asof_utc": gamma_audit["selected_snapshot_asof_utc"],
                "selected_snapshot_effective_utc": gamma_audit["selected_snapshot_effective_utc"],
                "selected_snapshot_source_path": gamma_audit["selected_snapshot_source_path"],
                "selected_snapshot_quality": gamma_audit["selected_snapshot_quality"],
                "net_gex_proxy": safe_float(selected_gamma.get(cols.get("net_gex_proxy", "net_gex_proxy"), np.nan)),
                "pinning_proxy": safe_float(selected_gamma.get(cols.get("pinning_proxy", "pinning_proxy"), np.nan)),
                "local_flip_found_flag": int(flip_state == "local_flip_found"),
                "no_local_flip_flag": int(flip_state == "no_local_flip"),
                "selected_source_row_identifier": gamma_audit.get("selected_source_row_identifier", ""),
                "selected_source_effective_available_at_utc": gamma_audit["selected_snapshot_effective_utc"],
                "selected_source_hash_or_index": gamma_audit.get("selected_source_content_hash", ""),
                "selected_source_content_hash": gamma_audit.get("selected_source_content_hash", ""),
                "selection_policy_version": gamma_audit.get("selection_policy_revision", DEALER_GAMMA_SELECTION_POLICY_REVISION),
            })
            conditioned_rows.append(conditioned)
    if expiry.empty:
        audit_rows.append({"module": "DealerGammaExpiry", "audit_status": "insufficient_data", "reason": "expiry_calendar_missing"})
    else:
        audit_rows.append({"module": "DealerGammaExpiry", "audit_status": "available" if calendar_rows else "insufficient_data", "reason": "" if calendar_rows else "no_expiry_or_friday_rows", "event_rows": len(calendar_rows), "conditioned_event_rows": len(conditioned_rows)})
    return pd.DataFrame(calendar_rows), pd.DataFrame(conditioned_rows), pd.DataFrame(post_rows), pd.DataFrame(audit_rows), pd.DataFrame(outcome_audit_rows), pd.DataFrame(calendar_availability_rows, columns=CALENDAR_AVAILABILITY_AUDIT_COLUMNS)


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    n = len(p_values)
    if n == 0:
        return []
    order = np.argsort(p_values)
    adjusted = np.empty(n)
    prev = 1.0
    for rank, idx in enumerate(order[::-1], start=1):
        original_rank = n - rank + 1
        val = min(prev, p_values[idx] * n / original_rank)
        adjusted[idx] = val
        prev = val
    return adjusted.tolist()


def summarize_association(panel: pd.DataFrame, feature_family: str, outcome_col: str, feature_col: str, primary: str = "primary") -> pd.DataFrame:
    cols = ["feature_family", "feature_name", "target_market", "outcome", "sample_count", "effect_size", "effect_size_bps", "raw_p_value", "adjusted_p_value", "multiple_testing_method", "primary_or_robustness", "evidence_engine", "evidence_verdict"]
    if panel.empty or feature_col not in panel.columns or outcome_col not in panel.columns:
        return pd.DataFrame(columns=cols)
    rows = []
    for target, group in panel.groupby("target_market"):
        work = group[[feature_col, outcome_col]].copy()
        work[feature_col] = pd.to_numeric(work[feature_col], errors="coerce")
        work[outcome_col] = pd.to_numeric(work[outcome_col], errors="coerce")
        work = work.dropna()
        n = len(work)
        if n < 30 or work[feature_col].std() == 0:
            effect = np.nan
            verdict = "insufficient_data"
        else:
            corr = work[feature_col].corr(work[outcome_col])
            effect = corr
            verdict = "exploratory_association" if abs(corr) > 0.05 else "no_incremental_value"
        rows.append({
            "feature_family": feature_family,
            "feature_name": feature_col,
            "target_market": target,
            "outcome": outcome_col,
            "sample_count": n,
            "effect_size": effect,
            "effect_size_bps": effect * 10000 if pd.notna(effect) else np.nan,
            "raw_p_value": np.nan,
            "adjusted_p_value": np.nan,
            "multiple_testing_method": "benjamini_hochberg",
            "primary_or_robustness": primary,
            "evidence_engine": "descriptive_association_only",
            "evidence_verdict": verdict,
        })
    return pd.DataFrame(rows, columns=cols)


def fit_feature_encoder(df: pd.DataFrame, columns: list[str]) -> dict[str, Any]:
    encoder: dict[str, Any] = {"columns": []}
    for col in columns:
        if col not in df.columns:
            encoder["columns"].append({"name": col, "kind": "missing", "output_columns": [col]})
            continue
        series = df[col]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().mean() >= 0.8 or series.dropna().empty:
            encoder["columns"].append({"name": col, "kind": "numeric", "output_columns": [col]})
        else:
            vocab = sorted(series.dropna().astype(str).unique().tolist())
            encoder["columns"].append({
                "name": col,
                "kind": "categorical",
                "vocabulary": vocab,
                "output_columns": [f"{col}={v}" for v in vocab],
            })
    return encoder


def transform_feature_encoder(df: pd.DataFrame, encoder: dict[str, Any]) -> tuple[pd.DataFrame, int]:
    pieces: list[pd.DataFrame] = []
    unseen_count = 0
    for spec in encoder.get("columns", []):
        col = spec["name"]
        if spec["kind"] == "missing" or col not in df.columns:
            pieces.append(pd.DataFrame({spec["output_columns"][0]: np.nan}, index=df.index))
            continue
        series = df[col]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        if spec["kind"] == "numeric":
            pieces.append(pd.DataFrame({spec["output_columns"][0]: pd.to_numeric(series, errors="coerce")}, index=df.index))
            continue
        text = series.astype(str)
        vocab = set(spec.get("vocabulary", []))
        non_null = series.notna()
        unseen_count += int((non_null & ~text.isin(vocab)).sum())
        data = {out_col: (text == out_col.split("=", 1)[1]).astype(float) for out_col in spec["output_columns"]}
        pieces.append(pd.DataFrame(data, index=df.index))
    if not pieces:
        return pd.DataFrame(index=df.index), unseen_count
    return pd.concat(pieces, axis=1), unseen_count


def ridge_predict(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_test: pd.DataFrame,
    alpha: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    means = x_train.mean(axis=0)
    stds = x_train.std(axis=0).replace(0, 1).fillna(1)
    xtr = ((x_train - means) / stds).fillna(0).to_numpy(dtype=float)
    xte = ((x_test - means) / stds).fillna(0).to_numpy(dtype=float)
    xtr = np.column_stack([np.ones(len(xtr)), xtr])
    xte = np.column_stack([np.ones(len(xte)), xte])
    y = pd.to_numeric(y_train, errors="coerce").to_numpy(dtype=float)
    penalty = np.eye(xtr.shape[1]) * alpha
    penalty[0, 0] = 0.0
    beta = np.linalg.pinv(xtr.T @ xtr + penalty) @ xtr.T @ y
    return xte @ beta, beta, stds.to_numpy(dtype=float)


def expanding_monthly_oos_predictions(
    frame: pd.DataFrame,
    outcome_col: str,
    baseline_cols: list[str],
    feature_cols: list[str],
    cfg: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    stat = cfg.get("statistical", {})
    alpha = safe_float(stat.get("ridge_alpha", 1.0), 1.0)
    min_train = int(cfg.get("walk_forward", {}).get("minimum_train_observations", 252))
    work = frame.copy()
    work["decision_ts"] = pd.to_datetime(work["decision_timestamp_utc"], utc=True, errors="coerce")
    work["test_month"] = work["decision_ts"].dt.tz_convert(ET).dt.to_period("M").astype(str)
    y = pd.to_numeric(work[outcome_col], errors="coerce")
    baseline_cols = list(dict.fromkeys(baseline_cols))
    feature_cols = list(dict.fromkeys(feature_cols))
    augmented_cols = list(dict.fromkeys(baseline_cols + feature_cols))
    keep = y.notna()
    for col in list(dict.fromkeys(baseline_cols + feature_cols)):
        if col not in work.columns:
            keep &= False
            continue
        series = work[col]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().mean() >= 0.8:
            keep &= numeric.notna()
    work = work.loc[keep].reset_index(drop=True)
    y = y.loc[keep].reset_index(drop=True)
    months = sorted(work["test_month"].dropna().unique().tolist())
    pred_rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    effect_coefs: list[float] = []
    for month in months:
        train_idx = work.index[work["test_month"] < month].to_numpy()
        test_idx = work.index[work["test_month"] == month].to_numpy()
        if len(train_idx) < min_train or len(test_idx) == 0:
            fold_rows.append({
                "test_month": month,
                "sample_count_train": len(train_idx),
                "sample_count_oos": len(test_idx),
                "fold_status": "insufficient_train",
            })
            continue
        base_encoder = fit_feature_encoder(work.iloc[train_idx], baseline_cols)
        aug_encoder = fit_feature_encoder(work.iloc[train_idx], augmented_cols)
        feature_encoder = fit_feature_encoder(work.iloc[train_idx], feature_cols)
        x_base_train, base_unseen_train = transform_feature_encoder(work.iloc[train_idx], base_encoder)
        x_base_test, base_unseen_test = transform_feature_encoder(work.iloc[test_idx], base_encoder)
        x_aug_train, aug_unseen_train = transform_feature_encoder(work.iloc[train_idx], aug_encoder)
        x_aug_test, aug_unseen_test = transform_feature_encoder(work.iloc[test_idx], aug_encoder)
        x_feature_train, _ = transform_feature_encoder(work.iloc[train_idx], feature_encoder)
        base_pred, _, _ = ridge_predict(x_base_train, y.iloc[train_idx], x_base_test, alpha)
        aug_pred, aug_beta, _ = ridge_predict(x_aug_train, y.iloc[train_idx], x_aug_test, alpha)
        hist_mean = float(y.iloc[train_idx].mean())
        feature_dummy_cols = x_feature_train.columns.tolist()
        aug_cols = x_aug_train.columns.tolist()
        coef_values = [aug_beta[aug_cols.index(c) + 1] for c in feature_dummy_cols if c in aug_cols]
        if coef_values:
            effect_coefs.append(float(np.nanmean(coef_values)))
        for idx, bp, ap in zip(test_idx, base_pred, aug_pred):
            pred_rows.append({
                "row_index": int(idx),
                "decision_timestamp_utc": work.loc[idx, "decision_timestamp_utc"],
                "test_month": month,
                "y_true": y.iloc[idx],
                "baseline_pred": bp,
                "augmented_pred": ap,
                "historical_mean_pred": hist_mean,
            })
        fold_rows.append({
            "test_month": month,
            "sample_count_train": len(train_idx),
            "sample_count_oos": len(test_idx),
            "unseen_category_count": base_unseen_train + base_unseen_test + aug_unseen_train + aug_unseen_test,
            "fold_status": "tested",
        })
    return pd.DataFrame(pred_rows), pd.DataFrame(fold_rows), float(np.nanmean(effect_coefs)) if effect_coefs else np.nan


def market_level_paired_walk_forward(
    frame: pd.DataFrame,
    outcome_col: str,
    parent_scope: str,
    model_scope: str,
    model_clock: str,
    baseline_cols: list[str],
    parent_feature_cols: list[str],
    augmented_feature_cols: list[str],
    cfg: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    stat = cfg.get("statistical", {})
    alpha = safe_float(stat.get("ridge_alpha", 1.0), 1.0)
    min_train = int(cfg.get("walk_forward", {}).get("minimum_train_observations", 252))
    work = frame.copy()
    work["decision_ts"] = pd.to_datetime(work["decision_timestamp_utc"], utc=True, errors="coerce")
    work["test_month"] = work["decision_ts"].dt.tz_convert(ET).dt.to_period("M").astype(str)
    parent_cols = list(dict.fromkeys(baseline_cols + parent_feature_cols))
    augmented_cols = list(dict.fromkeys(baseline_cols + augmented_feature_cols))
    required = list(dict.fromkeys(parent_cols + augmented_cols + [outcome_col]))
    for col in required:
        if col not in work.columns:
            work[col] = np.nan
    keep = pd.to_numeric(work[outcome_col], errors="coerce").notna()
    for col in parent_cols + augmented_cols:
        keep &= pd.to_numeric(work[col], errors="coerce").notna()
    work = work.loc[keep].reset_index(drop=True)
    y = pd.to_numeric(work[outcome_col], errors="coerce").reset_index(drop=True)
    pred_rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    coef_rows: list[dict[str, Any]] = []
    for month in sorted(work["test_month"].dropna().unique().tolist()):
        train_idx = work.index[work["test_month"] < month].to_numpy()
        test_idx = work.index[work["test_month"] == month].to_numpy()
        if len(train_idx) < min_train or len(test_idx) == 0:
            fold_rows.append({
                "target_market": work["target_market"].iloc[0] if len(work) else "",
                "model_scope": model_scope,
                "parent_model_scope": parent_scope,
                "model_clock": model_clock,
                "outcome": outcome_col,
                "test_month": month,
                "sample_count_train": len(train_idx),
                "sample_count_oos": len(test_idx),
                "fold_status": "insufficient_train",
            })
            continue
        parent_encoder = fit_feature_encoder(work.iloc[train_idx], parent_cols)
        aug_encoder = fit_feature_encoder(work.iloc[train_idx], augmented_cols)
        x_parent_train, parent_unseen_train = transform_feature_encoder(work.iloc[train_idx], parent_encoder)
        x_parent_test, parent_unseen_test = transform_feature_encoder(work.iloc[test_idx], parent_encoder)
        x_aug_train, aug_unseen_train = transform_feature_encoder(work.iloc[train_idx], aug_encoder)
        x_aug_test, aug_unseen_test = transform_feature_encoder(work.iloc[test_idx], aug_encoder)
        parent_pred, _, _ = ridge_predict(x_parent_train, y.iloc[train_idx], x_parent_test, alpha)
        aug_pred, aug_beta, _ = ridge_predict(x_aug_train, y.iloc[train_idx], x_aug_test, alpha)
        hist_mean = float(y.iloc[train_idx].mean())
        aug_encoded_cols = x_aug_train.columns.tolist()
        for feature_name, beta in zip(["intercept"] + aug_encoded_cols, aug_beta):
            if feature_name == "intercept":
                continue
            coef_rows.append({
                "target_market": work["target_market"].iloc[0],
                "model_scope": model_scope,
                "parent_model_scope": parent_scope,
                "model_clock": model_clock,
                "outcome": outcome_col,
                "test_month": month,
                "feature_name": feature_name,
                "standardized_coefficient": float(beta),
                "coefficient_sign": int(np.sign(beta)) if pd.notna(beta) else 0,
                "sample_count_train": len(train_idx),
                "sample_count_oos": len(test_idx),
                "fold_status": "tested",
            })
        for idx, pp, ap in zip(test_idx, parent_pred, aug_pred):
            pred_rows.append({
                "target_market": work.loc[idx, "target_market"],
                "model_scope": model_scope,
                "parent_model_scope": parent_scope,
                "outcome": outcome_col,
                "model_clock": model_clock,
                "row_index": int(idx),
                "decision_timestamp_utc": work.loc[idx, "decision_timestamp_utc"],
                "test_month": month,
                "y_true": y.iloc[idx],
                "parent_pred": pp,
                "augmented_pred": ap,
                "historical_mean_pred": hist_mean,
            })
        fold_rows.append({
            "target_market": work["target_market"].iloc[0],
            "model_scope": model_scope,
            "parent_model_scope": parent_scope,
            "model_clock": model_clock,
            "outcome": outcome_col,
            "test_month": month,
            "sample_count_train": len(train_idx),
            "sample_count_oos": len(test_idx),
            "unseen_category_count": parent_unseen_train + parent_unseen_test + aug_unseen_train + aug_unseen_test,
            "fold_status": "tested",
        })
    return pd.DataFrame(pred_rows), pd.DataFrame(fold_rows), pd.DataFrame(coef_rows)


def moving_block_bootstrap_delta_ci(
    augmented_errors: np.ndarray,
    baseline_errors: np.ndarray,
    block_length: int,
    iterations: int,
    seed: int,
) -> tuple[float, float, float]:
    n = len(augmented_errors)
    if n == 0:
        return np.nan, np.nan, 1.0
    block_length = max(1, min(block_length, n))
    rng = np.random.default_rng(seed)
    deltas: list[float] = []
    starts = np.arange(0, n)
    d = augmented_errors - baseline_errors
    for _ in range(max(1, iterations)):
        picked: list[int] = []
        while len(picked) < n:
            start = int(rng.choice(starts))
            picked.extend([(start + j) % n for j in range(block_length)])
        idx = np.array(picked[:n])
        deltas.append(float(np.mean(d[idx])))
    observed = float(np.mean(d))
    d_null = d - observed
    null_means: list[float] = []
    for _ in range(max(1, iterations)):
        picked = []
        while len(picked) < n:
            start = int(rng.choice(starts))
            picked.extend([(start + j) % n for j in range(block_length)])
        idx = np.array(picked[:n])
        null_means.append(float(np.mean(d_null[idx])))
    raw_p = float(np.mean(np.abs(null_means) >= abs(observed)))
    return float(np.quantile(deltas, 0.025)), float(np.quantile(deltas, 0.975)), raw_p if pd.notna(raw_p) else 1.0


def evidence_verdict_from_oos(row: dict[str, Any], execution_gate: str) -> str:
    if execution_gate != "passed":
        return execution_gate
    delta = safe_float(row.get("delta_oos_mse_vs_baseline"))
    ci_high = safe_float(row.get("bootstrap_delta_mse_ci_high"))
    r2_base = safe_float(row.get("oos_r2_vs_baseline"))
    pre = safe_float(row.get("subperiod_pre_2023_delta_oos_mse"))
    post = safe_float(row.get("subperiod_2023_onward_delta_oos_mse"))
    if pd.notna(pre) and pd.notna(post) and np.sign(pre) != np.sign(post):
        return "unstable_across_subperiods"
    if pd.notna(delta) and pd.notna(ci_high) and pd.notna(r2_base) and delta < 0 and ci_high < 0 and r2_base > 0:
        return "incremental_predictive_association_found"
    return "no_incremental_value"


def run_oos_comparison(
    panel: pd.DataFrame,
    *,
    module: str,
    test_family: str,
    feature_sets: dict[str, list[str]],
    outcomes: list[str],
    baseline_cols: list[str],
    cfg: dict[str, Any],
    min_oos_rows: int,
    min_test_months: int,
    primary_or_robustness: str = "primary",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    result_cols = [
        "module",
        "test_family",
        "feature_family",
        "feature_name",
        "target_market",
        "outcome",
        "primary_or_robustness",
        "sample_count_train",
        "sample_count_oos",
        "test_month_count",
        "oos_mse",
        "oos_mae",
        "oos_r2_vs_historical_mean",
        "oos_r2_vs_baseline",
        "delta_oos_mse_vs_baseline",
        "delta_oos_mae_vs_baseline",
        "effect_size_per_1sd_feature",
        "bootstrap_delta_mse_ci_low",
        "bootstrap_delta_mse_ci_high",
        "bootstrap_block_length",
        "bootstrap_iterations",
        "random_seed",
        "raw_p_value",
        "p_value_status",
        "adjusted_p_value",
        "multiple_testing_method",
        "subperiod_pre_2023_delta_oos_mse",
        "subperiod_2023_onward_delta_oos_mse",
        "research_execution_gate",
        "evidence_engine",
        "evidence_verdict",
    ]
    fold_rows: list[pd.DataFrame] = []
    rows: list[dict[str, Any]] = []
    if panel.empty:
        return pd.DataFrame(columns=result_cols), pd.DataFrame(columns=["module", "target_market", "feature_name", "outcome", "test_month", "sample_count_train", "sample_count_oos", "fold_status"])
    stat = cfg.get("statistical", {})
    block_len = int(stat.get("bootstrap_block_length", 5))
    iterations = int(stat.get("bootstrap_iterations", 1000))
    seed = int(stat.get("random_seed", 42))
    for target, target_panel in panel.groupby("target_market"):
        for outcome_col in outcomes:
            if outcome_col not in target_panel.columns:
                continue
            for feature_name, feature_cols in feature_sets.items():
                required = list(dict.fromkeys(["decision_timestamp_utc", outcome_col] + baseline_cols + feature_cols))
                if not set(required).issubset(set(target_panel.columns)):
                    missing = sorted(set(required) - set(target_panel.columns))
                    rows.append({
                        "module": module,
                        "test_family": test_family,
                        "feature_family": module,
                        "feature_name": feature_name,
                        "target_market": target,
                        "outcome": outcome_col,
                        "primary_or_robustness": primary_or_robustness,
                        "sample_count_train": 0,
                        "sample_count_oos": 0,
                        "test_month_count": 0,
                        "evidence_engine": "expanding_window_oos_ridge",
                        "research_execution_gate": "insufficient_data",
                        "evidence_verdict": "insufficient_data",
                        "p_value_status": "not_run",
                        "availability_failure_reason": "missing_columns:" + ",".join(missing),
                    })
                    continue
                preds, folds, effect = expanding_monthly_oos_predictions(target_panel[required].copy(), outcome_col, baseline_cols, feature_cols, cfg)
                if not folds.empty:
                    f = folds.copy()
                    f.insert(0, "outcome", outcome_col)
                    f.insert(0, "feature_name", feature_name)
                    f.insert(0, "target_market", target)
                    f.insert(0, "module", module)
                    fold_rows.append(f)
                tested = folds[folds.get("fold_status", pd.Series(dtype=str)).eq("tested")] if not folds.empty else pd.DataFrame()
                oos_n = len(preds)
                test_month_count = int(tested["test_month"].nunique()) if not tested.empty else 0
                train_n = int(tested["sample_count_train"].median()) if not tested.empty else 0
                if preds.empty:
                    mse = mae = r2_hist = r2_base = delta_mse = delta_mae = np.nan
                    ci_low = ci_high = np.nan
                    raw_p = np.nan
                else:
                    y = pd.to_numeric(preds["y_true"], errors="coerce").to_numpy(dtype=float)
                    aug = pd.to_numeric(preds["augmented_pred"], errors="coerce").to_numpy(dtype=float)
                    base = pd.to_numeric(preds["baseline_pred"], errors="coerce").to_numpy(dtype=float)
                    hist = pd.to_numeric(preds["historical_mean_pred"], errors="coerce").to_numpy(dtype=float)
                    aug_err = (y - aug) ** 2
                    base_err = (y - base) ** 2
                    hist_err = (y - hist) ** 2
                    mse = float(np.mean(aug_err))
                    mae = float(np.mean(np.abs(y - aug)))
                    base_mse = float(np.mean(base_err))
                    base_mae = float(np.mean(np.abs(y - base)))
                    hist_mse = float(np.mean(hist_err))
                    r2_hist = 1.0 - mse / hist_mse if hist_mse > 0 else np.nan
                    r2_base = 1.0 - mse / base_mse if base_mse > 0 else np.nan
                    delta_mse = mse - base_mse
                    delta_mae = mae - base_mae
                    ci_low, ci_high, raw_p = moving_block_bootstrap_delta_ci(aug_err, base_err, block_len, iterations, seed)
                pre_delta = np.nan
                post_delta = np.nan
                if not preds.empty:
                    pred_work = preds.copy()
                    pred_work["year"] = pd.to_datetime(pred_work["decision_timestamp_utc"], utc=True, errors="coerce").dt.year
                    for label, mask in [("pre", pred_work["year"] < 2023), ("post", pred_work["year"] >= 2023)]:
                        sub = pred_work[mask]
                        if not sub.empty:
                            sub_y = pd.to_numeric(sub["y_true"], errors="coerce")
                            sub_aug = pd.to_numeric(sub["augmented_pred"], errors="coerce")
                            sub_base = pd.to_numeric(sub["baseline_pred"], errors="coerce")
                            sub_delta = float(np.mean((sub_y - sub_aug) ** 2) - np.mean((sub_y - sub_base) ** 2))
                            if label == "pre":
                                pre_delta = sub_delta
                            else:
                                post_delta = sub_delta
                execution_gate = "passed" if oos_n >= min_oos_rows and test_month_count >= min_test_months and pd.notna(ci_low) and pd.notna(ci_high) else "insufficient_data"
                if oos_n == 0:
                    p_value_status = "not_run"
                elif execution_gate != "passed":
                    p_value_status = "exploratory_below_minimum_sample"
                else:
                    p_value_status = "valid_null_centered_bootstrap" if pd.notna(raw_p) else "not_used_primary_ci_based"
                row = {
                    "module": module,
                    "test_family": test_family,
                    "feature_family": module,
                    "feature_name": feature_name,
                    "target_market": target,
                    "outcome": outcome_col,
                    "primary_or_robustness": primary_or_robustness,
                    "sample_count_train": train_n,
                    "sample_count_oos": oos_n,
                    "test_month_count": test_month_count,
                    "oos_mse": mse,
                    "oos_mae": mae,
                    "oos_r2_vs_historical_mean": r2_hist,
                    "oos_r2_vs_baseline": r2_base,
                    "delta_oos_mse_vs_baseline": delta_mse,
                    "delta_oos_mae_vs_baseline": delta_mae,
                    "effect_size_per_1sd_feature": effect,
                    "bootstrap_delta_mse_ci_low": ci_low,
                    "bootstrap_delta_mse_ci_high": ci_high,
                    "bootstrap_block_length": block_len,
                    "bootstrap_iterations": iterations,
                    "random_seed": seed,
                    "raw_p_value": raw_p,
                    "p_value_status": p_value_status,
                    "adjusted_p_value": np.nan,
                    "multiple_testing_method": "benjamini_hochberg",
                    "subperiod_pre_2023_delta_oos_mse": pre_delta,
                    "subperiod_2023_onward_delta_oos_mse": post_delta,
                    "research_execution_gate": execution_gate,
                    "evidence_engine": "expanding_window_oos_ridge",
                }
                row["evidence_verdict"] = evidence_verdict_from_oos(row, execution_gate)
                rows.append(row)
    result = pd.DataFrame(rows)
    if result.empty:
        result = pd.DataFrame(columns=result_cols)
    elif "raw_p_value" in result.columns:
        valid = result["p_value_status"].astype(str).eq("valid_null_centered_bootstrap") if "p_value_status" in result.columns else pd.Series([False] * len(result))
        result["adjusted_p_value"] = np.nan
        if valid.any():
            result.loc[valid, "adjusted_p_value"] = benjamini_hochberg(pd.to_numeric(result.loc[valid, "raw_p_value"], errors="coerce").fillna(1.0).tolist())
    result = ensure_columns(result, result_cols)
    fold_audit = pd.concat(fold_rows, ignore_index=True) if fold_rows else pd.DataFrame(columns=["module", "target_market", "feature_name", "outcome", "test_month", "sample_count_train", "sample_count_oos", "fold_status"])
    return result, fold_audit


def build_expiry_group_contrast_panel(panel: pd.DataFrame, event_group: str, reference_group: str, feature_family: str) -> pd.DataFrame:
    if panel.empty or "comparison_group" not in panel.columns:
        return pd.DataFrame()
    work = panel[panel["comparison_group"].astype(str).isin([event_group, reference_group])].copy()
    if work.empty:
        return work
    prefix = "dealer_gamma_expiry_conditioned" if feature_family == "DealerGammaExpiryConditioned" else "expiry_calendar"
    work["event_group"] = event_group
    work["reference_group"] = reference_group
    work["event_group_indicator"] = work["comparison_group"].astype(str).eq(event_group).astype(float)
    work["contrast_id"] = f"{prefix}__{event_group}_vs_{reference_group}"
    return work


def run_expiry_group_contrast_oos(
    panel: pd.DataFrame,
    *,
    module: str,
    feature_family: str,
    feature_name: str,
    feature_cols: list[str],
    outcomes: list[str],
    baseline_cols: list[str],
    cfg: dict[str, Any],
    min_oos_rows_per_group: int,
    min_test_months_per_group: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    event_groups = ["triple_witching", "quarterly_expiry_non_triple", "monthly_expiry_non_quarterly"]
    reference_group = "non_expiry_friday"
    forbidden_baseline = {"monthly_expiry_flag", "quarterly_expiry_flag", "triple_witching_flag", "comparison_group", "event_group_indicator", "weekday"}
    baseline_cols = [c for c in baseline_cols if c not in forbidden_baseline]
    result_rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    pred_rows: list[dict[str, Any]] = []
    stat = cfg.get("statistical", {})
    block_len = int(stat.get("bootstrap_block_length", 5))
    iterations = int(stat.get("bootstrap_iterations", 1000))
    seed = int(stat.get("random_seed", 42))
    alpha = safe_float(stat.get("ridge_alpha", 1.0), 1.0)
    min_train = int(cfg.get("walk_forward", {}).get("minimum_train_observations", 252))
    if panel.empty:
        return pd.DataFrame(columns=EXPIRY_GROUP_CONTRAST_RESULT_COLUMNS), pd.DataFrame(), pd.DataFrame()
    for event_group in event_groups:
        contrast = build_expiry_group_contrast_panel(panel, event_group, reference_group, feature_family)
        if contrast.empty:
            continue
        for target, target_panel in contrast.groupby("target_market"):
            for outcome in outcomes:
                required = list(dict.fromkeys(["decision_timestamp_utc", "comparison_group", "event_group_indicator", outcome] + baseline_cols + feature_cols))
                if not set(required).issubset(target_panel.columns):
                    result_rows.append({
                        "module": module,
                        "feature_family": feature_family,
                        "contrast_id": f"{feature_family.lower()}__{event_group}_vs_{reference_group}",
                        "target_market": target,
                        "event_group": event_group,
                        "reference_group": reference_group,
                        "outcome": outcome,
                        "feature_name": feature_name,
                        "research_execution_gate": "insufficient_data",
                        "evidence_verdict": "insufficient_data",
                    })
                    continue
                work = target_panel[required + ["contrast_id", "event_group", "reference_group"]].copy()
                work["decision_ts"] = pd.to_datetime(work["decision_timestamp_utc"], utc=True, errors="coerce")
                work["test_month"] = work["decision_ts"].dt.tz_convert(ET).dt.to_period("M").astype(str)
                keep = work["decision_ts"].notna() & pd.to_numeric(work[outcome], errors="coerce").notna()
                for col in list(dict.fromkeys(baseline_cols + feature_cols)):
                    numeric = pd.to_numeric(work[col], errors="coerce")
                    if numeric.notna().mean() >= 0.8:
                        keep &= numeric.notna()
                work = work.loc[keep].sort_values("decision_ts").reset_index(drop=True)
                preds: list[dict[str, Any]] = []
                months = sorted(work["test_month"].dropna().unique().tolist())
                for month in months:
                    train = work[work["test_month"] < month].copy()
                    test = work[work["test_month"].eq(month)].copy()
                    status = "tested"
                    train_groups = set(train["comparison_group"].astype(str))
                    test_groups = set(test["comparison_group"].astype(str))
                    if len(train) < min_train:
                        status = "insufficient_train"
                    elif event_group not in train_groups:
                        status = "missing_event_group_in_train"
                    elif reference_group not in train_groups:
                        status = "missing_reference_group_in_train"
                    elif event_group not in test_groups:
                        status = "missing_event_group_in_test"
                    elif reference_group not in test_groups:
                        status = "missing_reference_group_in_test"
                    fold_rows.append({
                        "module": module,
                        "feature_family": feature_family,
                        "contrast_id": work["contrast_id"].iloc[0] if not work.empty else "",
                        "target_market": target,
                        "event_group": event_group,
                        "reference_group": reference_group,
                        "outcome": outcome,
                        "feature_name": feature_name,
                        "test_month": month,
                        "sample_count_train": len(train),
                        "sample_count_oos": len(test) if status == "tested" else 0,
                        "fold_status": status,
                    })
                    if status != "tested":
                        continue
                    base_encoder = fit_feature_encoder(train, baseline_cols)
                    aug_encoder = fit_feature_encoder(train, list(dict.fromkeys(baseline_cols + feature_cols)))
                    x_base_train, _ = transform_feature_encoder(train, base_encoder)
                    x_base_test, _ = transform_feature_encoder(test, base_encoder)
                    x_aug_train, _ = transform_feature_encoder(train, aug_encoder)
                    x_aug_test, _ = transform_feature_encoder(test, aug_encoder)
                    y_train = pd.to_numeric(train[outcome], errors="coerce")
                    y_test = pd.to_numeric(test[outcome], errors="coerce")
                    base_pred, _, _ = ridge_predict(x_base_train, y_train, x_base_test, alpha)
                    aug_pred, _, _ = ridge_predict(x_aug_train, y_train, x_aug_test, alpha)
                    for (_, trow), bp, ap, yv in zip(test.iterrows(), base_pred, aug_pred, y_test):
                        pred = {
                            "module": module,
                            "feature_family": feature_family,
                            "contrast_id": trow["contrast_id"],
                            "target_market": target,
                            "event_group": event_group,
                            "reference_group": reference_group,
                            "comparison_group": trow["comparison_group"],
                            "outcome": outcome,
                            "feature_name": feature_name,
                            "decision_timestamp_utc": trow["decision_timestamp_utc"],
                            "test_month": month,
                            "y_true": yv,
                            "baseline_pred": bp,
                            "augmented_pred": ap,
                        }
                        preds.append(pred)
                        pred_rows.append(pred)
                pred_df = pd.DataFrame(preds)
                if pred_df.empty:
                    mse = mae = r2_base = delta_mse = ci_low = ci_high = np.nan
                    event_n = ref_n = event_months = ref_months = 0
                    train_n = 0
                else:
                    y = pd.to_numeric(pred_df["y_true"], errors="coerce").to_numpy(dtype=float)
                    aug = pd.to_numeric(pred_df["augmented_pred"], errors="coerce").to_numpy(dtype=float)
                    base = pd.to_numeric(pred_df["baseline_pred"], errors="coerce").to_numpy(dtype=float)
                    aug_err = (y - aug) ** 2
                    base_err = (y - base) ** 2
                    mse = float(np.mean(aug_err))
                    mae = float(np.mean(np.abs(y - aug)))
                    base_mse = float(np.mean(base_err))
                    r2_base = 1.0 - mse / base_mse if base_mse > 0 else np.nan
                    delta_mse = mse - base_mse
                    ci_low, ci_high, _ = moving_block_bootstrap_delta_ci(aug_err, base_err, block_len, iterations, seed)
                    event_pred = pred_df[pred_df["comparison_group"].astype(str).eq(event_group)]
                    ref_pred = pred_df[pred_df["comparison_group"].astype(str).eq(reference_group)]
                    event_n = len(event_pred)
                    ref_n = len(ref_pred)
                    event_months = int(event_pred["test_month"].nunique()) if not event_pred.empty else 0
                    ref_months = int(ref_pred["test_month"].nunique()) if not ref_pred.empty else 0
                    tested_folds = pd.DataFrame(fold_rows)
                    train_n = int(pd.to_numeric(tested_folds.loc[tested_folds["fold_status"].eq("tested"), "sample_count_train"], errors="coerce").median()) if not tested_folds.empty else 0
                gate = "passed" if event_n >= min_oos_rows_per_group and ref_n >= min_oos_rows_per_group and event_months >= min_test_months_per_group and ref_months >= min_test_months_per_group and pd.notna(ci_low) and pd.notna(ci_high) else "insufficient_data"
                result = {
                    "module": module,
                    "feature_family": feature_family,
                    "contrast_id": f"{feature_family.lower()}__{event_group}_vs_{reference_group}",
                    "target_market": target,
                    "event_group": event_group,
                    "reference_group": reference_group,
                    "outcome": outcome,
                    "feature_name": feature_name,
                    "sample_count_train": train_n,
                    "sample_count_oos": event_n + ref_n,
                    "event_group_oos_row_count": event_n,
                    "reference_group_oos_row_count": ref_n,
                    "event_group_test_month_count": event_months,
                    "reference_group_test_month_count": ref_months,
                    "oos_mse": mse,
                    "oos_mae": mae,
                    "oos_r2_vs_baseline": r2_base,
                    "delta_oos_mse_vs_baseline": delta_mse,
                    "bootstrap_delta_mse_ci_low": ci_low,
                    "bootstrap_delta_mse_ci_high": ci_high,
                    "research_execution_gate": gate,
                    "evidence_verdict": evidence_verdict_from_oos({"delta_oos_mse_vs_baseline": delta_mse, "bootstrap_delta_mse_ci_high": ci_high, "oos_r2_vs_baseline": r2_base}, gate),
                    "baseline_model_version": "expiry_group_contrast_baseline_v1",
                    "baseline_feature_columns": ",".join(baseline_cols),
                    "event_group_definition_source": str(EXPIRY_FRIDAY_CLASSIFICATION_PATH).replace("\\", "/"),
                    "reference_group_definition_source": str(EXPIRY_FRIDAY_CLASSIFICATION_PATH).replace("\\", "/"),
                    "expiry_classification_coverage_status": "validated_classification_universe",
                    "holiday_adjusted_event_excluded_count": int((panel.get("comparison_group", pd.Series(dtype=str)).astype(str) == "holiday_adjusted_expiry_excluded_from_friday_primary").sum()) if not panel.empty else 0,
                    "clean_selected_prediction_count": event_n + ref_n,
                    "coverage_excluded_prediction_count": 0,
                    "selected_invalid_prediction_count": 0,
                    "nonselected_invalid_candidate_count": 0,
                }
                result_rows.append(result)
    return (
        pd.DataFrame(result_rows, columns=EXPIRY_GROUP_CONTRAST_RESULT_COLUMNS),
        pd.DataFrame(fold_rows),
        pd.DataFrame(pred_rows),
    )


def build_expiry_group_contrast_descriptive_oos(predictions: pd.DataFrame) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame(columns=["module", "feature_family", "contrast_id", "target_market", "event_group", "reference_group", "outcome", "event_group_oos_mean", "reference_group_oos_mean", "difference", "bootstrap_ci_low", "bootstrap_ci_high", "evidence_engine"])
    rows = []
    rng = np.random.default_rng(42)
    for keys, group in predictions.groupby(["module", "feature_family", "contrast_id", "target_market", "event_group", "reference_group", "outcome"], dropna=False):
        module, family, contrast_id, target, event_group, reference_group, outcome = keys
        event = pd.to_numeric(group.loc[group["comparison_group"].astype(str).eq(str(event_group)), "y_true"], errors="coerce").dropna().to_numpy()
        ref = pd.to_numeric(group.loc[group["comparison_group"].astype(str).eq(str(reference_group)), "y_true"], errors="coerce").dropna().to_numpy()
        if len(event) == 0 or len(ref) == 0:
            diff = low = high = np.nan
        else:
            diff = float(np.mean(event) - np.mean(ref))
            samples = []
            for _ in range(500):
                samples.append(float(np.mean(rng.choice(event, len(event), replace=True)) - np.mean(rng.choice(ref, len(ref), replace=True))))
            low, high = float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))
        rows.append({
            "module": module,
            "feature_family": family,
            "contrast_id": contrast_id,
            "target_market": target,
            "event_group": event_group,
            "reference_group": reference_group,
            "outcome": outcome,
            "event_group_oos_mean": float(np.mean(event)) if len(event) else np.nan,
            "reference_group_oos_mean": float(np.mean(ref)) if len(ref) else np.nan,
            "difference": diff,
            "bootstrap_ci_low": low,
            "bootstrap_ci_high": high,
            "evidence_engine": "descriptive_oos_group_mean_difference",
        })
    return pd.DataFrame(rows)


def build_walk_forward_manifest(sample_count: int, cfg: dict[str, Any]) -> dict[str, Any]:
    wf = cfg.get("walk_forward", {})
    minimum = int(wf.get("minimum_train_observations", 252))
    return {
        "method": "expanding_window",
        "random_split_used": False,
        "minimum_train_observations": minimum,
        "sample_count": sample_count,
        "oos_available": sample_count > minimum,
        "test_block": wf.get("test_block", "monthly"),
    }


def build_no_lookahead_audit(feature_join: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    cols = [
        "module",
        "feature_family",
        "target_market",
        "decision_timestamp_utc",
        "feature_as_of_timestamp_utc",
        "effective_available_at_utc",
        "feature_age_hours",
        "no_lookahead_passed",
        "violation_reason",
    ]
    if feature_join.empty:
        return pd.DataFrame(columns=cols), "not_run"
    rows: list[dict[str, Any]] = []
    for _, row in feature_join.iterrows():
        decision_ts = parse_ts(row.get("decision_timestamp_utc"))
        asof_ts = parse_ts(row.get("feature_as_of_timestamp_utc"))
        eff_ts = parse_ts(row.get("effective_available_at_utc"))
        feature_age = safe_float(row.get("feature_age_hours"))
        max_age = safe_float(row.get("max_feature_age_hours", np.nan))
        reasons = []
        if decision_ts is None:
            reasons.append("missing_required_timestamp:decision_timestamp_missing")
        if asof_ts is None:
            reasons.append("missing_required_timestamp:feature_asof_timestamp_missing")
        if eff_ts is None:
            reasons.append("missing_required_timestamp:effective_available_timestamp_missing")
        if pd.isna(feature_age):
            reasons.append("feature_age_missing")
        if decision_ts is not None and asof_ts is not None and asof_ts > decision_ts:
            reasons.append("feature_asof_after_decision")
        if decision_ts is not None and eff_ts is not None and eff_ts > decision_ts:
            reasons.append("effective_after_decision")
        if pd.notna(max_age) and pd.notna(feature_age) and feature_age > max_age:
            reasons.append("feature_age_exceeds_maximum")
        rows.append({
            "module": row.get("module", ""),
            "feature_family": row.get("feature_family", ""),
            "target_market": row.get("target_market", ""),
            "decision_timestamp_utc": row.get("decision_timestamp_utc", ""),
            "feature_as_of_timestamp_utc": row.get("feature_as_of_timestamp_utc", ""),
            "effective_available_at_utc": row.get("effective_available_at_utc", ""),
            "feature_age_hours": row.get("feature_age_hours", np.nan),
            "no_lookahead_passed": len(reasons) == 0,
            "violation_reason": ";".join(reasons),
        })
    audit = pd.DataFrame(rows, columns=cols)
    return audit, "passed" if bool(audit["no_lookahead_passed"].all()) else "failed"


def audit_source_feature_candidates(
    raw_source_frame: pd.DataFrame,
    module: str,
    feature_family: str,
    target_market: str,
    decision_timestamp_utc: Any,
    max_feature_age_hours: float,
    schema_mapping: dict[str, str],
    strict_quality_policy: dict[str, Any] | None = None,
) -> pd.DataFrame:
    decision_ts = parse_ts(decision_timestamp_utc)
    policy = strict_quality_policy or {}
    source_path = str(schema_mapping.get("source_path_or_provider", ""))
    if raw_source_frame.empty:
        return pd.DataFrame(columns=SOURCE_FEATURE_CANDIDATE_AUDIT_COLUMNS)
    rows: list[dict[str, Any]] = []
    target_col = schema_mapping.get("target_col", "")
    asof_col = schema_mapping.get("feature_as_of_col", "")
    eff_col = schema_mapping.get("effective_available_col", "")
    quality_col = schema_mapping.get("quality_col", "")
    target_alias = str(schema_mapping.get("target_alias", target_market)).upper()
    required_missing = [name for name, col in [("target", target_col), ("feature_asof", asof_col), ("effective_available", eff_col)] if not col or col not in raw_source_frame.columns]
    allowed_quality = {str(v).lower() for v in policy.get("allowed_quality", ["medium", "high", "true", "1", "yes", "unknown", ""])}
    if required_missing:
        for idx, _ in raw_source_frame.iterrows():
            rows.append({
                "module": module,
                "feature_family": feature_family,
                "target_market": target_market,
                "decision_timestamp_utc": decision_timestamp_utc,
                "source_path_or_provider": source_path,
                "source_row_identifier": str(idx),
                "source_row_hash_or_index": str(idx),
                "candidate_rank_before_selection": "",
                "feature_as_of_timestamp_utc": "",
                "effective_available_at_utc": "",
                "feature_age_hours": np.nan,
                "quality_value": "",
                "quality_policy": ",".join(sorted(allowed_quality)),
                "target_match_status": "unknown",
                "timestamp_status": "required_schema_missing",
                "age_status": "unknown",
                "quality_status": "unknown",
                "candidate_eligibility_status": "excluded",
                "candidate_exclusion_reason": "required_schema_missing:" + ",".join(required_missing),
                "selected_for_panel": False,
                "selected_for_model": False,
                "selection_reason": "required_schema_missing",
                "clean_replacement_available": False,
            })
        return pd.DataFrame(rows, columns=SOURCE_FEATURE_CANDIDATE_AUDIT_COLUMNS)
    work = raw_source_frame.copy()
    for idx, row in work.iterrows():
        raw_target = str(row.get(target_col, "")).upper()
        target_match = raw_target == target_alias
        asof_ts = parse_ts(row.get(asof_col))
        eff_ts = parse_ts(row.get(eff_col))
        quality_value = str(row.get(quality_col, "unknown")).lower() if quality_col and quality_col in row.index else "unknown"
        reasons = []
        timestamp_status = "valid"
        if not target_match:
            reasons.append("target_mismatch")
        if asof_ts is None:
            reasons.append("feature_asof_timestamp_missing")
            timestamp_status = "missing"
        if eff_ts is None:
            reasons.append("effective_available_timestamp_missing")
            timestamp_status = "missing"
        if decision_ts is not None and asof_ts is not None and asof_ts > decision_ts:
            reasons.append("feature_asof_after_decision")
            timestamp_status = "future"
        if decision_ts is not None and eff_ts is not None and eff_ts > decision_ts:
            reasons.append("effective_after_decision")
            timestamp_status = "future"
        age_hours = (decision_ts - eff_ts).total_seconds() / 3600 if decision_ts is not None and eff_ts is not None else np.nan
        age_status = "valid"
        if pd.isna(age_hours):
            reasons.append("feature_age_missing")
            age_status = "missing"
        elif age_hours > max_feature_age_hours:
            reasons.append("feature_age_exceeds_maximum")
            age_status = "too_old"
        quality_status = "valid"
        if quality_value not in allowed_quality:
            reasons.append("quality_below_required")
            quality_status = "invalid"
        eligible = len(reasons) == 0
        rows.append({
            "module": module,
            "feature_family": feature_family,
            "target_market": target_market,
            "decision_timestamp_utc": decision_timestamp_utc,
            "source_path_or_provider": source_path,
            "source_row_identifier": str(row.get(schema_mapping.get("row_id_col", ""), idx)) if schema_mapping.get("row_id_col", "") in row.index else str(idx),
            "source_row_hash_or_index": str(idx),
            "candidate_rank_before_selection": "",
            "feature_as_of_timestamp_utc": asof_ts.isoformat() if asof_ts is not None else "",
            "effective_available_at_utc": eff_ts.isoformat() if eff_ts is not None else "",
            "feature_age_hours": round(age_hours, 4) if pd.notna(age_hours) else np.nan,
            "quality_value": quality_value,
            "quality_policy": ",".join(sorted(allowed_quality)),
            "target_match_status": "matched" if target_match else "target_mismatch",
            "timestamp_status": timestamp_status,
            "age_status": age_status,
            "quality_status": quality_status,
            "candidate_eligibility_status": "eligible" if eligible else "excluded",
            "candidate_exclusion_reason": ";".join(reasons),
            "selected_for_panel": False,
            "selected_for_model": False,
            "selection_reason": "",
            "clean_replacement_available": False,
        })
    audit = pd.DataFrame(rows, columns=SOURCE_FEATURE_CANDIDATE_AUDIT_COLUMNS)
    eligible = audit[audit["candidate_eligibility_status"].eq("eligible")].copy()
    if not eligible.empty:
        eligible["effective_sort"] = pd.to_datetime(eligible["effective_available_at_utc"], utc=True, errors="coerce")
        selected_idx = eligible.sort_values("effective_sort").index[-1]
        audit.loc[selected_idx, "selected_for_panel"] = True
        audit.loc[selected_idx, "selected_for_model"] = True
        audit.loc[selected_idx, "selection_reason"] = "latest_clean_eligible_candidate"
        audit.loc[:, "clean_replacement_available"] = True
        audit.loc[:, "candidate_rank_before_selection"] = [str(i) for i in range(1, len(audit) + 1)]
    return audit


def summarize_source_feature_candidate_audit(candidate_audit: pd.DataFrame) -> pd.DataFrame:
    if candidate_audit.empty:
        return pd.DataFrame(columns=SOURCE_FEATURE_CANDIDATE_SUMMARY_COLUMNS)
    rows: list[dict[str, Any]] = []
    for keys, group in candidate_audit.groupby(["module", "feature_family", "target_market", "decision_timestamp_utc"], dropna=False):
        module, family, target, decision_ts = keys
        reasons = group["candidate_exclusion_reason"].astype(str)
        selected = group[group["selected_for_panel"].astype(bool)]
        clean_available = bool(group["candidate_eligibility_status"].eq("eligible").any())
        unavailable_reason = ""
        availability_state = "candidate_available_clean" if clean_available and reasons.astype(str).eq("").all() else "candidate_available_with_nonselected_invalid_rows" if clean_available else "coverage_gap_or_no_candidate"
        if selected.empty and not clean_available and not group.empty:
            unavailable_reason = ";".join(sorted(set(";".join(reasons.tolist()).split(";")) - {""}))
            if reasons.str.contains("required_schema_missing", regex=False).any():
                availability_state = "source_schema_invalid"
            elif reasons.str.contains("timestamp_missing|feature_age_missing", regex=True).any():
                availability_state = "selected_candidate_invalid"
            elif reasons.str.contains("feature_age_exceeds_maximum", regex=False).any():
                availability_state = "coverage_gap_or_no_candidate"
        valid_eff = pd.to_datetime(group["effective_available_at_utc"], utc=True, errors="coerce")
        decision_ts = parse_ts(decision_ts)
        if not clean_available and decision_ts is not None and valid_eff.notna().any() and decision_ts < valid_eff.min():
            availability_state = "coverage_not_started"
            unavailable_reason = "coverage_not_started"
        gate = "evaluate" if clean_available else ("data_quality_blocked" if availability_state in {"selected_candidate_invalid", "source_schema_invalid"} else "insufficient_data")
        rows.append({
            "module": module,
            "feature_family": family,
            "target_market": target,
            "decision_timestamp_utc": decision_ts,
            "raw_candidate_row_count": len(group),
            "eligible_row_count": int(group["candidate_eligibility_status"].eq("eligible").sum()),
            "selected_row_count": int(group["selected_for_panel"].astype(bool).sum()),
            "excluded_future_timestamp_count": int(reasons.str.contains("after_decision", regex=False).sum()),
            "excluded_missing_timestamp_count": int(reasons.str.contains("timestamp_missing|feature_age_missing", regex=True).sum()),
            "excluded_age_count": int(reasons.str.contains("feature_age_exceeds_maximum", regex=False).sum()),
            "excluded_quality_count": int(reasons.str.contains("quality_below_required", regex=False).sum()),
            "excluded_target_mismatch_count": int(reasons.str.contains("target_mismatch", regex=False).sum()),
            "selected_row_strictly_valid": not selected.empty,
            "clean_replacement_available": clean_available,
            "unavailable_reason": unavailable_reason,
            "module_gate_recommendation": gate,
            "decision_level_availability_state": availability_state,
        })
    return pd.DataFrame(rows)


def build_source_feature_candidate_audits(root: Path, daily_outcomes: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    max_age = safe_float(cfg.get("max_feature_age_hours", 96), 96)
    cta, vol = load_feature_history(root)
    dealer = load_dealer_gamma_history(root)
    expiry = load_expiry_calendar(root)
    pieces: list[pd.DataFrame] = []
    decisions = daily_outcomes[["target_market", "decision_timestamp_utc", "decision_date"]].copy() if not daily_outcomes.empty else pd.DataFrame(columns=["target_market", "decision_timestamp_utc", "decision_date"])
    for _, row in decisions.iterrows():
        target = str(row["target_market"]).upper()
        decision_ts = row["decision_timestamp_utc"]
        asset = target_to_feature_asset(target)
        pieces.append(audit_source_feature_candidates(
            cta, "CTA", "CTA", target, decision_ts, max_age,
            {"target_col": "asset", "feature_as_of_col": "feature_as_of_timestamp_utc", "effective_available_col": "effective_available_at_utc", "quality_col": "quality_flag", "target_alias": asset, "source_path_or_provider": "market_bomb_history/cta_proxy_history.csv"},
            {"allowed_quality": ["medium", "high", "ok", "unknown", ""]},
        ))
        vol_asset = asset if asset in {"QQQ", "SPY", "SOXX"} else "QQQ"
        pieces.append(audit_source_feature_candidates(
            vol, "VolControl", "VolControl", target, decision_ts, max_age,
            {"target_col": "asset", "feature_as_of_col": "feature_as_of_timestamp_utc", "effective_available_col": "effective_available_at_utc", "quality_col": "quality_flag", "target_alias": vol_asset, "source_path_or_provider": "market_bomb_history/vol_control_proxy_history.csv"},
            {"allowed_quality": ["medium", "high", "ok", "unknown", ""]},
        ))
        pieces.append(audit_source_feature_candidates(
            dealer, "DealerGamma", "DealerGamma", target, decision_ts, max_age,
            {"target_col": "ticker", "feature_as_of_col": "feature_as_of_timestamp_utc", "effective_available_col": "effective_available_at_utc", "quality_col": "raw_chain_quality", "target_alias": target, "source_path_or_provider": "dealer_gamma_proxy_history.csv"},
            {"allowed_quality": ["medium", "high"]},
        ))
    for _, row in decisions.iterrows():
        day = pd.Timestamp(row.get("decision_date") or pd.to_datetime(row["decision_timestamp_utc"]).date())
        if day.weekday() != 4:
            continue
        target = str(row["target_market"]).upper()
        decision_ts = pd.Timestamp.combine(day.date(), time(9, 30)).tz_localize(ET).tz_convert(UTC).isoformat()
        pieces.append(audit_source_feature_candidates(
            dealer, "DealerGammaExpiryConditioned", "DealerGammaExpiryConditioned", target, decision_ts, max_age,
            {"target_col": "ticker", "feature_as_of_col": "feature_as_of_timestamp_utc", "effective_available_col": "effective_available_at_utc", "quality_col": "raw_chain_quality", "target_alias": target, "source_path_or_provider": "dealer_gamma_proxy_history.csv"},
            {"allowed_quality": ["medium", "high"]},
        ))
    if not expiry.empty:
        exp = expiry.copy()
        exp["target_market"] = "US"
        exp["feature_as_of_timestamp_utc"] = exp.get("calendar_source_effective_at_utc", exp.get("schedule_published_at_utc", ""))
        exp["effective_available_at_utc"] = exp["feature_as_of_timestamp_utc"]
        exp["quality_grade"] = "high"
        for _, row in decisions.iterrows():
            day = pd.Timestamp(row.get("decision_date") or pd.to_datetime(row["decision_timestamp_utc"]).date())
            if day.weekday() != 4:
                continue
            decision_ts = pd.Timestamp.combine(day.date(), time(9, 30)).tz_localize(ET).tz_convert(UTC).isoformat()
            pieces.append(audit_source_feature_candidates(
                exp, "ExpiryCalendar", "ExpiryCalendar", str(row["target_market"]).upper(), decision_ts, 24 * 365 * 20,
                {"target_col": "target_market", "feature_as_of_col": "feature_as_of_timestamp_utc", "effective_available_col": "effective_available_at_utc", "quality_col": "quality_grade", "target_alias": "US", "source_path_or_provider": str(EXPIRY_CALENDAR_PATH).replace("\\", "/")},
                {"allowed_quality": ["high"]},
            ))
    non_empty = [p for p in pieces if p is not None and not p.empty]
    candidate = pd.concat(non_empty, ignore_index=True) if non_empty else pd.DataFrame(columns=SOURCE_FEATURE_CANDIDATE_AUDIT_COLUMNS)
    summary = summarize_source_feature_candidate_audit(candidate)
    return candidate, summary


def build_source_selection_parity_audit(candidate_audit: pd.DataFrame, panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    if candidate_audit.empty:
        return pd.DataFrame(columns=SOURCE_SELECTION_PARITY_COLUMNS)
    selected = candidate_audit[candidate_audit.get("selected_for_panel", pd.Series(dtype=bool)).astype(bool)].copy()
    cta_vol_scope_requirements = {
        "CTA_only": ["CTA"],
        "Vol_only": ["VolControl"],
        "CTA_plus_Vol": ["CTA", "VolControl"],
    }
    cta_panel = panels.get("CTA") if "CTA" in panels else pd.DataFrame()
    if cta_panel is not None and not cta_panel.empty:
        for _, prow in cta_panel.iterrows():
            target = str(prow.get("target_market", ""))
            decision = str(prow.get("decision_timestamp_utc", ""))
            for scope, required_families in cta_vol_scope_requirements.items():
                for family in required_families:
                    candidates = selected[
                        selected["target_market"].astype(str).eq(target)
                        & selected["decision_timestamp_utc"].astype(str).eq(decision)
                        & selected["module"].astype(str).eq(family)
                    ]
                    audit_id = str(candidates.iloc[0].get("source_row_identifier", "")) if not candidates.empty else ""
                    panel_id = str(prow.get("selected_source_row_identifier", "")) if family == str(prow.get("feature_family", "")) else audit_id
                    status = "matched" if audit_id and (panel_id == audit_id) else "unavailable_coverage" if audit_id == "" else "mismatch"
                    rows.append({
                        "module": "CTA_Vol",
                        "feature_family": "CTA_Vol",
                        "model_scope": scope,
                        "target_market": target,
                        "decision_timestamp_utc": decision,
                        "required_source_family": family,
                        "audit_selected_source_row_identifier": audit_id,
                        "panel_selected_source_row_identifier": panel_id,
                        "audit_selected_source_hash_or_index": audit_id,
                        "panel_selected_source_hash_or_index": panel_id,
                        "audit_selected_effective_available_at_utc": str(candidates.iloc[0].get("effective_available_at_utc", "")) if not candidates.empty else "",
                        "panel_selected_effective_available_at_utc": str(prow.get("selected_source_effective_available_at_utc", "")) if family == str(prow.get("feature_family", "")) else (str(candidates.iloc[0].get("effective_available_at_utc", "")) if not candidates.empty else ""),
                        "selection_parity_status": status,
                        "selection_parity_failure_reason": "" if status == "matched" else ("audit_selected_row_missing" if audit_id == "" else "selected_source_row_mismatch"),
                        "scope_gate_recommendation": "evaluate" if status == "matched" else ("insufficient_data" if status == "unavailable_coverage" else "data_quality_blocked"),
                    })
    for module, panel in panels.items():
        if module in {"CTA", "VolControl"}:
            continue
        if panel.empty or "selected_source_row_identifier" not in panel.columns:
            continue
        for _, prow in panel.iterrows():
            target = str(prow.get("target_market", ""))
            decision = str(prow.get("decision_timestamp_utc", ""))
            candidates = selected[
                selected["target_market"].astype(str).eq(target)
                & selected["decision_timestamp_utc"].astype(str).eq(decision)
                & selected["module"].astype(str).isin([module, "CTA", "VolControl"])
            ]
            audit_id = str(candidates.iloc[0].get("source_row_identifier", "")) if not candidates.empty else ""
            panel_id = str(prow.get("selected_source_row_identifier", ""))
            status = "matched" if audit_id == panel_id and panel_id != "" else "not_applicable" if panel_id == "" else "mismatch"
            rows.append({
                "module": module,
                "feature_family": prow.get("feature_family", module),
                "model_scope": prow.get("feature_family", module),
                "target_market": target,
                "decision_timestamp_utc": decision,
                "required_source_family": module,
                "audit_selected_source_row_identifier": audit_id,
                "panel_selected_source_row_identifier": panel_id,
                "audit_selected_source_hash_or_index": audit_id,
                "panel_selected_source_hash_or_index": str(prow.get("selected_source_hash_or_index", panel_id)),
                "audit_selected_effective_available_at_utc": str(candidates.iloc[0].get("effective_available_at_utc", "")) if not candidates.empty else "",
                "panel_selected_effective_available_at_utc": str(prow.get("selected_source_effective_available_at_utc", "")),
                "selection_parity_status": status,
                "selection_parity_failure_reason": "" if status == "matched" else ("audit_selected_row_missing" if audit_id == "" else "selected_source_row_mismatch"),
                "scope_gate_recommendation": "evaluate" if status == "matched" else ("insufficient_data" if status == "not_applicable" else "data_quality_blocked"),
            })
    return pd.DataFrame(rows, columns=SOURCE_SELECTION_PARITY_COLUMNS)


def build_cta_vol_selector_parity_audit(root: Path, cta_panel: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    cta, vol = load_feature_history(root)
    rows: list[dict[str, Any]] = []
    if cta_panel.empty:
        return pd.DataFrame(columns=SOURCE_SELECTION_PARITY_COLUMNS)
    max_age = safe_float(cfg.get("max_feature_age_hours", 96), 96)
    scope_requirements = {
        "CTA_only": ["CTA"],
        "Vol_only": ["VolControl"],
        "CTA_plus_Vol": ["CTA", "VolControl"],
    }
    for _, prow in cta_panel.iterrows():
        target = str(prow.get("target_market", ""))
        asset = target_to_feature_asset(target)
        decision = str(prow.get("decision_timestamp_utc", ""))
        for scope, families in scope_requirements.items():
            for family in families:
                if family == "CTA":
                    audit_sel = select_latest_clean_feature(family="CTA", target=asset, decision_timestamp_utc=decision, target_vol=None, source_rows=cta, max_age_hours=max_age)
                    panel_id = str(prow.get("cta_selected_source_row_identifier", ""))
                    panel_hash = str(prow.get("cta_selected_source_content_hash", ""))
                    panel_eff = str(prow.get("cta_selected_source_effective_available_at_utc", ""))
                    panel_primary = bool(prow.get("cta_primary_eligible", False))
                    panel_status = str(prow.get("cta_selection_status", ""))
                    panel_quality = str(prow.get("cta_selected_source_quality_value", ""))
                else:
                    vol_target = asset if asset in {"QQQ", "SPY", "SOXX"} else "QQQ"
                    audit_sel = select_latest_clean_feature(family="VolControl", target=vol_target, decision_timestamp_utc=decision, target_vol=0.12, source_rows=vol, max_age_hours=max_age)
                    panel_id = str(prow.get("vol_selected_source_row_identifier", ""))
                    panel_hash = str(prow.get("vol_selected_source_content_hash", ""))
                    panel_eff = str(prow.get("vol_selected_source_effective_available_at_utc", ""))
                    panel_primary = bool(prow.get("vol_primary_eligible", False))
                    panel_status = str(prow.get("vol_selection_status", ""))
                    panel_quality = str(prow.get("vol_selected_source_quality_value", ""))
                audit_id = str(audit_sel.get("selected_source_row_identifier", ""))
                audit_hash = str(audit_sel.get("selected_source_content_hash", ""))
                audit_eff = str(audit_sel.get("selected_source_effective_available_at_utc", ""))
                if audit_sel.get("selection_status") == "selected" and panel_primary:
                    matched = audit_id == panel_id and audit_hash == panel_hash and audit_eff == panel_eff
                    status = "matched" if matched else "mismatch"
                    reason = "" if matched else "selected_source_record_mismatch"
                elif audit_sel.get("selection_status") == "selected_invalid" or (panel_id and not panel_primary):
                    status = "selected_invalid"
                    reason = str(audit_sel.get("invalid_reason", "selected_invalid"))
                else:
                    status = "unavailable_coverage"
                    reason = str(audit_sel.get("invalid_reason", "unavailable_coverage"))
                rows.append({
                    "module": "CTA_Vol",
                    "feature_family": "CTA_Vol",
                    "model_scope": scope,
                    "target_market": target,
                    "decision_timestamp_utc": decision,
                    "required_source_family": family,
                    "audit_selected_source_row_identifier": audit_id,
                    "panel_selected_source_row_identifier": panel_id,
                    "audit_selected_source_hash_or_index": audit_hash,
                    "panel_selected_source_hash_or_index": panel_hash,
                    "audit_selected_effective_available_at_utc": audit_eff,
                    "panel_selected_effective_available_at_utc": panel_eff,
                    "audit_selection_status": audit_sel.get("selection_status", ""),
                    "panel_selection_status": panel_status,
                    "audit_selected_source_quality_value": audit_sel.get("selected_source_quality_value", ""),
                    "panel_selected_source_quality_value": panel_quality,
                    "selection_quality_contract_revision": audit_sel.get("selection_quality_contract_revision", ""),
                    "selection_parity_status": status,
                    "selection_parity_failure_reason": reason,
                    "scope_gate_recommendation": "evaluate" if status == "matched" else ("insufficient_data" if status == "unavailable_coverage" else "data_quality_blocked"),
                })
    return pd.DataFrame(rows, columns=SOURCE_SELECTION_PARITY_COLUMNS)


def audit_raw_feature_candidates(
    raw_feature_rows: pd.DataFrame,
    module: str,
    target_market: str,
    decision_timestamp_utc: Any,
    max_feature_age_hours: float,
) -> dict[str, Any]:
    decision_ts = parse_ts(decision_timestamp_utc)
    rows = raw_feature_rows.copy()
    feature_family = str(rows.get("feature_family", pd.Series([module])).iloc[0]) if not rows.empty else module
    result = {
        "module": module,
        "feature_family": feature_family,
        "target_market": target_market,
        "decision_timestamp_utc": decision_timestamp_utc,
        "raw_candidate_row_count": len(rows),
        "eligible_row_count": 0,
        "selected_row_count": 0,
        "excluded_future_timestamp_count": 0,
        "excluded_missing_timestamp_count": 0,
        "excluded_age_count": 0,
        "excluded_quality_count": 0,
        "excluded_target_mismatch_count": 0,
        "data_quality_blocking_violation_count": 0,
        "selected_row_strictly_valid": False,
        "clean_replacement_available": False,
        "module_gate_recommendation": "data_quality_blocked",
    }
    if rows.empty or decision_ts is None:
        return result
    target_series = rows.get("target_market", pd.Series([target_market] * len(rows), index=rows.index)).astype(str).str.upper()
    target_ok = target_series.eq(str(target_market).upper())
    result["excluded_target_mismatch_count"] = int((~target_ok).sum())
    rows = rows[target_ok].copy()
    if rows.empty:
        return result
    asof = pd.to_datetime(rows.get("feature_as_of_timestamp_utc", pd.Series(index=rows.index, dtype=object)), utc=True, errors="coerce")
    eff = pd.to_datetime(rows.get("effective_available_at_utc", pd.Series(index=rows.index, dtype=object)), utc=True, errors="coerce")
    missing = asof.isna() | eff.isna()
    future = (asof > decision_ts) | (eff > decision_ts)
    age = (decision_ts - eff).dt.total_seconds() / 3600
    age_missing = age.isna()
    age_bad = age > float(max_feature_age_hours)
    quality = rows.get("quality_grade", rows.get("raw_chain_quality", pd.Series(["high"] * len(rows), index=rows.index))).astype(str).str.lower()
    quality_bad = quality.isin(["bad", "low", "corrupt", "incomplete", "false"])
    eligible = ~(missing | future | age_missing | age_bad | quality_bad)
    result["excluded_missing_timestamp_count"] = int(missing.sum() + age_missing.sum())
    result["excluded_future_timestamp_count"] = int(future.sum())
    result["excluded_age_count"] = int(age_bad.sum())
    result["excluded_quality_count"] = int(quality_bad.sum())
    result["eligible_row_count"] = int(eligible.sum())
    result["data_quality_blocking_violation_count"] = int((missing | future | age_bad | age_missing).sum())
    if eligible.any():
        result["selected_row_count"] = 1
        result["selected_row_strictly_valid"] = True
        result["clean_replacement_available"] = True
        result["module_gate_recommendation"] = "evaluate"
    else:
        result["module_gate_recommendation"] = "data_quality_blocked"
    return result


def build_raw_feature_candidate_quality_audit(feature_join: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    if feature_join.empty:
        return pd.DataFrame(columns=RAW_FEATURE_CANDIDATE_AUDIT_COLUMNS)
    rows: list[dict[str, Any]] = []
    max_age = safe_float(cfg.get("max_feature_age_hours", 96), 96)
    for keys, group in feature_join.groupby(["module", "feature_family", "target_market", "decision_timestamp_utc"], dropna=False):
        module, feature_family, target, decision_ts = keys
        audit = audit_raw_feature_candidates(group, str(module), str(target), decision_ts, max_age)
        audit["feature_family"] = str(feature_family)
        rows.append(audit)
    return pd.DataFrame(rows, columns=RAW_FEATURE_CANDIDATE_AUDIT_COLUMNS)


def raw_quality_blocked_modules(raw_candidate_audit: pd.DataFrame) -> set[str]:
    if raw_candidate_audit.empty:
        return set()
    blocked = raw_candidate_audit[raw_candidate_audit["module_gate_recommendation"].astype(str).eq("data_quality_blocked")]
    return set(blocked.get("module", pd.Series(dtype=str)).astype(str).replace("", np.nan).dropna().tolist())


def build_expiry_group_sample_sufficiency_audit(
    panel: pd.DataFrame,
    *,
    feature_family: str,
    outcomes: list[str],
    min_oos_rows: int,
    min_test_months: int,
) -> pd.DataFrame:
    if panel.empty:
        return pd.DataFrame(columns=EXPIRY_GROUP_OOS_COLUMNS)
    reference_group = "non_expiry_friday"
    event_groups = ["triple_witching", "quarterly_expiry_non_triple", "monthly_expiry_non_quarterly"]
    rows: list[dict[str, Any]] = []
    work = panel.copy()
    work["test_month"] = pd.to_datetime(work.get("decision_timestamp_utc"), utc=True, errors="coerce").dt.tz_convert(ET).dt.to_period("M").astype(str)
    for target, target_panel in work.groupby("target_market"):
        ref = target_panel[target_panel.get("comparison_group", pd.Series(dtype=str)).astype(str).eq(reference_group)]
        for group_name in event_groups + [reference_group]:
            event = target_panel[target_panel.get("comparison_group", pd.Series(dtype=str)).astype(str).eq(group_name)]
            for outcome in outcomes:
                if outcome not in target_panel.columns:
                    continue
                event_valid = event[event[outcome].notna()]
                ref_valid = ref[ref[outcome].notna()]
                event_months = int(event_valid["test_month"].nunique()) if not event_valid.empty else 0
                ref_months = int(ref_valid["test_month"].nunique()) if not ref_valid.empty else 0
                event_n = len(event_valid)
                ref_n = len(ref_valid)
                sufficient = event_n >= min_oos_rows and ref_n >= min_oos_rows and event_months >= min_test_months and ref_months >= min_test_months
                gate = "passed" if sufficient else "insufficient_data"
                rows.append({
                    "target_market": target,
                    "comparison_group": group_name,
                    "reference_group": reference_group,
                    "feature_family": feature_family,
                    "feature_name": "expiry_event_flags",
                    "outcome": outcome,
                    "sample_count": event_n,
                    "oos_sample_count": event_n,
                    "test_month_count": event_months,
                    "minimum_oos_required": min_oos_rows,
                    "minimum_test_months_required": min_test_months,
                    "event_group_row_count": event_n,
                    "reference_group_row_count": ref_n,
                    "event_group_oos_row_count": event_n,
                    "reference_group_oos_row_count": ref_n,
                    "event_group_test_month_count": event_months,
                    "reference_group_test_month_count": ref_months,
                    "group_sufficiency_status": gate,
                    "research_execution_gate": gate,
                    "evidence_verdict": gate,
                })
    return pd.DataFrame(rows, columns=EXPIRY_GROUP_OOS_COLUMNS)


def research_gate_from_oos(results: pd.DataFrame, engine_requested: bool) -> str:
    if not engine_requested:
        return "not_run"
    if results.empty:
        return "insufficient_data"
    if "research_execution_gate" in results.columns and results["research_execution_gate"].astype(str).eq("passed").any():
        return "passed"
    if results["evidence_verdict"].astype(str).eq("data_quality_blocked").any():
        return "data_quality_blocked"
    return "insufficient_data"


def market_data_gate(feature_join: pd.DataFrame, no_lookahead_status: str) -> str:
    if feature_join.empty:
        return "insufficient_data"
    if no_lookahead_status == "failed":
        return "failed"
    return "passed"


def quality_blocked_modules(no_lookahead: pd.DataFrame) -> set[str]:
    if no_lookahead.empty or "no_lookahead_passed" not in no_lookahead.columns:
        return set()
    failed = no_lookahead[~no_lookahead["no_lookahead_passed"].astype(bool)]
    return set(failed.get("module", pd.Series(dtype=str)).astype(str).replace("", np.nan).dropna().tolist())


def apply_data_quality_block(results: pd.DataFrame, module_name: str, blocked: set[str]) -> pd.DataFrame:
    out = results.copy()
    if module_name not in blocked:
        return out
    if out.empty:
        out = pd.DataFrame([{"module": module_name}])
    out["research_execution_gate"] = "data_quality_blocked"
    out["evidence_verdict"] = "data_quality_blocked"
    out["p_value_status"] = "not_run_data_quality_blocked"
    out["raw_p_value"] = np.nan
    out["adjusted_p_value"] = np.nan
    return out


def apply_cta_vol_source_quality_blocks(results: pd.DataFrame, source_summary: pd.DataFrame) -> pd.DataFrame:
    if results.empty or source_summary.empty:
        return results
    blocked_sources = set(source_summary.loc[source_summary["module_gate_recommendation"].astype(str).eq("data_quality_blocked"), "module"].astype(str))
    out = results.copy()
    masks = []
    if "CTA" in blocked_sources:
        masks.append(out["feature_name"].astype(str).isin(["CTA_only", "CTA_plus_Vol"]))
    if "VolControl" in blocked_sources:
        masks.append(out["feature_name"].astype(str).isin(["Vol_only", "CTA_plus_Vol"]))
    if not masks:
        return out
    mask = masks[0]
    for extra in masks[1:]:
        mask = mask | extra
    out.loc[mask, "research_execution_gate"] = "data_quality_blocked"
    out.loc[mask, "evidence_verdict"] = "data_quality_blocked"
    out.loc[mask, "p_value_status"] = "not_run_data_quality_blocked"
    out.loc[mask, "raw_p_value"] = np.nan
    out.loc[mask, "adjusted_p_value"] = np.nan
    return out


def apply_scope_integrity_blocks(results: pd.DataFrame, scope_audit: pd.DataFrame, module: str) -> pd.DataFrame:
    if results.empty or scope_audit.empty:
        return results
    audit = scope_audit[scope_audit.get("module", pd.Series(dtype=str)).astype(str).eq(module)]
    if audit.empty:
        return results
    blocked_scopes = set(audit.loc[audit.get("scope_gate_recommendation", pd.Series(dtype=str)).astype(str).eq("data_quality_blocked"), "model_scope"].astype(str))
    insufficient_scopes = set(audit.loc[audit.get("scope_gate_recommendation", pd.Series(dtype=str)).astype(str).eq("insufficient_data"), "model_scope"].astype(str))
    out = results.copy()
    if "feature_name" not in out.columns:
        return out
    blocked_mask = out["feature_name"].astype(str).isin(blocked_scopes)
    insufficient_mask = out["feature_name"].astype(str).isin(insufficient_scopes) & ~blocked_mask
    out.loc[blocked_mask, "research_execution_gate"] = "data_quality_blocked"
    out.loc[blocked_mask, "evidence_verdict"] = "data_quality_blocked"
    out.loc[blocked_mask, "p_value_status"] = "not_run_data_quality_blocked"
    out.loc[blocked_mask, ["raw_p_value", "adjusted_p_value"]] = np.nan
    out.loc[insufficient_mask, "research_execution_gate"] = "insufficient_data"
    out.loc[insufficient_mask, "evidence_verdict"] = "insufficient_data"
    out.loc[insufficient_mask, "p_value_status"] = "not_run"
    return out


def build_scope_integrity_gate_audit(
    source_selection_parity: pd.DataFrame,
    leveraged_integrity: pd.DataFrame,
    expiry_integrity: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not source_selection_parity.empty:
        for keys, group in source_selection_parity.groupby(["module", "feature_family", "model_scope", "target_market", "decision_timestamp_utc"], dropna=False):
            module, family, scope, target, decision = keys
            recs = group.get("scope_gate_recommendation", pd.Series(dtype=str)).astype(str)
            gate = "data_quality_blocked" if recs.eq("data_quality_blocked").any() else ("insufficient_data" if recs.eq("insufficient_data").any() else "evaluate")
            rows.append({
                "module": module,
                "feature_family": family,
                "model_scope": scope,
                "target_market": target,
                "decision_timestamp_utc": decision,
                "scope_integrity_status": "eligible_primary" if gate == "evaluate" else gate,
                "scope_integrity_failure_reason": ";".join(sorted(set(group.get("selection_parity_failure_reason", pd.Series(dtype=str)).astype(str).replace("", np.nan).dropna().tolist()))),
                "scope_gate_recommendation": gate,
            })
    if not leveraged_integrity.empty:
        for keys, group in leveraged_integrity.groupby(["target_market", "decision_timestamp_utc"], dropna=False):
            target, decision = keys
            statuses = group.get("leveraged_etf_primary_input_integrity_status", pd.Series(dtype=str)).astype(str)
            status = "data_quality_blocked" if statuses.eq("data_quality_blocked").any() else ("insufficient_data" if statuses.eq("insufficient_data").any() else "eligible_primary")
            rows.append({
                "module": "LeveragedETF",
                "feature_family": "LeveragedETF",
                "model_scope": "LeveragedETF_pressure",
                "target_market": target,
                "decision_timestamp_utc": decision,
                "scope_integrity_status": status,
                "scope_integrity_failure_reason": ";".join(sorted(set(group.get("component_failure_reason", pd.Series(dtype=str)).astype(str).replace("", np.nan).dropna().tolist()))),
                "scope_gate_recommendation": "evaluate" if status == "eligible_primary" else status,
            })
    if not expiry_integrity.empty:
        for _, row in expiry_integrity.iterrows():
            rows.append({
                "module": row.get("module", "ExpiryCalendar"),
                "feature_family": "ExpiryCalendar",
                "model_scope": "expiry_classification_provenance",
                "target_market": "",
                "decision_timestamp_utc": "",
                "scope_integrity_status": row.get("scope_integrity_status", ""),
                "scope_integrity_failure_reason": row.get("scope_integrity_failure_reason", ""),
                "scope_gate_recommendation": row.get("scope_gate_recommendation", ""),
            })
    return pd.DataFrame(rows)


def build_module_data_quality_propagation_audit(no_lookahead: pd.DataFrame, oos_by_module: dict[str, pd.DataFrame], raw_candidate_audit: pd.DataFrame | None = None) -> pd.DataFrame:
    rows = []
    for module, result in oos_by_module.items():
        module_audit = no_lookahead[no_lookahead.get("module", pd.Series(dtype=str)).astype(str).eq(module)] if not no_lookahead.empty else pd.DataFrame()
        raw_audit = raw_candidate_audit[raw_candidate_audit.get("module", pd.Series(dtype=str)).astype(str).eq(module)] if raw_candidate_audit is not None and not raw_candidate_audit.empty else pd.DataFrame()
        failed = module_audit[~module_audit.get("no_lookahead_passed", pd.Series(dtype=bool)).astype(bool)] if not module_audit.empty else pd.DataFrame()
        reasons = failed.get("violation_reason", pd.Series(dtype=str)).astype(str)
        missing = reasons.str.contains("missing_required_timestamp|feature_age_missing", regex=True).sum() if not reasons.empty else 0
        future = reasons.str.contains("after_decision", regex=True).sum() if not reasons.empty else 0
        age = reasons.str.contains("feature_age_exceeds_maximum", regex=True).sum() if not reasons.empty else 0
        if result.empty:
            gate = "data_quality_blocked" if len(failed) else "insufficient_data"
            verdict = gate
            eligible = 0
        else:
            gate = ",".join(sorted(set(result.get("research_execution_gate", pd.Series(dtype=str)).astype(str))))
            verdict = ",".join(sorted(set(result.get("evidence_verdict", pd.Series(dtype=str)).astype(str))))
            eligible = int(pd.to_numeric(result.get("sample_count_oos", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
        rows.append({
            "module": module,
            "target_market": "",
            "raw_candidate_row_count": int(pd.to_numeric(raw_audit.get("raw_candidate_row_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not raw_audit.empty else len(module_audit),
            "eligible_row_count": int(pd.to_numeric(raw_audit.get("eligible_row_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not raw_audit.empty else eligible,
            "excluded_future_timestamp_count": int(future) + (int(pd.to_numeric(raw_audit.get("excluded_future_timestamp_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not raw_audit.empty else 0),
            "excluded_missing_timestamp_count": int(missing) + (int(pd.to_numeric(raw_audit.get("excluded_missing_timestamp_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not raw_audit.empty else 0),
            "excluded_age_count": int(age) + (int(pd.to_numeric(raw_audit.get("excluded_age_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not raw_audit.empty else 0),
            "excluded_quality_count": int(pd.to_numeric(raw_audit.get("excluded_quality_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not raw_audit.empty else 0,
            "excluded_target_mismatch_count": int(pd.to_numeric(raw_audit.get("excluded_target_mismatch_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not raw_audit.empty else 0,
            "selected_row_count": int(pd.to_numeric(raw_audit.get("selected_row_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not raw_audit.empty else eligible,
            "data_quality_blocking_violation_count": len(failed) + (int(pd.to_numeric(raw_audit.get("data_quality_blocking_violation_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not raw_audit.empty else 0),
            "research_execution_gate": gate,
            "evidence_verdict": verdict,
        })
    return pd.DataFrame(rows, columns=MODULE_QUALITY_AUDIT_COLUMNS)


def refresh_status_rows(refresh_daily_prices: bool, refresh_intraday_prices: bool, run_gamma_surrogate_exploration: bool) -> list[dict[str, Any]]:
    rows = []
    for flag_name, enabled in [
        ("refresh_daily_prices", refresh_daily_prices),
        ("refresh_intraday_prices", refresh_intraday_prices),
        ("run_gamma_surrogate_exploration", run_gamma_surrogate_exploration),
    ]:
        if enabled:
            rows.append({
                "module": "RefreshAdapter",
                "operation": flag_name,
                "status": "not_supported",
                "reason": "refresh_adapter_not_implemented",
            })
    return rows


def source_inventory(root: Path) -> pd.DataFrame:
    paths = [
        root / "market_bomb_history" / "cta_proxy_history.csv",
        root / "market_bomb_history" / "vol_control_proxy_history.csv",
        root / "dealer_gamma_proxy_history.csv",
        root / "market_bomb_history" / "dealer_gamma_proxy_history.csv",
        root / "market_bomb_history" / "leveraged_etf_aum_history.csv",
        root / EXPIRY_CALENDAR_PATH,
        root / EXPIRY_CALENDAR_METADATA_PATH,
        root / EXPIRY_SCHEDULE_AVAILABILITY_RULES_PATH,
        root / EXPIRY_FRIDAY_CLASSIFICATION_PATH,
        root / EXPIRY_FRIDAY_CLASSIFICATION_METADATA_PATH,
        root / SOURCE_COVERAGE_CONTRACTS_PATH,
        root / LEVERAGED_ETF_INPUT_CONTRACTS_PATH,
        root / NYSE_CALENDAR_PATH,
        root / NYSE_CALENDAR_METADATA_PATH,
        root / EXPIRY_INTRADAY_RULES_PATH,
    ]
    rows = []
    for path in paths:
        rows.append({
            "source_path_or_provider": str(path.relative_to(root)).replace("\\", "/") if path.exists() else str(path.relative_to(root)).replace("\\", "/"),
            "exists": path.exists(),
            "source_hash_or_request_id": hash_file(path) if path.exists() and path.is_file() else "",
            "file_size_bytes": path.stat().st_size if path.exists() and path.is_file() else 0,
        })
    return pd.DataFrame(rows)


def build_nyse_session_calendar_audit(calendar: pd.DataFrame, root: Path | None = None) -> pd.DataFrame:
    if calendar.empty:
        return pd.DataFrame([{
            "session_date": "",
            "calendar_coverage_status": "missing",
            "is_regular_session": False,
            "is_early_close": False,
            "regular_open_et": "",
            "regular_close_et": "",
            "calendar_source": "",
            "calendar_version": "",
            "availability_status": "unavailable",
            "availability_failure_reason": "nyse_calendar_file_missing",
        }], columns=NYSE_SESSION_AUDIT_COLUMNS)
    provenance = validate_nyse_calendar_provenance(root, calendar) if root is not None else {"status": "passed", "reason": ""}
    rows = []
    for _, row in calendar.iterrows():
        is_regular = bool(row.get("is_regular_session", False))
        rows.append({
            "session_date": row.get("session_date", ""),
            "calendar_coverage_status": "covered",
            "is_regular_session": is_regular,
            "is_early_close": bool(row.get("is_early_close", False)),
            "regular_open_et": row.get("regular_open_et", ""),
            "regular_close_et": row.get("regular_close_et", ""),
            "calendar_source": row.get("calendar_source", ""),
            "calendar_version": row.get("calendar_version", ""),
            "availability_status": "available" if is_regular and provenance["status"] == "passed" else "unavailable",
            "availability_failure_reason": "" if is_regular and provenance["status"] == "passed" else ("nyse_calendar_provenance_validation_failed:" + provenance["reason"] if provenance["status"] != "passed" else "not_regular_session"),
        })
    return pd.DataFrame(rows, columns=NYSE_SESSION_AUDIT_COLUMNS)


def build_nyse_calendar_continuity_audit(root: Path, calendar: pd.DataFrame) -> pd.DataFrame:
    validation = validate_nyse_calendar_provenance(root, calendar)
    rows = []
    if calendar.empty:
        return pd.DataFrame([{"validation_status": "failed", "validation_failure_reason": "nyse_calendar_file_missing"}])
    start = str(calendar["session_date"].min())
    end = str(calendar["session_date"].max())
    full_dates = pd.date_range(start, end, freq="D").date.astype(str)
    observed = set(calendar["session_date"].astype(str))
    missing = [d for d in full_dates if d not in observed]
    rows.append({
        "coverage_start": start,
        "coverage_end": end,
        "expected_calendar_date_count": len(full_dates),
        "observed_calendar_date_count": len(observed),
        "missing_calendar_date_count": len(missing),
        "missing_calendar_dates": ";".join(missing[:50]),
        "validation_status": validation["status"],
        "validation_failure_reason": validation["reason"],
    })
    return pd.DataFrame(rows)


def build_expiry_classification_coverage_audit(root: Path, classification: pd.DataFrame, nyse_calendar: pd.DataFrame) -> pd.DataFrame:
    validation = validate_expiry_classification_provenance(root, classification, nyse_calendar)
    metadata = load_expiry_friday_classification_metadata(root)
    start = str(metadata.get("coverage_start", classification["session_date"].min() if not classification.empty else ""))
    end = str(metadata.get("coverage_end", classification["session_date"].max() if not classification.empty else ""))
    if nyse_calendar.empty or "session_date" not in nyse_calendar.columns:
        return pd.DataFrame([{"availability_status": "unavailable", "availability_failure_reason": "nyse_calendar_missing"}], columns=EXPIRY_CLASSIFICATION_AUDIT_COLUMNS)
    regular_fridays = nyse_calendar[
        nyse_calendar.get("is_regular_session", pd.Series(dtype=bool)).astype(bool)
        & (pd.to_datetime(nyse_calendar["session_date"], errors="coerce").dt.weekday == 4)
        & (nyse_calendar["session_date"].astype(str) >= start)
        & (nyse_calendar["session_date"].astype(str) <= end)
    ]["session_date"].astype(str).tolist()
    rows = []
    for day in regular_fridays:
        class_rows = classification[classification["session_date"].astype(str).eq(day)] if not classification.empty else pd.DataFrame()
        if class_rows.empty:
            rows.append({
                "session_date": day,
                "expected_regular_friday": True,
                "classification_row_count": 0,
                "classification_status": "unavailable_incomplete_schedule",
                "classification_complete": False,
                "comparison_group": "unavailable_incomplete_schedule",
                "availability_status": "unavailable",
                "availability_failure_reason": "classification_row_missing",
            })
            continue
        row = class_rows.iloc[-1]
        ok = validation["status"] == "passed" and bool(row.get("classification_complete", False)) and str(row.get("classification_status", "")) == "available_complete"
        rows.append({
            "session_date": day,
            "expected_regular_friday": True,
            "classification_row_count": len(class_rows),
            "classification_status": row.get("classification_status", ""),
            "classification_complete": bool(row.get("classification_complete", False)),
            "comparison_group": row.get("comparison_group", ""),
            "availability_status": "available" if ok else "unavailable",
            "availability_failure_reason": "" if ok else validation.get("reason", "classification_incomplete"),
        })
    return pd.DataFrame(rows, columns=EXPIRY_CLASSIFICATION_AUDIT_COLUMNS)


def build_expiry_classification_provenance_audit(root: Path, classification: pd.DataFrame, nyse_calendar: pd.DataFrame) -> pd.DataFrame:
    validation = validate_expiry_classification_provenance(root, classification, nyse_calendar)
    metadata = load_expiry_friday_classification_metadata(root)
    return pd.DataFrame([{
        "validation_status": validation.get("status", "failed"),
        "validation_failure_reason": validation.get("reason", ""),
        "regular_friday_count": validation.get("regular_friday_count", 0),
        "coverage_start": metadata.get("coverage_start", ""),
        "coverage_end": metadata.get("coverage_end", ""),
        "source_identifier": metadata.get("source_identifier", ""),
        "calendar_source_file_sha256": metadata.get("calendar_source_file_sha256", ""),
        "schedule_rules_file_sha256": metadata.get("schedule_rules_file_sha256", ""),
        "classification_calendar_file_sha256": metadata.get("classification_calendar_file_sha256", ""),
    }])


def build_expiry_classification_integrity_gate_audit(root: Path, classification: pd.DataFrame, nyse_calendar: pd.DataFrame) -> pd.DataFrame:
    validation = validate_expiry_classification_provenance(root, classification, nyse_calendar)
    status = "passed" if validation.get("status") == "passed" else "data_quality_blocked"
    return pd.DataFrame([{
        "module": "ExpiryCalendar",
        "classification_provenance_status": validation.get("status", "failed"),
        "classification_provenance_failure_reason": validation.get("reason", ""),
        "scope_integrity_status": status,
        "scope_integrity_failure_reason": "" if status == "passed" else "expiry_classification_provenance_invalid:" + str(validation.get("reason", "")),
        "scope_gate_recommendation": "evaluate" if status == "passed" else "data_quality_blocked",
        "regular_friday_count": validation.get("regular_friday_count", 0),
    }])


def build_expiry_classification_historical_availability_audit(
    root: Path,
    classification: pd.DataFrame,
    nyse_calendar: pd.DataFrame,
    daily_outcomes: pd.DataFrame,
) -> pd.DataFrame:
    validation = validate_expiry_classification_provenance(root, classification, nyse_calendar)
    rows: list[dict[str, Any]] = []
    if classification.empty:
        return pd.DataFrame([{
            "session_date": "",
            "target_market": "",
            "decision_timestamp_utc": "",
            "comparison_group": "unavailable_incomplete_schedule",
            "classification_complete": False,
            "classification_effective_available_at_utc": "",
            "classification_provenance_status": validation.get("status", "failed"),
            "historically_available_at_decision": False,
            "primary_eligible": False,
            "eligibility_failure_reason": "classification_missing",
        }])
    targets = sorted(daily_outcomes.get("target_market", pd.Series(["US"])).astype(str).unique().tolist()) if not daily_outcomes.empty else ["US"]
    for _, crow in classification.iterrows():
        day = str(crow.get("session_date", ""))
        default_decision = pd.Timestamp.combine(pd.Timestamp(day).date(), time(9, 30)).tz_localize(ET).tz_convert(UTC).isoformat() if day else ""
        for target in targets:
            decision_ts_text = default_decision
            decision_ts = parse_ts(decision_ts_text)
            eff_ts = parse_ts(crow.get("classification_effective_available_at_utc", ""))
            complete = bool(crow.get("classification_complete", False))
            historically_available = bool(eff_ts is not None and decision_ts is not None and eff_ts <= decision_ts)
            primary = validation.get("status") == "passed" and complete and historically_available and str(crow.get("classification_status", "")) == "available_complete"
            reason = ""
            if validation.get("status") != "passed":
                reason = "expiry_classification_provenance_invalid:" + str(validation.get("reason", ""))
            elif not complete:
                reason = "classification_incomplete"
            elif not historically_available:
                reason = "classification_effective_availability_after_decision"
            rows.append({
                "session_date": day,
                "target_market": target,
                "decision_time_policy": "expiry_event_decision_0930_et_v1",
                "decision_timestamp_utc": decision_ts_text,
                "comparison_group": crow.get("comparison_group", ""),
                "classification_complete": complete,
                "classification_effective_available_at_utc": crow.get("classification_effective_available_at_utc", ""),
                "classification_provenance_status": validation.get("status", "failed"),
                "historically_available_at_decision": historically_available,
                "primary_eligible": primary,
                "eligibility_failure_reason": reason,
            })
    return pd.DataFrame(rows)


def build_provider_bar_semantics_validation_audit(root: Path, targets: list[str]) -> pd.DataFrame:
    event_rules = expiry_intraday_rules(root)
    verified = bool(event_rules.get("provider_bar_semantics_verified", False))
    rows = []
    for target in targets:
        rows.append({
            "provider": event_rules.get("provider", "local_intraday_bars"),
            "target_market": target,
            "bar_timestamp_convention": event_rules.get("bar_timestamp_convention", "bar_end"),
            "tested_session_date": "",
            "expected_first_regular_bar_timestamp_et": event_rules.get("regular_session_open_bar_timestamp_et", "09:35"),
            "observed_first_regular_bar_timestamp_et": "",
            "official_open_reference": "",
            "official_close_reference": "",
            "validation_status": "passed" if verified else "not_verified",
            "validation_evidence_source": event_rules.get("provider_bar_semantics_source", ""),
            "validated_at_utc": event_rules.get("provider_bar_semantics_verified_at_utc", ""),
        })
    return pd.DataFrame(rows)


def market_level_model_spec() -> dict[str, Any]:
    return {
        "version": "market_level_model_spec_v1_1_8",
        "actionization_gate": False,
        "targets": ["SPY", "QQQ", "SOXX"],
        "minimum_training_observations": 252,
        "minimum_valid_oos_observations": 100,
        "minimum_non_empty_oos_folds": 3,
        "eod_models": {
            "B0": {"parent": "", "features": []},
            "B1": {"parent": "B0", "features": ["cta_exposure_change_proxy"]},
            "B2": {"parent": "B0", "features": ["vol_control_exposure_change_proxy"]},
            "B3": {"parent": "B0", "features": ["cta_exposure_change_proxy", "vol_control_exposure_change_proxy"]},
            "B4": {"parent": "B3", "features": ["cta_exposure_change_proxy", "vol_control_exposure_change_proxy", "negative_gamma_proxy_indicator", "gamma_flip_distance_pct"]},
            "B5": {"parent": "B4", "features": ["cta_exposure_change_proxy", "vol_control_exposure_change_proxy", "negative_gamma_proxy_indicator", "gamma_flip_distance_pct", "systematic_sell_pressure_x_negative_gamma"]},
        },
        "intraday_models": {
            "C0": {"parent": "", "features": []},
            "C1": {"parent": "C0", "features": ["aggregate_pressure_usd"]},
            "C2": {"parent": "C1", "features": ["aggregate_pressure_usd", "negative_gamma_proxy_indicator", "gamma_flip_distance_pct"]},
            "C3": {"parent": "C2", "features": ["aggregate_pressure_usd", "negative_gamma_proxy_indicator", "gamma_flip_distance_pct", "leveraged_sell_pressure_x_negative_gamma"]},
        },
        "direct_parent_incremental_formula": "incremental_oos_r_squared_vs_parent = 1 - SSE_augmented / SSE_parent on identical paired OOS rows",
        "guardrails": [
            "CTA and VolControl are rule-based proxies, not observed fund flows.",
            "Leveraged ETF pressure is an estimated rebalance proxy, not confirmed execution.",
            "Dealer Gamma is reconstructed from option-chain assumptions, not observed dealer inventory or hedge flow.",
            "Associations are predictive OOS fit only, not causal attribution.",
        ],
    }


def build_market_level_feature_panel(
    *,
    eod_decision_universe: pd.DataFrame,
    intraday_decision_universe: pd.DataFrame,
    daily_baseline: pd.DataFrame,
    cta_panel: pd.DataFrame,
    dealer_panel: pd.DataFrame,
    lev_panel: pd.DataFrame,
    dealer_intraday_selection: pd.DataFrame | None = None,
    dealer_eod_selection_audit: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if eod_decision_universe is None:
        raise ValueError("eod_decision_universe is required")
    if intraday_decision_universe is None:
        raise ValueError("intraday_decision_universe is required")

    def numeric_col(df: pd.DataFrame, col: str, default: float = np.nan) -> pd.Series:
        if col not in df.columns:
            return pd.Series([default] * len(df), index=df.index, dtype=float)
        return pd.to_numeric(df[col], errors="coerce")

    targets = ["SPY", "QQQ", "SOXX"]
    eod = eod_decision_universe[eod_decision_universe.get("target_market", pd.Series(dtype=str)).astype(str).isin(targets)].copy() if not eod_decision_universe.empty else pd.DataFrame()
    if not eod.empty:
        eod = eod.merge(daily_baseline.drop(columns=["decision_timestamp_utc"], errors="ignore"), on=["target_market", "decision_date"], how="left", suffixes=("", "_baseline"))
        eod["decision_time_policy"] = "eod_regular_close_v1"
        eod["model_clock"] = "EOD"
        if "forward_return_3d" not in eod.columns:
            eod["forward_return_3d"] = np.nan
        cta_cols = [
            "target_market", "decision_timestamp_utc", "cta_exposure_change_proxy", "vol_control_exposure_change_proxy",
            "cta_primary_eligible", "vol_primary_eligible", "cta_selection_status", "vol_selection_status",
            "cta_availability_state", "vol_availability_state", "cta_invalid_reason", "vol_invalid_reason",
            "cta_selected_source_row_identifier", "cta_selected_source_content_hash", "cta_selected_source_effective_available_at_utc",
            "vol_selected_source_row_identifier", "vol_selected_source_content_hash", "vol_selected_source_effective_available_at_utc",
        ]
        if not cta_panel.empty:
            eod = eod.merge(cta_panel[[c for c in cta_cols if c in cta_panel.columns]], on=["target_market", "decision_timestamp_utc"], how="left")
        dealer_cols = ["target_market", "decision_timestamp_utc", "negative_gamma_proxy_indicator", "gamma_flip_distance_pct", "net_gex_proxy", "gamma_flip_state", "dealer_gamma_selection_status", "dealer_gamma_effective_available_at_utc", "dealer_gamma_sign_policy_revision"]
        if not dealer_panel.empty:
            eod = eod.merge(dealer_panel[[c for c in dealer_cols if c in dealer_panel.columns]], on=["target_market", "decision_timestamp_utc"], how="left", suffixes=("", "_dealer"))
        if dealer_eod_selection_audit is not None and not dealer_eod_selection_audit.empty:
            gamma_audit_cols = [
                "target_market", "decision_timestamp_utc", "selection_status", "availability_state", "primary_eligible",
                "invalid_reason", "selected_source_row_identifier", "selected_source_content_hash",
                "selected_source_effective_available_at_utc", "selected_source_as_of_timestamp_utc",
                "dealer_gamma_source_contract_revision", "selection_policy_revision",
            ]
            eod = eod.merge(dealer_eod_selection_audit[[c for c in gamma_audit_cols if c in dealer_eod_selection_audit.columns]], on=["target_market", "decision_timestamp_utc"], how="left", suffixes=("", "_gamma_eod_audit"))
            eod["dealer_gamma_selection_status"] = eod.get("selection_status", eod.get("dealer_gamma_selection_status", ""))
            eod["dealer_gamma_availability_state"] = eod.get("availability_state", "")
            eod["dealer_gamma_primary_eligible"] = eod.get("primary_eligible", False)
            eod["dealer_gamma_invalid_reason"] = eod.get("invalid_reason", "")
            eod["dealer_gamma_selected_source_row_identifier"] = eod.get("selected_source_row_identifier", "")
            eod["dealer_gamma_selected_source_content_hash"] = eod.get("selected_source_content_hash", "")
            eod["dealer_gamma_selected_source_effective_available_at_utc"] = eod.get("selected_source_effective_available_at_utc", "")
        cta_num = numeric_col(eod, "cta_exposure_change_proxy")
        vol_num = numeric_col(eod, "vol_control_exposure_change_proxy")
        if "negative_gamma_proxy_indicator" not in eod.columns:
            eod["negative_gamma_proxy_indicator"] = np.nan
        eod["systematic_sell_pressure_proxy"] = -(cta_num + vol_num)
        eod["systematic_sell_pressure_x_negative_gamma"] = eod["systematic_sell_pressure_proxy"] * eod["negative_gamma_proxy_indicator"]
    if not intraday_decision_universe.empty:
        intraday = intraday_decision_universe[intraday_decision_universe.get("target_market", pd.Series(dtype=str)).astype(str).isin(targets)].copy()
        lev_join_cols = [c for c in lev_panel.columns if c not in {"decision_date", "model_clock", "decision_time_policy"}]
        if not lev_panel.empty:
            intraday = intraday.merge(lev_panel[lev_join_cols], on=["target_market", "decision_timestamp_utc"], how="left", suffixes=("", "_leveraged"))
    else:
        intraday = pd.DataFrame()
    if not intraday.empty:
        intraday["decision_time_policy"] = "intraday_1530_et_v1"
        intraday["model_clock"] = "INTRADAY"
        if "leveraged_etf_primary_input_gate" not in intraday.columns:
            intraday["leveraged_etf_primary_input_gate"] = "insufficient_data"
        else:
            intraday["leveraged_etf_primary_input_gate"] = intraday["leveraged_etf_primary_input_gate"].fillna("insufficient_data")
        if "leveraged_etf_primary_input_integrity_status" not in intraday.columns:
            intraday["leveraged_etf_primary_input_integrity_status"] = intraday["leveraged_etf_primary_input_gate"]
        else:
            intraday["leveraged_etf_primary_input_integrity_status"] = intraday["leveraged_etf_primary_input_integrity_status"].fillna("insufficient_data")
        if dealer_intraday_selection is not None and not dealer_intraday_selection.empty:
            gamma_cols = ["target_market", "decision_timestamp_utc", "negative_gamma_proxy_indicator", "gamma_flip_distance_pct", "net_gex_proxy", "gamma_flip_state", "selection_status", "selected_source_effective_available_at_utc", "dealer_gamma_sign_policy_revision"]
            intraday = intraday.merge(dealer_intraday_selection[[c for c in gamma_cols if c in dealer_intraday_selection.columns]], on=["target_market", "decision_timestamp_utc"], how="left", suffixes=("", "_intraday_gamma"))
            intraday["dealer_gamma_selection_status"] = intraday.get("selection_status", "")
            intraday["dealer_gamma_effective_available_at_utc"] = intraday.get("selected_source_effective_available_at_utc", "")
        if "negative_gamma_proxy_indicator" not in intraday.columns:
            intraday["negative_gamma_proxy_indicator"] = np.nan
        sell_pressure = -numeric_col(intraday, "aggregate_pressure_usd")
        intraday["leveraged_sell_pressure_x_negative_gamma"] = sell_pressure * intraday["negative_gamma_proxy_indicator"]
    panel = pd.concat([eod, intraday], ignore_index=True, sort=False)
    required_cols = [
        "target_market", "decision_date", "decision_timestamp_utc", "decision_time_policy", "model_clock",
        "next_session_return", "forward_return_3d", "forward_return_5d", "forward_realized_vol_5d",
        "intraday_return_1530_to_close", "intraday_absolute_return_1530_to_close", "intraday_range_1530_to_close",
        "cta_exposure_change_proxy", "vol_control_exposure_change_proxy", "aggregate_pressure_usd",
        "negative_gamma_proxy_indicator", "gamma_flip_distance_pct", "net_gex_proxy",
        "systematic_sell_pressure_x_negative_gamma", "leveraged_sell_pressure_x_negative_gamma",
    ]
    return ensure_columns(panel, required_cols)


def _aggregate_parity_status(statuses: list[str]) -> str:
    clean = [str(s) for s in statuses if str(s)]
    if any(s == "mismatch" for s in clean):
        return "mismatch"
    if any(s == "audit_missing" for s in clean):
        return "audit_missing"
    if any(s == "selected_invalid" for s in clean):
        return "selected_invalid"
    if any(s == "unavailable_coverage" for s in clean):
        return "unavailable_coverage"
    if clean and all(s == "matched" for s in clean):
        return "matched"
    return "not_applicable"


def _component_integrity_from_status(selection_status: str, availability_state: str, primary_eligible: bool, source_parity_status: str, reason: str) -> tuple[str, str]:
    if selection_status == "selected_invalid" or availability_state in {"selected_invalid", "data_quality_blocked", "missing_required_field"}:
        return "selected_invalid", reason or "selected_invalid"
    if source_parity_status == "mismatch":
        return "selected_invalid", ";".join([r for r in [reason, "source_selection_parity_mismatch"] if r])
    if source_parity_status == "audit_missing":
        return "selected_invalid", reason or "required_parity_audit_missing"
    if source_parity_status == "selected_invalid":
        return "selected_invalid", reason or "source_selection_selected_invalid"
    if selection_status != "selected" or not primary_eligible:
        return "unavailable_coverage", reason or "source_unavailable"
    if source_parity_status == "unavailable_coverage":
        return "unavailable_coverage", reason or "source_selection_unavailable_coverage"
    return "valid", ""


def build_market_level_component_provenance_status(
    *,
    market_level_panel: pd.DataFrame,
    cta_vol_selector_parity: pd.DataFrame,
    leveraged_selector_parity: pd.DataFrame,
    leveraged_primary_integrity: pd.DataFrame,
    dealer_eod_panel: pd.DataFrame,
    dealer_intraday_selection: pd.DataFrame,
    dealer_eod_actual_feature_lineage: pd.DataFrame | None = None,
    dealer_gamma_source_parity: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if market_level_panel.empty:
        return pd.DataFrame(columns=MARKET_LEVEL_COMPONENT_PROVENANCE_COLUMNS)

    def add_row(
        panel_row: pd.Series,
        component: str,
        selection_status: str,
        availability_state: str,
        primary_eligible: bool,
        source_parity_status: str,
        reason: str = "",
        source_id: str = "",
        source_hash: str = "",
        source_eff: str = "",
        evidence_type: str = "actual_vs_fresh_source_selection" ,
        dependency_component: str = "",
        derived_base_status: str = "",
        input_integrity_status: str = "",
    ) -> None:
        integrity, integrity_reason = _component_integrity_from_status(selection_status, availability_state, primary_eligible, source_parity_status, reason)
        if not input_integrity_status:
            input_integrity_status = integrity
        rows.append({
            "target_market": panel_row.get("target_market", ""),
            "decision_timestamp_utc": panel_row.get("decision_timestamp_utc", ""),
            "model_clock": panel_row.get("model_clock", ""),
            "required_component": component,
            "selection_status": selection_status,
            "availability_state": availability_state,
            "primary_eligible": primary_eligible,
            "source_parity_status": source_parity_status,
            "input_integrity_status": input_integrity_status,
            "integrity_status": integrity,
            "integrity_reason": integrity_reason,
            "selected_source_row_identifier": source_id,
            "selected_source_content_hash": source_hash,
            "selected_source_effective_available_at_utc": source_eff,
            "provenance_evidence_type": evidence_type,
            "provenance_dependency_component": dependency_component,
            "derived_from_base_integrity_status": derived_base_status,
            "provenance_policy_revision": "market_level_component_provenance_v1_1_13",
        })

    for _, prow in market_level_panel.iterrows():
        target = str(prow.get("target_market", ""))
        decision = str(prow.get("decision_timestamp_utc", ""))
        clock = str(prow.get("model_clock", ""))
        add_row(prow, "baseline", "selected", "valid", True, "not_applicable")
        if clock == "EOD":
            for comp, prefix, family in [("CTA", "cta", "CTA"), ("VolControl", "vol", "VolControl")]:
                parity = pd.DataFrame()
                if not cta_vol_selector_parity.empty:
                    parity = cta_vol_selector_parity[
                        cta_vol_selector_parity.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)
                        & cta_vol_selector_parity.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str).eq(decision)
                        & cta_vol_selector_parity.get("required_source_family", pd.Series(dtype=str)).astype(str).eq(family)
                    ]
                panel_primary = bool(prow.get(f"{prefix}_primary_eligible", False))
                parity_status = _aggregate_parity_status(parity.get("selection_parity_status", pd.Series(dtype=str)).astype(str).tolist()) if not parity.empty else ("audit_missing" if panel_primary else "unavailable_coverage")
                add_row(
                    prow,
                    comp,
                    str(prow.get(f"{prefix}_selection_status", "unavailable_coverage")),
                    str(prow.get(f"{prefix}_availability_state", "unavailable_coverage")),
                    panel_primary,
                    parity_status,
                    str(prow.get(f"{prefix}_invalid_reason", "")),
                    str(prow.get(f"{prefix}_selected_source_row_identifier", "")),
                    str(prow.get(f"{prefix}_selected_source_content_hash", "")),
                    str(prow.get(f"{prefix}_selected_source_effective_available_at_utc", "")),
                )
            eod_match = dealer_eod_panel[
                dealer_eod_panel.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)
                & dealer_eod_panel.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str).eq(decision)
            ] if not dealer_eod_panel.empty else pd.DataFrame()
            if eod_match.empty:
                add_row(prow, "DealerGammaEOD", "unavailable_coverage", "unavailable_coverage", False, "unavailable_coverage", "dealer_gamma_eod_unavailable")
                add_row(prow, "DealerGammaSignEOD", "unavailable_coverage", "unavailable_coverage", False, "unavailable_coverage", "dealer_gamma_sign_eod_unavailable")
            else:
                drow = eod_match.iloc[-1]
                gamma_selected = bool(drow.get("primary_eligible", False)) and str(drow.get("selection_status", drow.get("dealer_gamma_selection_status", ""))) == "selected"
                gamma_selection_status = str(drow.get("selection_status", drow.get("dealer_gamma_selection_status", "unavailable_coverage")))
                gamma_availability_state = str(drow.get("availability_state", drow.get("dealer_gamma_availability_state", "unavailable_coverage")))
                gamma_invalid_reason = str(drow.get("invalid_reason", drow.get("dealer_gamma_invalid_reason", "")))
                gamma_parity = dealer_gamma_source_parity[
                    dealer_gamma_source_parity.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)
                    & dealer_gamma_source_parity.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str).eq(decision)
                    & dealer_gamma_source_parity.get("required_source_family", pd.Series(dtype=str)).astype(str).eq("DealerGammaEOD")
                ] if dealer_gamma_source_parity is not None and not dealer_gamma_source_parity.empty else pd.DataFrame()
                lineage_match = dealer_eod_actual_feature_lineage[
                    dealer_eod_actual_feature_lineage.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)
                    & dealer_eod_actual_feature_lineage.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str).eq(decision)
                ] if dealer_eod_actual_feature_lineage is not None and not dealer_eod_actual_feature_lineage.empty else pd.DataFrame()
                lrow = lineage_match.iloc[-1] if not lineage_match.empty else pd.Series(dtype=object)
                gamma_parity_status = _aggregate_parity_status(gamma_parity.get("selection_parity_status", pd.Series(dtype=str)).astype(str).tolist()) if not gamma_parity.empty else ("audit_missing" if gamma_selected else ("selected_invalid" if gamma_selection_status == "selected_invalid" else "unavailable_coverage"))
                gamma_integrity, gamma_reason = _component_integrity_from_status(gamma_selection_status, gamma_availability_state, gamma_selected, gamma_parity_status, gamma_invalid_reason)
                add_row(prow, "DealerGammaEOD", gamma_selection_status, gamma_availability_state, gamma_selected, gamma_parity_status, gamma_invalid_reason, str(lrow.get("actual_selected_source_row_identifier", "")), str(lrow.get("actual_selected_source_content_hash", "")), str(lrow.get("actual_selected_source_effective_available_at_utc", "")))
                sign_ok = pd.notna(safe_float(drow.get("negative_gamma_proxy_indicator", np.nan)))
                if gamma_integrity == "selected_invalid":
                    add_row(prow, "DealerGammaSignEOD", "selected_invalid", "selected_invalid", False, "not_applicable", gamma_reason, str(drow.get("selected_source_row_identifier", "")), str(drow.get("selected_source_content_hash", drow.get("source_hash_or_request_id", ""))), str(drow.get("dealer_gamma_effective_available_at_utc", "")), "derived_from_base_component", "DealerGammaEOD", gamma_integrity)
                elif gamma_integrity == "unavailable_coverage":
                    add_row(prow, "DealerGammaSignEOD", "unavailable_coverage", "unavailable_coverage", False, "not_applicable", gamma_reason or "dealer_gamma_eod_unavailable", str(drow.get("selected_source_row_identifier", "")), str(drow.get("selected_source_content_hash", drow.get("source_hash_or_request_id", ""))), str(drow.get("dealer_gamma_effective_available_at_utc", "")), "derived_from_base_component", "DealerGammaEOD", gamma_integrity)
                else:
                    add_row(prow, "DealerGammaSignEOD", "selected" if sign_ok else "unavailable_coverage", "valid" if sign_ok else "unavailable_coverage", bool(sign_ok), "not_applicable", "" if sign_ok else "gamma_sign_convention_unverified", str(drow.get("selected_source_row_identifier", "")), str(drow.get("selected_source_content_hash", drow.get("source_hash_or_request_id", ""))), str(drow.get("dealer_gamma_effective_available_at_utc", "")), "derived_from_base_component", "DealerGammaEOD", gamma_integrity)
        elif clock == "INTRADAY":
            lev_parity = leveraged_selector_parity[
                leveraged_selector_parity.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)
                & leveraged_selector_parity.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str).eq(decision)
            ] if not leveraged_selector_parity.empty else pd.DataFrame()
            lev_integrity = leveraged_primary_integrity[
                leveraged_primary_integrity.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)
                & leveraged_primary_integrity.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str).eq(decision)
            ] if not leveraged_primary_integrity.empty else pd.DataFrame()
            panel_lev_eligible = str(prow.get("leveraged_etf_primary_input_gate", prow.get("leveraged_etf_primary_input_integrity_status", ""))) == "eligible_primary"
            if not lev_integrity.empty:
                gates = lev_integrity.get("leveraged_etf_primary_input_gate", pd.Series(dtype=str)).astype(str).tolist()
                if "data_quality_blocked" in gates:
                    lev_input_status = "data_quality_blocked"
                elif "insufficient_data" in gates:
                    lev_input_status = "insufficient_data"
                elif gates and all(g == "eligible_primary" for g in gates):
                    lev_input_status = "eligible_primary"
                else:
                    lev_input_status = "insufficient_data"
            else:
                lev_input_status = "audit_missing" if panel_lev_eligible else "insufficient_data"
            lev_parity_status = _aggregate_parity_status(lev_parity.get("selection_parity_status", pd.Series(dtype=str)).astype(str).tolist()) if not lev_parity.empty else ("audit_missing" if panel_lev_eligible else "unavailable_coverage")
            if lev_input_status == "data_quality_blocked":
                lev_status = "selected_invalid"
            elif lev_input_status == "eligible_primary":
                lev_status = "selected"
            else:
                lev_status = "unavailable_coverage"
            lev_reason = str(prow.get("availability_failure_reason", ""))
            if lev_parity_status == "audit_missing" or lev_input_status == "audit_missing":
                lev_status = "selected_invalid"
                lev_reason = lev_reason or "required_parity_audit_missing"
            add_row(prow, "LeveragedETF", lev_status, "valid" if lev_status == "selected" else lev_status, lev_status == "selected", lev_parity_status, lev_reason, input_integrity_status=lev_input_status)
            intraday_match = dealer_intraday_selection[
                dealer_intraday_selection.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)
                & dealer_intraday_selection.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str).eq(decision)
            ] if not dealer_intraday_selection.empty else pd.DataFrame()
            if intraday_match.empty:
                add_row(prow, "DealerGammaIntraday", "unavailable_coverage", "unavailable_coverage", False, "unavailable_coverage", "dealer_gamma_intraday_unavailable")
                add_row(prow, "DealerGammaSignIntraday", "unavailable_coverage", "unavailable_coverage", False, "unavailable_coverage", "dealer_gamma_sign_intraday_unavailable")
            else:
                drow = intraday_match.iloc[-1]
                selected = bool(drow.get("primary_eligible", False)) and str(drow.get("selection_status", "")) == "selected"
                gamma_parity = dealer_gamma_source_parity[
                    dealer_gamma_source_parity.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)
                    & dealer_gamma_source_parity.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str).eq(decision)
                    & dealer_gamma_source_parity.get("required_source_family", pd.Series(dtype=str)).astype(str).eq("DealerGammaIntraday")
                ] if dealer_gamma_source_parity is not None and not dealer_gamma_source_parity.empty else pd.DataFrame()
                gamma_parity_status = _aggregate_parity_status(gamma_parity.get("selection_parity_status", pd.Series(dtype=str)).astype(str).tolist()) if not gamma_parity.empty else ("audit_missing" if selected else str(drow.get("availability_state", "unavailable_coverage")))
                gamma_integrity, gamma_reason = _component_integrity_from_status(str(drow.get("selection_status", "unavailable_coverage")), str(drow.get("availability_state", "unavailable_coverage")), selected, gamma_parity_status, str(drow.get("invalid_reason", "")))
                add_row(prow, "DealerGammaIntraday", str(drow.get("selection_status", "unavailable_coverage")), str(drow.get("availability_state", "unavailable_coverage")), selected, gamma_parity_status, str(drow.get("invalid_reason", "")), str(drow.get("selected_source_row_identifier", "")), str(drow.get("selected_source_content_hash", "")), str(drow.get("selected_source_effective_available_at_utc", "")))
                sign_ok = pd.notna(safe_float(drow.get("negative_gamma_proxy_indicator", np.nan)))
                if gamma_integrity == "selected_invalid":
                    add_row(prow, "DealerGammaSignIntraday", "selected_invalid", "selected_invalid", False, "not_applicable", gamma_reason, str(drow.get("selected_source_row_identifier", "")), str(drow.get("selected_source_content_hash", "")), str(drow.get("selected_source_effective_available_at_utc", "")), "derived_from_base_component", "DealerGammaIntraday", gamma_integrity)
                elif gamma_integrity == "unavailable_coverage":
                    add_row(prow, "DealerGammaSignIntraday", "unavailable_coverage", "unavailable_coverage", False, "not_applicable", gamma_reason or "dealer_gamma_intraday_unavailable", str(drow.get("selected_source_row_identifier", "")), str(drow.get("selected_source_content_hash", "")), str(drow.get("selected_source_effective_available_at_utc", "")), "derived_from_base_component", "DealerGammaIntraday", gamma_integrity)
                else:
                    add_row(prow, "DealerGammaSignIntraday", "selected" if sign_ok else "unavailable_coverage", "valid" if sign_ok else "unavailable_coverage", bool(sign_ok), "not_applicable", "" if sign_ok else "gamma_sign_convention_unverified", str(drow.get("selected_source_row_identifier", "")), str(drow.get("selected_source_content_hash", "")), str(drow.get("selected_source_effective_available_at_utc", "")), "derived_from_base_component", "DealerGammaIntraday", gamma_integrity)
    return pd.DataFrame(rows, columns=MARKET_LEVEL_COMPONENT_PROVENANCE_COLUMNS)


def build_market_level_model_scope_integrity(panel_or_provenance: pd.DataFrame, component_provenance: pd.DataFrame | None = None) -> pd.DataFrame:
    spec = market_level_model_spec()
    provenance = component_provenance if component_provenance is not None else panel_or_provenance
    if component_provenance is None and "required_component" not in provenance.columns:
        provenance = build_market_level_component_provenance_status(
            market_level_panel=panel_or_provenance,
            cta_vol_selector_parity=pd.DataFrame(),
            leveraged_selector_parity=pd.DataFrame(),
            leveraged_primary_integrity=pd.DataFrame(),
            dealer_eod_panel=pd.DataFrame(),
            dealer_intraday_selection=pd.DataFrame(),
            dealer_gamma_source_parity=pd.DataFrame(),
        )
    dependencies = market_level_required_components_by_scope()

    rows: list[dict[str, Any]] = []
    if provenance.empty:
        return pd.DataFrame(columns=MARKET_LEVEL_SCOPE_INTEGRITY_COLUMNS)
    for keys, group in provenance.groupby(["target_market", "decision_timestamp_utc", "model_clock"], dropna=False):
        target, decision, clock = keys
        scopes = spec["eod_models"] if clock == "EOD" else spec["intraday_models"] if clock == "INTRADAY" else {}
        for scope in scopes.keys():
            comp_rows = []
            for comp in dependencies.get(scope, ["baseline"]):
                match = group[group["required_component"].astype(str).eq(comp)]
                if match.empty:
                    comp_rows.append({
                        "required_component": comp,
                        "integrity_status": "unavailable_coverage",
                        "integrity_reason": f"{comp}_provenance_missing",
                        "source_parity_status": "unavailable_coverage",
                    })
                else:
                    comp_rows.append(match.iloc[-1].to_dict())
            statuses = [str(r.get("integrity_status", "")) for r in comp_rows]
            if "selected_invalid" in statuses:
                scope_status = "selected_invalid"
            elif "unavailable_coverage" in statuses:
                scope_status = "unavailable_coverage"
            else:
                scope_status = "valid"
            reasons = ";".join(sorted(set(str(r.get("integrity_reason", "")) for r in comp_rows if str(r.get("integrity_reason", "")))))
            for comp_row in comp_rows:
                rows.append({
                    "target_market": target,
                    "decision_timestamp_utc": decision,
                    "model_clock": clock,
                    "model_scope": scope,
                    "required_component": comp_row.get("required_component", ""),
                    "component_integrity_status": comp_row.get("integrity_status", ""),
                    "component_integrity_reason": comp_row.get("integrity_reason", ""),
                    "source_parity_status": comp_row.get("source_parity_status", ""),
                    "scope_integrity_status": scope_status,
                    "scope_integrity_failure_reason": reasons,
                })
    return pd.DataFrame(rows, columns=MARKET_LEVEL_SCOPE_INTEGRITY_COLUMNS)


def market_level_required_components_by_scope() -> dict[str, list[str]]:
    return {
        "B0": ["baseline"],
        "B1": ["baseline", "CTA"],
        "B2": ["baseline", "VolControl"],
        "B3": ["baseline", "CTA", "VolControl"],
        "B4": ["baseline", "CTA", "VolControl", "DealerGammaEOD", "DealerGammaSignEOD"],
        "B5": ["baseline", "CTA", "VolControl", "DealerGammaEOD", "DealerGammaSignEOD"],
        "C0": ["baseline"],
        "C1": ["baseline", "LeveragedETF"],
        "C2": ["baseline", "LeveragedETF", "DealerGammaIntraday", "DealerGammaSignIntraday"],
        "C3": ["baseline", "LeveragedETF", "DealerGammaIntraday", "DealerGammaSignIntraday"],
    }

def canonicalize_market_level_decision_universe(universe: pd.DataFrame, *, model_clock: str, required_columns: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    canonical_columns = list(dict.fromkeys(required_columns + MARKET_LEVEL_DECISION_UNIVERSE_INTEGRITY_COLUMNS))
    if universe is None:
        raise ValueError("explicit decision universe is required")
    if universe.empty:
        return (
            ensure_columns(pd.DataFrame(), canonical_columns),
            pd.DataFrame(columns=MARKET_LEVEL_DECISION_UNIVERSE_INTEGRITY_COLUMNS),
        )
    work = ensure_columns(universe.copy(), required_columns)
    work["model_clock"] = model_clock
    work["_target_key"] = work.get("target_market", pd.Series(dtype=str)).astype(str)
    work["_clock_key"] = work.get("model_clock", pd.Series(dtype=str)).astype(str)
    work["_decision_key"] = work.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str)
    invalid_mask = (
        work["_target_key"].str.strip().eq("")
        | work["_clock_key"].str.strip().eq("")
        | work["_decision_key"].str.strip().eq("")
        | pd.to_datetime(work["_decision_key"], utc=True, errors="coerce").isna()
    )
    rows: list[dict[str, Any]] = []
    canonical_rows: list[dict[str, Any]] = []
    for key, group in work.groupby(["_target_key", "_clock_key", "_decision_key"], dropna=False):
        target, clock, decision = key
        raw_count = len(group)
        duplicate = raw_count > 1
        invalid_key = bool(invalid_mask.loc[group.index].any())
        compare_cols = [
            c for c in [
                "decision_date",
                "intraday_outcome_availability_status",
                "intraday_outcome_availability_reason",
                "next_session_return",
                "forward_return_3d",
                "forward_return_5d",
                "forward_realized_vol_5d",
                "intraday_return_1530_to_close",
                "intraday_absolute_return_1530_to_close",
                "intraday_range_1530_to_close",
            ] if c in group.columns
        ]
        conflict = False
        if duplicate and compare_cols:
            conflict = len(group[compare_cols].astype(str).drop_duplicates()) > 1
        status = "valid"
        reasons = []
        if invalid_key:
            status = "selected_invalid"
            reasons.append("invalid_decision_universe_key")
        if duplicate:
            status = "selected_invalid"
            reasons.append("duplicate_decision_universe_key")
            if conflict:
                reasons.append("duplicate_metadata_conflict")
        audit_row = {
            "target_market": target,
            "model_clock": clock,
            "decision_timestamp_utc": decision,
            "raw_universe_row_count": raw_count,
            "canonical_universe_row_count": 1,
            "duplicate_detected": duplicate,
            "duplicate_metadata_conflict_detected": conflict,
            "universe_key_integrity_status": status,
            "universe_key_integrity_reason": ";".join(reasons),
        }
        rows.append(audit_row)
        canonical = group.iloc[0].drop(labels=[c for c in group.columns if str(c).startswith("_")], errors="ignore").to_dict()
        canonical.update(audit_row)
        canonical_rows.append(canonical)
    canonical_df = ensure_columns(pd.DataFrame(canonical_rows), canonical_columns)
    audit_df = pd.DataFrame(rows, columns=MARKET_LEVEL_DECISION_UNIVERSE_INTEGRITY_COLUMNS)
    return canonical_df, audit_df


def build_market_level_target_clock_gate_audit(
    eod_decision_universe: pd.DataFrame,
    intraday_decision_universe: pd.DataFrame,
    intraday_universe_gate_audit: pd.DataFrame,
) -> pd.DataFrame:
    spec = market_level_model_spec()
    rows: list[dict[str, Any]] = []
    outcome_map = {
        "EOD": ["next_session_return", "forward_return_3d", "forward_return_5d", "forward_realized_vol_5d"],
        "INTRADAY": ["intraday_return_1530_to_close", "intraday_absolute_return_1530_to_close", "intraday_range_1530_to_close"],
    }
    for target in spec["targets"]:
        eod_count = int(eod_decision_universe.get("target_market", pd.Series(dtype=str)).astype(str).eq(target).sum()) if not eod_decision_universe.empty else 0
        for model_scope in spec["eod_models"].keys():
            for outcome in outcome_map["EOD"]:
                rows.append({
                    "target_market": target,
                    "model_clock": "EOD",
                    "model_scope": model_scope,
                    "outcome": outcome,
                    "target_clock_gate_status": "valid" if eod_count else "unavailable_coverage",
                    "target_clock_gate_reason": "" if eod_count else "eod_decision_universe_empty",
                    "candidate_decision_count": eod_count,
                    "universe_gate_selected_invalid_count": 0,
                    "universe_gate_unavailable_coverage_count": 0 if eod_count else 1,
                })
        gate = intraday_universe_gate_audit[
            intraday_universe_gate_audit.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)
        ] if intraday_universe_gate_audit is not None and not intraday_universe_gate_audit.empty else pd.DataFrame()
        canonical_intraday_count = int(intraday_decision_universe.get("target_market", pd.Series(dtype=str)).astype(str).eq(target).sum()) if intraday_decision_universe is not None and not intraday_decision_universe.empty else 0
        if gate.empty:
            gate_status = "unavailable_coverage"
            gate_reason = "intraday_universe_gate_missing"
            selected_invalid_count = 0
            unavailable_count = 1
            candidate_count = canonical_intraday_count
        else:
            grow = gate.iloc[-1]
            gate_status = str(grow.get("target_clock_gate_integrity_status", "unavailable_coverage"))
            gate_reason = str(grow.get("target_clock_gate_reason", grow.get("universe_generation_reason", "")))
            selected_invalid_count = int(gate_status == "selected_invalid")
            unavailable_count = int(gate_status == "unavailable_coverage")
            candidate_count = canonical_intraday_count
        for model_scope in spec["intraday_models"].keys():
            for outcome in outcome_map["INTRADAY"]:
                rows.append({
                    "target_market": target,
                    "model_clock": "INTRADAY",
                    "model_scope": model_scope,
                    "outcome": outcome,
                    "target_clock_gate_status": gate_status,
                    "target_clock_gate_reason": gate_reason,
                    "candidate_decision_count": candidate_count,
                    "universe_gate_selected_invalid_count": selected_invalid_count,
                    "universe_gate_unavailable_coverage_count": unavailable_count,
                })
    return pd.DataFrame(rows, columns=MARKET_LEVEL_TARGET_CLOCK_GATE_COLUMNS)


def classify_market_level_decision_buckets(
    *,
    canonical_eod_decision_universe: pd.DataFrame,
    canonical_intraday_decision_universe: pd.DataFrame,
    universe_integrity_audit: pd.DataFrame,
    intraday_universe_gate_audit: pd.DataFrame,
    market_level_panel: pd.DataFrame,
    market_level_scope_integrity: pd.DataFrame,
    model_spec: dict[str, Any],
    base_cfg: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    buckets = build_market_level_decision_bucket_audit(
        canonical_eod_decision_universe=canonical_eod_decision_universe,
        canonical_intraday_decision_universe=canonical_intraday_decision_universe,
        universe_integrity_audit=universe_integrity_audit,
        market_level_panel=market_level_panel,
        market_level_scope_integrity=market_level_scope_integrity,
        model_spec=model_spec,
        base_cfg=base_cfg,
    )
    gates = build_market_level_target_clock_gate_audit(canonical_eod_decision_universe, canonical_intraday_decision_universe, intraday_universe_gate_audit)
    return buckets, gates


def run_market_level_oos_backtest(
    panel: pd.DataFrame,
    decision_bucket_audit: pd.DataFrame,
    target_clock_gate_audit: pd.DataFrame,
    universe_coverage_reconciliation: pd.DataFrame,
    cfg: dict[str, Any],
    base_cfg: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    _require_columns(
        decision_bucket_audit,
        ["target_market", "decision_timestamp_utc", "model_clock", "model_scope", "outcome", "candidate_in_universe_flag", "bucket"],
        "decision bucket artifact required",
    )
    _require_columns(
        target_clock_gate_audit,
        [
            "target_market", "model_clock", "model_scope", "outcome", "target_clock_gate_status",
            "target_clock_gate_reason", "candidate_decision_count", "universe_gate_selected_invalid_count",
            "universe_gate_unavailable_coverage_count",
        ],
        "target clock gate artifact required",
    )
    _require_columns(
        universe_coverage_reconciliation,
        [
            "target_market", "model_clock", "decision_timestamp_utc", "model_scope", "outcome",
            "coverage_reconciliation_status", "coverage_reconciliation_reason",
        ],
        "universe coverage reconciliation artifact required",
    )
    spec = market_level_model_spec()
    metric_rows: list[dict[str, Any]] = []
    pred_rows: list[dict[str, Any]] = []
    coef_rows_all: list[dict[str, Any]] = []
    fold_audit_rows: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    regime_rows: list[dict[str, Any]] = []
    eod_outcomes = ["next_session_return", "forward_return_3d", "forward_return_5d", "forward_realized_vol_5d"]
    intraday_outcomes = ["intraday_return_1530_to_close", "intraday_absolute_return_1530_to_close", "intraday_range_1530_to_close"]
    min_oos = int(spec["minimum_valid_oos_observations"])
    min_folds = int(spec["minimum_non_empty_oos_folds"])
    work = panel.copy()
    model_lookup = {**spec["eod_models"], **spec["intraday_models"]}
    for clock, models, outcomes, baseline_cols, policy in [
        ("EOD", spec["eod_models"], eod_outcomes, base_cfg.get("daily", []), "eod_regular_close_v1"),
        ("INTRADAY", spec["intraday_models"], intraday_outcomes, base_cfg.get("intraday", []), "intraday_1530_et_v1"),
    ]:
        clock_panel = work[work.get("model_clock", pd.Series(dtype=str)).astype(str).eq(clock)].copy() if not work.empty else pd.DataFrame()
        for target in spec["targets"]:
            target_panel = clock_panel[clock_panel.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)].copy() if not clock_panel.empty else pd.DataFrame()
            for model_name, model in models.items():
                features = list(model.get("features", []))
                parent_name = str(model.get("parent", ""))
                parent_features = list(model_lookup.get(parent_name, {}).get("features", [])) if parent_name else []
                for outcome in outcomes:
                    gate_match = target_clock_gate_audit[
                        target_clock_gate_audit.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)
                        & target_clock_gate_audit.get("model_scope", pd.Series(dtype=str)).astype(str).eq(model_name)
                        & target_clock_gate_audit.get("model_clock", pd.Series(dtype=str)).astype(str).eq(clock)
                        & target_clock_gate_audit.get("outcome", pd.Series(dtype=str)).astype(str).eq(outcome)
                    ] if target_clock_gate_audit is not None and not target_clock_gate_audit.empty else pd.DataFrame()
                    if gate_match.empty:
                        universe_gate_selected_invalid_count = 1
                        universe_gate_unavailable_coverage_count = 0
                        target_clock_gate_status = "audit_missing"
                        target_clock_gate_reason = "required_target_clock_gate_row_missing"
                    else:
                        gate_row = gate_match.iloc[-1]
                        universe_gate_selected_invalid_count = int(safe_float(gate_row.get("universe_gate_selected_invalid_count", 0), 0))
                        universe_gate_unavailable_coverage_count = int(safe_float(gate_row.get("universe_gate_unavailable_coverage_count", 0), 0))
                        target_clock_gate_status = str(gate_row.get("target_clock_gate_status", "audit_missing"))
                        target_clock_gate_reason = str(gate_row.get("target_clock_gate_reason", ""))

                    bucket_rows = decision_bucket_audit[
                        decision_bucket_audit.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)
                        & decision_bucket_audit.get("model_scope", pd.Series(dtype=str)).astype(str).eq(model_name)
                        & decision_bucket_audit.get("model_clock", pd.Series(dtype=str)).astype(str).eq(clock)
                        & decision_bucket_audit.get("outcome", pd.Series(dtype=str)).astype(str).eq(outcome)
                    ].copy()
                    candidate_decisions = set(bucket_rows.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str).tolist())
                    candidate_count = len(candidate_decisions)
                    invalid_decisions = set(bucket_rows[bucket_rows.get("bucket", pd.Series(dtype=str)).astype(str).eq("selected_invalid")]["decision_timestamp_utc"].astype(str).tolist()) if not bucket_rows.empty else set()
                    unavailable_decisions = set(bucket_rows[bucket_rows.get("bucket", pd.Series(dtype=str)).astype(str).eq("scope_unavailable_coverage")]["decision_timestamp_utc"].astype(str).tolist()) if not bucket_rows.empty else set()
                    outcome_unavailable_decisions = set(bucket_rows[bucket_rows.get("bucket", pd.Series(dtype=str)).astype(str).eq("outcome_unavailable")]["decision_timestamp_utc"].astype(str).tolist()) if not bucket_rows.empty else set()
                    feature_numeric_unavailable_decisions = set(bucket_rows[bucket_rows.get("bucket", pd.Series(dtype=str)).astype(str).eq("feature_numeric_unavailable")]["decision_timestamp_utc"].astype(str).tolist()) if not bucket_rows.empty else set()
                    valid_included_decisions = set(bucket_rows[bucket_rows.get("bucket", pd.Series(dtype=str)).astype(str).eq("valid_included")]["decision_timestamp_utc"].astype(str).tolist()) if not bucket_rows.empty else set()
                    valid_frame = target_panel[target_panel.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str).isin(valid_included_decisions)].copy() if not target_panel.empty else pd.DataFrame()
                    valid_frame_decisions = set(valid_frame.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str).tolist()) if not valid_frame.empty else set()
                    missing_valid_panel_decisions = valid_included_decisions - valid_frame_decisions
                    coverage_rows = universe_coverage_reconciliation[
                        universe_coverage_reconciliation.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)
                        & universe_coverage_reconciliation.get("model_scope", pd.Series(dtype=str)).astype(str).eq(model_name)
                        & universe_coverage_reconciliation.get("model_clock", pd.Series(dtype=str)).astype(str).eq(clock)
                        & universe_coverage_reconciliation.get("outcome", pd.Series(dtype=str)).astype(str).eq(outcome)
                    ].copy()
                    if coverage_rows.empty and candidate_count:
                        coverage_mismatch_decisions = {"__coverage_row_missing__"}
                        coverage_mismatch_count = 1
                        coverage_reconciliation_mismatch_reasons = "required_universe_coverage_reconciliation_row_missing"
                    else:
                        mismatch_rows = coverage_rows[
                            ~coverage_rows.get("coverage_reconciliation_status", pd.Series(dtype=str)).astype(str).eq("matched")
                        ].copy() if not coverage_rows.empty else pd.DataFrame()
                        coverage_mismatch_decisions = set(mismatch_rows.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str).tolist()) if not mismatch_rows.empty else set()
                        coverage_mismatch_count = len(coverage_mismatch_decisions)
                        coverage_reconciliation_mismatch_reasons = ";".join(sorted(set(mismatch_rows.get("coverage_reconciliation_reason", pd.Series(dtype=str)).astype(str).tolist()))) if not mismatch_rows.empty else ""
                    reconciliation_total = (
                        len(invalid_decisions)
                        + len(unavailable_decisions)
                        + len(outcome_unavailable_decisions)
                        + len(feature_numeric_unavailable_decisions)
                        + len(valid_included_decisions)
                    )
                    reconciliation_gap = candidate_count - reconciliation_total
                    reconciliation_status = "matched" if reconciliation_gap == 0 else "mismatch"
                    result_status = "data_quality_blocked" if invalid_decisions or universe_gate_selected_invalid_count or missing_valid_panel_decisions or coverage_mismatch_count else "insufficient_data"
                    tested_folds = 0
                    oos_n = 0
                    oos_r2 = np.nan
                    parent_oos_r2 = np.nan
                    incremental_r2 = np.nan
                    mse = np.nan
                    parent_mse = np.nan
                    delta_mse = np.nan
                    mae = np.nan
                    parent_mae = np.nan
                    delta_mae = np.nan
                    coef_median = np.nan
                    sign_consistency = np.nan
                    coef_dispersion = np.nan
                    interaction_summary = ""
                    if not invalid_decisions and not missing_valid_panel_decisions and coverage_mismatch_count == 0 and universe_gate_selected_invalid_count == 0 and len(valid_frame) >= min_oos:
                        preds, folds, coefs = market_level_paired_walk_forward(valid_frame, outcome, parent_name, model_name, clock, baseline_cols, parent_features, features, cfg)
                        tested_folds = int(folds.get("fold_status", pd.Series(dtype=str)).astype(str).eq("tested").sum()) if not folds.empty else 0
                        oos_n = len(preds)
                        if oos_n >= min_oos and tested_folds >= min_folds:
                            y = pd.to_numeric(preds["y_true"], errors="coerce")
                            pred = pd.to_numeric(preds["augmented_pred"], errors="coerce")
                            parent_pred = pd.to_numeric(preds["parent_pred"], errors="coerce")
                            hist = pd.to_numeric(preds["historical_mean_pred"], errors="coerce")
                            sse = float(((y - pred) ** 2).sum())
                            parent_sse = float(((y - parent_pred) ** 2).sum())
                            sst = float(((y - hist) ** 2).sum())
                            oos_r2 = 1 - sse / sst if sst else np.nan
                            parent_oos_r2 = 1 - parent_sse / sst if sst else np.nan
                            incremental_r2 = 1 - sse / parent_sse if parent_sse > 0 else np.nan
                            mse = float(((y - pred) ** 2).mean())
                            parent_mse = float(((y - parent_pred) ** 2).mean())
                            delta_mse = mse - parent_mse
                            mae = float((y - pred).abs().mean())
                            parent_mae = float((y - parent_pred).abs().mean())
                            delta_mae = mae - parent_mae
                            model_feature_coefs = coefs[coefs.get("feature_name", pd.Series(dtype=str)).astype(str).isin(features)] if not coefs.empty else pd.DataFrame()
                            coef_values = pd.to_numeric(model_feature_coefs.get("standardized_coefficient", pd.Series(dtype=float)), errors="coerce").dropna()
                            if not coef_values.empty:
                                coef_median = float(coef_values.median())
                                median_sign = int(np.sign(coef_median))
                                sign_consistency = float((np.sign(coef_values) == median_sign).mean()) if median_sign else np.nan
                                coef_dispersion = float(coef_values.std(ddof=0))
                            interaction_cols = [c for c in ["systematic_sell_pressure_x_negative_gamma", "leveraged_sell_pressure_x_negative_gamma"] if c in features]
                            if interaction_cols and not coefs.empty:
                                ivals = pd.to_numeric(coefs[coefs["feature_name"].isin(interaction_cols)]["standardized_coefficient"], errors="coerce").dropna()
                                if not ivals.empty:
                                    interaction_summary = f"median={float(ivals.median()):.8g};dispersion_std={float(ivals.std(ddof=0)):.8g};folds={len(ivals)}"
                            result_status = "valid"
                            pred_rows.extend(preds.to_dict("records"))
                        fold_audit_rows.extend(folds.to_dict("records"))
                        coef_rows_all.extend(coefs.to_dict("records"))
                    metric_rows.append({
                        "result_status": result_status,
                        "target_market": target,
                        "outcome": outcome,
                        "model_scope": model_name,
                        "model_clock": clock,
                        "candidate_decision_count": candidate_count,
                        "valid_included_decision_count": len(valid_included_decisions),
                        "valid_oos_observation_count": oos_n,
                        "unavailable_coverage_exclusion_count": len(unavailable_decisions),
                        "scope_unavailable_coverage_exclusion_count": len(unavailable_decisions),
                        "outcome_unavailable_exclusion_count": len(outcome_unavailable_decisions),
                        "feature_numeric_unavailable_exclusion_count": len(feature_numeric_unavailable_decisions),
                        "selected_invalid_exclusion_count": len(invalid_decisions),
                        "universe_gate_selected_invalid_count": universe_gate_selected_invalid_count,
                        "universe_gate_unavailable_coverage_count": universe_gate_unavailable_coverage_count,
                        "target_clock_gate_status": target_clock_gate_status,
                        "target_clock_gate_reason": target_clock_gate_reason,
                        "coverage_reconciliation_mismatch_count": coverage_mismatch_count,
                        "coverage_reconciliation_mismatch_decision_timestamps": ";".join(sorted(coverage_mismatch_decisions)[:50]),
                        "coverage_reconciliation_mismatch_reasons": coverage_reconciliation_mismatch_reasons,
                        "reconciliation_total": reconciliation_total,
                        "reconciliation_gap": reconciliation_gap,
                        "reconciliation_status": reconciliation_status,
                        "affected_decision_timestamps": ";".join(sorted(invalid_decisions | missing_valid_panel_decisions | coverage_mismatch_decisions)[:50]),
                        "oos_fold_count": tested_folds,
                        "oos_r_squared_vs_historical_mean": oos_r2,
                        "parent_oos_r_squared_vs_historical_mean": parent_oos_r2,
                        "incremental_oos_r_squared_vs_parent": incremental_r2,
                        "oos_mse": mse,
                        "parent_oos_mse": parent_mse,
                        "delta_oos_mse_vs_parent": delta_mse,
                        "oos_mae": mae,
                        "parent_oos_mae": parent_mae,
                        "delta_oos_mae_vs_parent": delta_mae,
                        "directional_hit_rate": np.nan,
                        "coefficient_median_across_folds": coef_median,
                        "coefficient_sign_consistency": sign_consistency,
                        "coefficient_fold_dispersion": coef_dispersion,
                        "coefficient_dispersion_method": "std_ddof0",
                        "interaction_coefficient_summary": interaction_summary,
                        "feature_availability_rate": len(valid_included_decisions) / max(candidate_count, 1),
                        "decision_time_policy": policy,
                        "source_provenance_policy_revision": MARKET_LEVEL_INTEGRITY_REVISION,
                    })
                    quality_rows.append({
                        "target_market": target,
                        "model_scope": model_name,
                        "outcome": outcome,
                        "candidate_decision_count": candidate_count,
                        "valid_included_decision_count": len(valid_included_decisions),
                        "unavailable_coverage_exclusion_count": len(unavailable_decisions),
                        "scope_unavailable_coverage_exclusion_count": len(unavailable_decisions),
                        "outcome_unavailable_exclusion_count": len(outcome_unavailable_decisions),
                        "feature_numeric_unavailable_exclusion_count": len(feature_numeric_unavailable_decisions),
                        "selected_invalid_exclusion_count": len(invalid_decisions),
                        "universe_gate_selected_invalid_count": universe_gate_selected_invalid_count,
                        "universe_gate_unavailable_coverage_count": universe_gate_unavailable_coverage_count,
                        "target_clock_gate_status": target_clock_gate_status,
                        "target_clock_gate_reason": target_clock_gate_reason,
                        "coverage_reconciliation_mismatch_count": coverage_mismatch_count,
                        "coverage_reconciliation_mismatch_decision_timestamps": ";".join(sorted(coverage_mismatch_decisions)[:50]),
                        "coverage_reconciliation_mismatch_reasons": coverage_reconciliation_mismatch_reasons,
                        "reconciliation_total": reconciliation_total,
                        "reconciliation_gap": reconciliation_gap,
                        "reconciliation_status": reconciliation_status,
                        "result_status": result_status,
                    })
    metrics = pd.DataFrame(metric_rows)
    if not metrics.empty:
        for _, row in metrics.iterrows():
            model_def = spec["eod_models"].get(row["model_scope"], spec["intraday_models"].get(row["model_scope"], {}))
            parent = model_def.get("parent", "")
            comparison_rows.append({
                "target_market": row["target_market"],
                "outcome": row["outcome"],
                "model_scope": row["model_scope"],
                "parent_model_scope": parent,
                "result_status": row["result_status"],
                "incremental_oos_r_squared_vs_parent": row.get("incremental_oos_r_squared_vs_parent", np.nan),
                "delta_oos_mse_vs_parent": row.get("delta_oos_mse_vs_parent", np.nan),
                "delta_oos_mae_vs_parent": row.get("delta_oos_mae_vs_parent", np.nan),
                "feature_availability_difference": np.nan,
                "interpretation_caveat": "predictive association / incremental OOS fit only; not causal attribution",
            })
    regime_rows.append({"regime_partition": "positive_vs_negative_gamma_proxy", "status": "not_run_if_insufficient_data", "threshold_policy": "predeclared_proxy_state_only"})
    pred_cols = ["target_market", "model_scope", "parent_model_scope", "outcome", "model_clock", "row_index", "decision_timestamp_utc", "test_month", "y_true", "parent_pred", "augmented_pred", "historical_mean_pred"]
    coef_cols = ["target_market", "model_scope", "parent_model_scope", "model_clock", "outcome", "test_month", "feature_name", "standardized_coefficient", "coefficient_sign", "sample_count_train", "sample_count_oos", "fold_status"]
    fold_cols = ["target_market", "model_scope", "parent_model_scope", "outcome", "model_clock", "test_month", "sample_count_train", "sample_count_oos", "unseen_category_count", "fold_status"]
    metric_cols = ["result_status", "target_market", "outcome", "model_scope", "model_clock", "candidate_decision_count", "valid_included_decision_count", "valid_oos_observation_count", "unavailable_coverage_exclusion_count", "scope_unavailable_coverage_exclusion_count", "outcome_unavailable_exclusion_count", "feature_numeric_unavailable_exclusion_count", "selected_invalid_exclusion_count", "universe_gate_selected_invalid_count", "universe_gate_unavailable_coverage_count", "target_clock_gate_status", "target_clock_gate_reason", "coverage_reconciliation_mismatch_count", "coverage_reconciliation_mismatch_decision_timestamps", "coverage_reconciliation_mismatch_reasons", "reconciliation_total", "reconciliation_gap", "reconciliation_status", "affected_decision_timestamps", "oos_fold_count", "oos_r_squared_vs_historical_mean", "parent_oos_r_squared_vs_historical_mean", "incremental_oos_r_squared_vs_parent", "oos_mse", "parent_oos_mse", "delta_oos_mse_vs_parent", "oos_mae", "parent_oos_mae", "delta_oos_mae_vs_parent", "directional_hit_rate", "coefficient_median_across_folds", "coefficient_sign_consistency", "coefficient_fold_dispersion", "coefficient_dispersion_method", "interaction_coefficient_summary", "feature_availability_rate", "decision_time_policy", "source_provenance_policy_revision"]
    comp_cols = ["target_market", "outcome", "model_scope", "parent_model_scope", "result_status", "incremental_oos_r_squared_vs_parent", "delta_oos_mse_vs_parent", "delta_oos_mae_vs_parent", "feature_availability_difference", "interpretation_caveat"]
    regime_cols = ["regime_partition", "status", "threshold_policy"]
    quality_cols = ["target_market", "model_scope", "outcome", "candidate_decision_count", "valid_included_decision_count", "unavailable_coverage_exclusion_count", "scope_unavailable_coverage_exclusion_count", "outcome_unavailable_exclusion_count", "feature_numeric_unavailable_exclusion_count", "selected_invalid_exclusion_count", "universe_gate_selected_invalid_count", "universe_gate_unavailable_coverage_count", "target_clock_gate_status", "target_clock_gate_reason", "coverage_reconciliation_mismatch_count", "coverage_reconciliation_mismatch_decision_timestamps", "coverage_reconciliation_mismatch_reasons", "reconciliation_total", "reconciliation_gap", "reconciliation_status", "result_status"]
    return (
        pd.DataFrame(pred_rows, columns=pred_cols),
        pd.DataFrame(coef_rows_all, columns=coef_cols),
        pd.DataFrame(fold_audit_rows, columns=fold_cols),
        pd.DataFrame(metric_rows, columns=metric_cols),
        pd.DataFrame(comparison_rows, columns=comp_cols),
        pd.DataFrame(regime_rows, columns=regime_cols),
        pd.DataFrame(quality_rows, columns=quality_cols),
    )


def build_market_level_decision_bucket_audit(
    *,
    canonical_eod_decision_universe: pd.DataFrame,
    canonical_intraday_decision_universe: pd.DataFrame,
    universe_integrity_audit: pd.DataFrame,
    market_level_panel: pd.DataFrame,
    market_level_scope_integrity: pd.DataFrame,
    model_spec: dict[str, Any] | None = None,
    base_cfg: dict[str, Any],
) -> pd.DataFrame:
    spec = model_spec or market_level_model_spec()
    rows: list[dict[str, Any]] = []
    configs = [
        ("EOD", canonical_eod_decision_universe, spec["eod_models"], ["next_session_return", "forward_return_3d", "forward_return_5d", "forward_realized_vol_5d"], base_cfg.get("daily", [])),
        ("INTRADAY", canonical_intraday_decision_universe, spec["intraday_models"], ["intraday_return_1530_to_close", "intraday_absolute_return_1530_to_close", "intraday_range_1530_to_close"], base_cfg.get("intraday", [])),
    ]
    for clock, universe, models, outcomes, baseline_cols in configs:
        if universe is None or universe.empty:
            continue
        universe_work = universe.copy()
        if "model_clock" not in universe_work.columns:
            universe_work["model_clock"] = clock
        universe_work = universe_work[
            universe_work.get("model_clock", pd.Series(dtype=str)).astype(str).eq(clock)
            & universe_work.get("target_market", pd.Series(dtype=str)).astype(str).isin(spec["targets"])
        ].copy()
        if universe_work.empty:
            continue
        universe_work["_decision_key"] = universe_work.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str)
        clock_panel = market_level_panel[market_level_panel.get("model_clock", pd.Series(dtype=str)).astype(str).eq(clock)].copy() if not market_level_panel.empty else pd.DataFrame()
        if not clock_panel.empty:
            clock_panel["_decision_key"] = clock_panel.get("decision_timestamp_utc", pd.Series(dtype=str)).astype(str)
        for target in spec["targets"]:
            target_universe = universe_work[universe_work.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)].copy()
            if target_universe.empty:
                continue
            target_panel = clock_panel[clock_panel.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)].copy() if not clock_panel.empty else pd.DataFrame()
            for model_name, model in models.items():
                features = list(model.get("features", []))
                scope_rows = market_level_scope_integrity[
                    market_level_scope_integrity.get("target_market", pd.Series(dtype=str)).astype(str).eq(target)
                    & market_level_scope_integrity.get("model_scope", pd.Series(dtype=str)).astype(str).eq(model_name)
                    & market_level_scope_integrity.get("model_clock", pd.Series(dtype=str)).astype(str).eq(clock)
                ] if not market_level_scope_integrity.empty else pd.DataFrame()
                status_by_decision: dict[str, str] = {}
                reason_by_decision: dict[str, str] = {}
                if not scope_rows.empty:
                    for decision_key, sg in scope_rows.groupby(scope_rows["decision_timestamp_utc"].astype(str), dropna=False):
                        statuses = sg.get("scope_integrity_status", pd.Series(dtype=str)).astype(str).tolist()
                        reasons = ";".join(sorted(set(sg.get("scope_integrity_failure_reason", pd.Series(dtype=str)).astype(str).tolist())))
                        if "selected_invalid" in statuses:
                            status_by_decision[str(decision_key)] = "selected_invalid"
                        elif "unavailable_coverage" in statuses:
                            status_by_decision[str(decision_key)] = "unavailable_coverage"
                        else:
                            status_by_decision[str(decision_key)] = "valid"
                        reason_by_decision[str(decision_key)] = reasons
                for outcome in outcomes:
                    required_features = list(dict.fromkeys(baseline_cols + features))
                    for _, urow in target_universe.iterrows():
                        decision = str(urow.get("_decision_key", ""))
                        universe_status = str(urow.get("universe_key_integrity_status", "valid"))
                        universe_reason = str(urow.get("universe_key_integrity_reason", ""))
                        duplicate_universe = bool(urow.get("duplicate_detected", False))
                        row_match = target_panel[target_panel.get("_decision_key", pd.Series(dtype=str)).astype(str).eq(decision)] if not target_panel.empty else pd.DataFrame()
                        panel_row_count = len(row_match)
                        panel_row_present = panel_row_count > 0
                        panel_row = row_match.iloc[0] if panel_row_count == 1 else pd.Series(dtype=object)
                        scope_absent = decision not in status_by_decision
                        scope_status = status_by_decision.get(decision, "selected_invalid")
                        scope_reason = reason_by_decision.get(decision, "required_scope_integrity_audit_missing")
                        if clock == "INTRADAY" and str(urow.get("intraday_outcome_availability_status", "")) == "outcome_unavailable":
                            outcome_available = False
                        elif panel_row_count == 1:
                            outcome_available = pd.notna(pd.to_numeric(pd.Series([panel_row.get(outcome, np.nan)]), errors="coerce").iloc[0])
                        else:
                            outcome_available = False
                        missing_features = [
                            col for col in required_features
                            if pd.isna(pd.to_numeric(pd.Series([panel_row.get(col, np.nan)]), errors="coerce").iloc[0])
                        ]
                        panel_absence_reason = "" if panel_row_present else "panel_row_missing_after_universe_join"
                        if universe_status == "selected_invalid":
                            bucket = "selected_invalid"
                            reason = universe_reason or "invalid_decision_universe_key"
                        elif panel_row_count > 1:
                            bucket = "selected_invalid"
                            reason = "duplicate_market_level_panel_rows"
                        elif scope_absent:
                            bucket = "selected_invalid"
                            reason = "required_scope_integrity_audit_missing"
                        elif scope_status == "selected_invalid":
                            bucket = "selected_invalid"
                            reason = ";".join([r for r in [panel_absence_reason, scope_reason] if r])
                        elif scope_status == "unavailable_coverage":
                            bucket = "scope_unavailable_coverage"
                            reason = ";".join([r for r in [panel_absence_reason, scope_reason] if r])
                        elif not panel_row_present:
                            bucket = "feature_numeric_unavailable"
                            reason = panel_absence_reason
                        elif not outcome_available:
                            bucket = "outcome_unavailable"
                            reason = str(urow.get("intraday_outcome_availability_reason", "")) if clock == "INTRADAY" else f"{outcome}_missing"
                        elif missing_features:
                            bucket = "feature_numeric_unavailable"
                            reason = "missing_numeric_features:" + ",".join(missing_features)
                        else:
                            bucket = "valid_included"
                            reason = ""
                        rows.append({
                            "target_market": target,
                            "decision_timestamp_utc": decision,
                            "model_clock": clock,
                            "model_scope": model_name,
                            "outcome": outcome,
                            "candidate_in_universe_flag": True,
                            "bucket": bucket,
                            "bucket_reason": reason,
                            "scope_integrity_status": scope_status,
                            "outcome_availability_status": "available" if outcome_available else "outcome_unavailable",
                            "numeric_feature_availability_status": "available" if not missing_features else "feature_numeric_unavailable",
                            "missing_numeric_features": ",".join(missing_features),
                            "panel_row_present": bool(panel_row_present),
                            "panel_row_count": panel_row_count,
                            "panel_row_absence_reason": panel_absence_reason,
                            "universe_key_integrity_status": universe_status,
                            "universe_key_integrity_reason": universe_reason,
                            "duplicate_universe_key_detected": duplicate_universe,
                            "oos_bucket_policy": MARKET_LEVEL_OOS_BUCKET_POLICY,
                        })
    return pd.DataFrame(rows, columns=MARKET_LEVEL_DECISION_BUCKET_COLUMNS)


def build_market_level_universe_coverage_reconciliation(
    canonical_eod_decision_universe: pd.DataFrame,
    canonical_intraday_decision_universe: pd.DataFrame,
    universe_integrity_audit: pd.DataFrame,
    market_level_panel: pd.DataFrame,
    market_level_component_provenance: pd.DataFrame,
    market_level_scope_integrity: pd.DataFrame,
    market_level_decision_bucket_audit: pd.DataFrame,
    model_spec: dict[str, Any] | None = None,
) -> pd.DataFrame:
    spec = model_spec or market_level_model_spec()
    required_by_scope = market_level_required_components_by_scope()
    universe_parts = []
    if canonical_eod_decision_universe is not None and not canonical_eod_decision_universe.empty:
        eod = canonical_eod_decision_universe.copy()
        eod["model_clock"] = "EOD"
        universe_parts.append(eod)
    if canonical_intraday_decision_universe is not None and not canonical_intraday_decision_universe.empty:
        intraday = canonical_intraday_decision_universe.copy()
        intraday["model_clock"] = "INTRADAY"
        universe_parts.append(intraday)
    if not universe_parts:
        return pd.DataFrame(columns=MARKET_LEVEL_UNIVERSE_COVERAGE_RECONCILIATION_COLUMNS)
    universe = pd.concat(universe_parts, ignore_index=True, sort=False)
    universe = ensure_columns(universe, [
        "target_market", "model_clock", "decision_timestamp_utc",
        "universe_key_integrity_status", "universe_key_integrity_reason",
    ]).copy()

    if universe_integrity_audit is not None and not universe_integrity_audit.empty:
        audit_cols = [
            "target_market", "model_clock", "decision_timestamp_utc",
            "universe_key_integrity_status", "universe_key_integrity_reason",
        ]
        audit = ensure_columns(universe_integrity_audit, audit_cols)[audit_cols].copy()
        audit = audit.drop_duplicates(["target_market", "model_clock", "decision_timestamp_utc"], keep="last")
        universe = universe.drop(columns=["universe_key_integrity_status", "universe_key_integrity_reason"], errors="ignore").merge(
            audit,
            on=["target_market", "model_clock", "decision_timestamp_utc"],
            how="left",
        )
    universe["universe_key_integrity_status"] = universe.get("universe_key_integrity_status", pd.Series(dtype=str)).replace("", np.nan).fillna("valid")
    universe["universe_key_integrity_reason"] = universe.get("universe_key_integrity_reason", pd.Series(dtype=str)).fillna("")

    configs = {
        "EOD": (spec["eod_models"], ["next_session_return", "forward_return_3d", "forward_return_5d", "forward_realized_vol_5d"]),
        "INTRADAY": (spec["intraday_models"], ["intraday_return_1530_to_close", "intraday_absolute_return_1530_to_close", "intraday_range_1530_to_close"]),
    }
    def grouped_component_counts(df: pd.DataFrame) -> dict[tuple[str, str, str, str, str], int]:
        needed = ["target_market", "model_clock", "decision_timestamp_utc", "model_scope", "required_component"]
        if df is None or df.empty or not set(needed).issubset(df.columns):
            return {}
        work = df[needed].copy()
        for col in needed:
            work[col] = work[col].astype(str)
        return work.groupby(needed, dropna=False).size().astype(int).to_dict()

    panel_counts: dict[tuple[str, str, str], int] = {}
    if market_level_panel is not None and not market_level_panel.empty and {"target_market", "model_clock", "decision_timestamp_utc"}.issubset(market_level_panel.columns):
        pwork = market_level_panel[["target_market", "model_clock", "decision_timestamp_utc"]].copy()
        for col in pwork.columns:
            pwork[col] = pwork[col].astype(str)
        panel_counts = pwork.groupby(["target_market", "model_clock", "decision_timestamp_utc"], dropna=False).size().astype(int).to_dict()

    provenance_counts = grouped_component_counts(market_level_component_provenance)
    scope_counts = grouped_component_counts(market_level_scope_integrity)
    bucket_counts: dict[tuple[str, str, str, str, str], int] = {}
    bucket_values: dict[tuple[str, str, str, str, str], str] = {}
    bucket_needed = ["target_market", "model_clock", "decision_timestamp_utc", "model_scope", "outcome"]
    if market_level_decision_bucket_audit is not None and not market_level_decision_bucket_audit.empty and set(bucket_needed).issubset(market_level_decision_bucket_audit.columns):
        bwork = market_level_decision_bucket_audit[bucket_needed + [c for c in ["bucket"] if c in market_level_decision_bucket_audit.columns]].copy()
        for col in bucket_needed:
            bwork[col] = bwork[col].astype(str)
        bucket_counts = bwork.groupby(bucket_needed, dropna=False).size().astype(int).to_dict()
        for key, group in bwork.groupby(bucket_needed, dropna=False):
            if len(group) == 1:
                bucket_values[tuple(str(v) for v in key)] = str(group.iloc[0].get("bucket", ""))

    rows = []
    for _, row in universe.iterrows():
        target = str(row.get("target_market", ""))
        clock = str(row.get("model_clock", ""))
        decision = str(row.get("decision_timestamp_utc", ""))
        universe_status = str(row.get("universe_key_integrity_status", "valid") or "valid")
        universe_reason = str(row.get("universe_key_integrity_reason", "") or "")
        if clock not in configs:
            continue
        models, outcomes = configs[clock]
        panel_count = int(panel_counts.get((target, clock, decision), 0))
        for model_scope in models.keys():
            expected_components = required_by_scope.get(model_scope, ["baseline"])
            prov_component_counts = {component: int(provenance_counts.get((target, clock, decision, model_scope, component), 0)) for component in expected_components}
            scope_component_counts = {component: int(scope_counts.get((target, clock, decision, model_scope, component), 0)) for component in expected_components}
            missing_prov = [component for component, count in prov_component_counts.items() if count == 0]
            dup_prov = [component for component, count in prov_component_counts.items() if count > 1]
            missing_scope = [component for component, count in scope_component_counts.items() if count == 0]
            dup_scope = [component for component, count in scope_component_counts.items() if count > 1]
            for outcome in outcomes:
                bucket_key = (target, clock, decision, model_scope, outcome)
                bucket_count = int(bucket_counts.get(bucket_key, 0))
                reasons: list[str] = []
                if universe_status != "valid":
                    reasons.append(universe_reason or "duplicate_decision_universe_key")
                if panel_count == 0:
                    reasons.append("panel_row_missing_after_universe_join")
                elif panel_count > 1:
                    reasons.append("duplicate_market_level_panel_rows")
                reasons.extend([f"missing_component_provenance:{component}" for component in missing_prov])
                reasons.extend([f"duplicate_component_provenance:{component}" for component in dup_prov])
                reasons.extend([f"missing_scope_integrity:{component}" for component in missing_scope])
                reasons.extend([f"duplicate_scope_integrity:{component}" for component in dup_scope])
                if bucket_count == 0:
                    reasons.append("missing_decision_bucket_row")
                elif bucket_count > 1:
                    reasons.append("duplicate_decision_bucket_row")
                status = "matched" if not reasons else "mismatch"
                rows.append({
                    "target_market": target,
                    "model_clock": clock,
                    "decision_timestamp_utc": decision,
                    "model_scope": model_scope,
                    "outcome": outcome,
                    "in_canonical_decision_universe": True,
                    "universe_key_integrity_status": universe_status,
                    "universe_key_integrity_reason": universe_reason,
                    "expected_required_components": ",".join(expected_components),
                    "expected_required_component_count": len(expected_components),
                    "actual_provenance_components": ",".join([component for component in expected_components for _ in range(prov_component_counts.get(component, 0))]),
                    "actual_provenance_component_count": int(sum(prov_component_counts.values())),
                    "missing_provenance_components": ",".join(missing_prov),
                    "duplicate_provenance_components": ",".join(dup_prov),
                    "expected_scope_integrity_components": ",".join(expected_components),
                    "actual_scope_integrity_components": ",".join([component for component in expected_components for _ in range(scope_component_counts.get(component, 0))]),
                    "missing_scope_integrity_components": ",".join(missing_scope),
                    "duplicate_scope_integrity_components": ",".join(dup_scope),
                    "market_level_panel_row_count": panel_count,
                    "panel_row_present": panel_count > 0,
                    "panel_row_status": "matched" if panel_count == 1 else ("missing" if panel_count == 0 else "duplicate"),
                    "expected_bucket_row_count": 1,
                    "actual_bucket_row_count": bucket_count,
                    "bucket_row_status": "matched" if bucket_count == 1 else ("missing" if bucket_count == 0 else "duplicate"),
                    "actual_bucket_value": bucket_values.get(bucket_key, "") if bucket_count == 1 else "",
                    "coverage_reconciliation_status": status,
                    "coverage_reconciliation_reason": ";".join(dict.fromkeys([r for r in reasons if r])),
                })
    return pd.DataFrame(rows, columns=MARKET_LEVEL_UNIVERSE_COVERAGE_RECONCILIATION_COLUMNS)


def market_level_report_text(metrics: pd.DataFrame, quality: pd.DataFrame) -> str:
    valid = int(metrics.get("result_status", pd.Series(dtype=str)).astype(str).eq("valid").sum()) if not metrics.empty else 0
    reconciliation_cols = [
        "target_market",
        "model_scope",
        "outcome",
        "candidate_decision_count",
        "selected_invalid_exclusion_count",
        "scope_unavailable_coverage_exclusion_count",
        "outcome_unavailable_exclusion_count",
        "feature_numeric_unavailable_exclusion_count",
        "universe_gate_selected_invalid_count",
        "universe_gate_unavailable_coverage_count",
        "target_clock_gate_status",
        "target_clock_gate_reason",
        "valid_included_decision_count",
        "reconciliation_gap",
        "result_status",
    ]
    reconciliation = metrics[[c for c in reconciliation_cols if c in metrics.columns]].copy() if not metrics.empty else pd.DataFrame(columns=reconciliation_cols)
    return (
        "# Market-Level Market Impact Backtest v1\n\n"
        "actionization_gate=false\n\n"
        "This is research-only. It does not change live scanner, notification, sizing, broker, or execution behavior.\n\n"
        "CTA and VolControl are rule-based proxies, not observed fund flows. Leveraged ETF pressure is an estimated rebalance proxy, not confirmed execution. Dealer Gamma is reconstructed from option-chain assumptions, not observed dealer inventory or hedge flow. Results are associations, not causal attribution.\n\n"
        "Decision universe policy: EOD and intraday MarketLevel panels are built from explicit canonical decision universes only. Intraday universe generation has no business-day fallback when the NYSE calendar is missing or invalid, and an empty intraday universe does not fall back to lev_panel or raw bar rows.\n\n"
        "Decision buckets are enumerated from explicit decision universes, not from panel rows. Panel join misses remain visible in the bucket artifact and cannot silently drop candidates.\n\n"
        "Duplicate target/clock/decision universe keys are canonicalized once for auditability and marked `selected_invalid`; they are not silently deduped into valid candidates.\n\n"
        "Universe coverage reconciliation is target x clock x decision x scope x outcome. It is distinct from decision bucket reconciliation: bucket reconciliation explains candidate inclusion/exclusion, while coverage reconciliation verifies required provenance and scope-integrity artifacts for that exact group.\n\n"
        "Coverage mismatch is a local data-quality block for the affected target/clock/scope/outcome group, not a global block for unrelated groups.\n\n"
        "Actual lineage means an actual feature panel row or actual panel component row, not only a selection audit row. EOD Gamma matched parity accepts actual-lineage records only. Matched source parity requires direct actual-vs-fresh equality. Eligible primary inputs are not treated as matched parity without actual component proof.\n\n"
        "Target-clock calendar gate status is separate from decision buckets and missing target-clock gate evidence is fail-closed. Target/date/scope data-quality failures do not globally block unrelated targets, clocks, or scopes.\n\n"
        "The 16:00 close bar is an outcome requirement, not a Leveraged ETF primary input.\n\n"
        "No coefficient or R-squared interpretation should be made when OOS sufficiency or coverage integrity is not met.\n\n"
        f"OOS bucket policy: `{MARKET_LEVEL_OOS_BUCKET_POLICY}`\n\n"
        f"Valid metric rows: `{valid}`\n\n"
        "## Reconciliation Summary\n\n"
        + markdown_table(reconciliation)
        + "\n\n"
        "## Metrics\n\n"
        + markdown_table(metrics)
        + "\n\n## Data Quality\n\n"
        + markdown_table(quality)
        + "\n\nNext research step, if data coverage supports it, is to join immutable timestamped market features to historical Minervini notifications and test MAE / stop-hit / portfolio-DD policy simulations. That is outside this patch.\n"
    )


def write_reports(
    root: Path,
    cta_oos: pd.DataFrame,
    lev_oos: pd.DataFrame,
    dealer_oos: pd.DataFrame,
    expiry_oos: pd.DataFrame,
    expiry_group_oos: pd.DataFrame,
    source_candidate_summary: pd.DataFrame | None,
    calendar_availability_audit: pd.DataFrame | None,
    provider_bar_semantics_audit: pd.DataFrame | None,
    expiry_group_contrast_folds: pd.DataFrame | None,
    gate: dict[str, Any],
    refresh_rows: list[dict[str, Any]] | None = None,
) -> None:
    reports = root / OUTPUT_ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    def by_test_family(df: pd.DataFrame, value: str) -> pd.DataFrame:
        if df.empty or "test_family" not in df.columns:
            return df.iloc[0:0].copy()
        return df[df["test_family"].astype(str).eq(value)]

    header = (
        "feature is proxy: true\n\n"
        "observed flow: false\n\n"
        "dealer inventory observed: false\n\n"
        f"no-lookahead status: `{gate.get('no_lookahead_status', 'unknown')}`\n\n"
        f"actionization_gate: `{str(gate.get('actionization_gate', False)).lower()}`\n\n"
    )
    (reports / "cta_vol_market_impact_primary.md").write_text(header + markdown_table(cta_oos) + "\n", encoding="utf-8")
    (reports / "leveraged_etf_intraday_impact_primary.md").write_text(header + markdown_table(lev_oos) + "\n", encoding="utf-8")
    (reports / "dealer_gamma_observed_primary.md").write_text(header + markdown_table(dealer_oos) + "\n", encoding="utf-8")
    expiry_report = [
        header,
        "event decision time: `D 09:30 ET`\n\n",
        "strict intraday outcome: `first regular-session bar open -> regular close` when provider bar semantics are verified; early closes excluded from primary.\n\n",
        "## Session-bar semantics / provider validation status\n\n",
        markdown_table(provider_bar_semantics_audit if provider_bar_semantics_audit is not None else pd.DataFrame()),
        "\n\n## Calendar availability contract status\n\n",
        markdown_table(calendar_availability_audit if calendar_availability_audit is not None else pd.DataFrame()),
        "## Calendar-only primary event study\n\n",
        markdown_table(by_test_family(expiry_oos, "dealer_gamma_expiry_calendar_event")),
        "\n\n## Gamma-conditioned primary event study\n\n",
        markdown_table(by_test_family(expiry_oos, "dealer_gamma_expiry_conditioned")),
        "\n\n## Calendar-only / gamma-conditioned group-contrast OOS\n\n",
        markdown_table(expiry_group_oos),
        "\n\n## Group fold exclusions\n\n",
        markdown_table(expiry_group_contrast_folds if expiry_group_contrast_folds is not None else pd.DataFrame()),
        "\n\n## Post-expiry secondary analysis\n\n",
        markdown_table(by_test_family(expiry_oos, "dealer_gamma_expiry_post_event_secondary")),
        "\n\n## Group sample sufficiency\n\n",
        markdown_table(expiry_group_oos),
        "\n\n## Source candidate audit\n\n",
        markdown_table(source_candidate_summary if source_candidate_summary is not None else pd.DataFrame()),
        "\n\nactionization_gate=false\n",
    ]
    (reports / "dealer_gamma_expiry_event_study.md").write_text("".join(expiry_report), encoding="utf-8")
    gamma_status = "not_implemented" if refresh_rows and any(r.get("operation") == "run_gamma_surrogate_exploration" for r in refresh_rows) else "not_run"
    (reports / "gamma_surrogate_exploratory.md").write_text(
        f"status: `{gamma_status}`\n\nfeature is proxy: true\n\nprimary result mixed: false\n\ngamma surrogate is disabled by default and is not a silent no-op.\n",
        encoding="utf-8",
    )
    (reports / "combined_feature_robustness.md").write_text("Combined model is exploratory only and not used for actionization in v1.\n", encoding="utf-8")
    (reports / "data_sufficiency_report.md").write_text(markdown_table(pd.DataFrame([gate])) + "\n", encoding="utf-8")


def gate_audit_text(gate: dict[str, Any]) -> str:
    return (
        "# Market Impact Backtest Gate Audit\n\n"
        f"market_impact_data_gate: `{gate['market_impact_data_gate']}`\n\n"
        f"cta_vol_primary_research_gate: `{gate['cta_vol_primary_research_gate']}`\n\n"
        f"leveraged_etf_primary_research_gate: `{gate['leveraged_etf_primary_research_gate']}`\n\n"
        f"dealer_gamma_primary_research_gate: `{gate['dealer_gamma_primary_research_gate']}`\n\n"
        f"dealer_gamma_expiry_research_gate: `{gate.get('dealer_gamma_expiry_research_gate', 'not_run')}`\n\n"
        f"cta_vol_research_execution_gate: `{gate.get('cta_vol_research_execution_gate', 'not_run')}`\n\n"
        f"cta_vol_evidence_verdict: `{gate.get('cta_vol_evidence_verdict', 'not_run')}`\n\n"
        f"leveraged_etf_research_execution_gate: `{gate.get('leveraged_etf_research_execution_gate', 'not_run')}`\n\n"
        f"leveraged_etf_evidence_verdict: `{gate.get('leveraged_etf_evidence_verdict', 'not_run')}`\n\n"
        f"dealer_gamma_state_research_execution_gate: `{gate.get('dealer_gamma_state_research_execution_gate', 'not_run')}`\n\n"
        f"dealer_gamma_state_evidence_verdict: `{gate.get('dealer_gamma_state_evidence_verdict', 'not_run')}`\n\n"
        f"dealer_gamma_distance_research_execution_gate: `{gate.get('dealer_gamma_distance_research_execution_gate', 'not_run')}`\n\n"
        f"dealer_gamma_distance_evidence_verdict: `{gate.get('dealer_gamma_distance_evidence_verdict', 'not_run')}`\n\n"
        f"dealer_gamma_expiry_calendar_research_execution_gate: `{gate.get('dealer_gamma_expiry_calendar_research_execution_gate', 'not_run')}`\n\n"
        f"dealer_gamma_expiry_calendar_evidence_verdict: `{gate.get('dealer_gamma_expiry_calendar_evidence_verdict', 'not_run')}`\n\n"
        f"dealer_gamma_expiry_conditioned_research_execution_gate: `{gate.get('dealer_gamma_expiry_conditioned_research_execution_gate', 'not_run')}`\n\n"
        f"dealer_gamma_expiry_conditioned_evidence_verdict: `{gate.get('dealer_gamma_expiry_conditioned_evidence_verdict', 'not_run')}`\n\n"
        f"dealer_gamma_expiry_post_event_secondary_research_execution_gate: `{gate.get('dealer_gamma_expiry_post_event_secondary_research_execution_gate', 'not_run')}`\n\n"
        f"dealer_gamma_expiry_post_event_secondary_evidence_verdict: `{gate.get('dealer_gamma_expiry_post_event_secondary_evidence_verdict', 'not_run')}`\n\n"
        f"actionization_gate: `{str(gate['actionization_gate']).lower()}`\n\n"
        f"no_lookahead_status: `{gate['no_lookahead_status']}`\n\n"
        f"insufficient_data_modules: `{gate['insufficient_data_modules']}`\n\n"
    )


def run(
    root: Path = Path("."),
    refresh_daily_prices: bool = False,
    refresh_intraday_prices: bool = False,
    run_cta_vol_analysis: bool = True,
    run_leveraged_etf_analysis: bool = True,
    run_dealer_observed_analysis: bool = True,
    run_gamma_surrogate_exploration: bool = False,
) -> dict[str, Path]:
    cfg = rules(root)
    base_cfg = baseline_config(root)
    mappings = feature_mappings(root)
    _sources_cfg = data_sources_config(root)
    out = root / OUTPUT_ROOT
    out.mkdir(parents=True, exist_ok=True)
    reports = out / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    targets = list(cfg.get("targets", ["QQQ", "SPY", "SOXX", "SMH"]))
    prices = load_price_history(root, targets)
    daily_outcomes = build_daily_outcomes(prices)
    expiry_calendar = load_expiry_calendar(root)
    expiry_classification = load_expiry_friday_classification(root)
    nyse_calendar = load_nyse_calendar(root)
    daily_baseline = build_daily_baseline(prices, expiry_calendar)
    open_baseline = build_daily_baseline_asof_open(prices, expiry_calendar)
    cta_panel, availability, no_lookahead = (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    if run_cta_vol_analysis:
        cta_panel, availability, no_lookahead = build_cta_vol_feature_outcome_panel(root, daily_outcomes, cfg)
        cta_panel = attach_daily_baseline(cta_panel, daily_baseline)
    lev_panel, lev_audit = (pd.DataFrame(), pd.DataFrame())
    lev_panel_component_manifest = pd.DataFrame(columns=LEVERAGED_ETF_COMPONENT_MANIFEST_COLUMNS)
    if run_leveraged_etf_analysis:
        lev_panel, lev_audit = build_leveraged_etf_panel(root, cfg)
        lev_panel_component_manifest = lev_panel.attrs.get("component_manifest", pd.DataFrame(columns=LEVERAGED_ETF_COMPONENT_MANIFEST_COLUMNS))
        lev_panel.attrs.clear()
    market_level_intraday_universe, market_level_intraday_universe_gate = build_market_level_intraday_universe_with_gate(root, cfg)
    raw_market_level_intraday_universe = ensure_columns(market_level_intraday_universe.copy(), MARKET_LEVEL_INTRADAY_DECISION_UNIVERSE_COLUMNS)
    canonical_market_level_intraday_universe, intraday_universe_integrity_audit = canonicalize_market_level_decision_universe(
        raw_market_level_intraday_universe,
        model_clock="INTRADAY",
        required_columns=MARKET_LEVEL_INTRADAY_DECISION_UNIVERSE_COLUMNS,
    )
    market_level_intraday_universe = canonical_market_level_intraday_universe
    lev_input_audit, lev_input_summary, lev_universe_input_audit, lev_selection_parity = build_leveraged_etf_input_candidate_audits(root, cfg, canonical_market_level_intraday_universe, lev_panel_component_manifest)
    lev_primary_input_integrity, lev_primary_input_gate_summary, lev_aum_selector_parity, lev_bar_semantics_gate = build_leveraged_etf_primary_input_integrity_outputs(lev_input_audit, lev_universe_input_audit, lev_selection_parity)
    dealer_panel, dealer_audit = (pd.DataFrame(), pd.DataFrame())
    dealer_gamma_eod_selection_audit = pd.DataFrame(columns=["decision_date", *DEALER_GAMMA_SELECTION_COLUMNS])
    dealer_gamma_eod_actual_feature_lineage = pd.DataFrame(columns=DEALER_GAMMA_EOD_ACTUAL_FEATURE_LINEAGE_COLUMNS)
    dealer_gamma_eod_feature_hydration_audit = pd.DataFrame(columns=DEALER_GAMMA_EOD_FEATURE_HYDRATION_COLUMNS)
    if run_dealer_observed_analysis:
        dealer_gamma_eod_selection_audit = build_dealer_gamma_eod_selection_audit(root, daily_outcomes, cfg)
        dealer_panel, dealer_audit, dealer_gamma_eod_actual_feature_lineage, dealer_gamma_eod_feature_hydration_audit = build_dealer_gamma_panel_with_actual_lineage(root, daily_outcomes, cfg, dealer_gamma_eod_selection_audit)
        dealer_panel = attach_daily_baseline(dealer_panel, daily_baseline)
    dealer_state_panel, dealer_distance_panel, dealer_sample_audit = split_dealer_gamma_state_distance(dealer_panel)
    raw_market_level_eod_universe = daily_outcomes[daily_outcomes.get("target_market", pd.Series(dtype=str)).astype(str).isin(["SPY", "QQQ", "SOXX"])].copy() if not daily_outcomes.empty else pd.DataFrame()
    if not raw_market_level_eod_universe.empty:
        raw_market_level_eod_universe["model_clock"] = "EOD"
        raw_market_level_eod_universe["decision_time_policy"] = "eod_regular_close_v1"
        raw_market_level_eod_universe["decision_universe_policy"] = MARKET_LEVEL_EOD_UNIVERSE_POLICY
    raw_market_level_eod_universe = ensure_columns(raw_market_level_eod_universe, MARKET_LEVEL_EOD_DECISION_UNIVERSE_COLUMNS)
    canonical_market_level_eod_universe, eod_universe_integrity_audit = canonicalize_market_level_decision_universe(
        raw_market_level_eod_universe,
        model_clock="EOD",
        required_columns=MARKET_LEVEL_EOD_DECISION_UNIVERSE_COLUMNS,
    )
    market_level_eod_universe = canonical_market_level_eod_universe
    market_level_intraday_universe = canonical_market_level_intraday_universe
    market_level_decision_universe_integrity_audit = ensure_columns(
        pd.concat([eod_universe_integrity_audit, intraday_universe_integrity_audit], ignore_index=True, sort=False),
        MARKET_LEVEL_DECISION_UNIVERSE_INTEGRITY_COLUMNS,
    )
    market_level_intraday_universe_gate = ensure_columns(market_level_intraday_universe_gate, MARKET_LEVEL_INTRADAY_UNIVERSE_GATE_COLUMNS)
    dealer_gamma_intraday_selection_audit = build_dealer_gamma_intraday_selection_audit(root, canonical_market_level_intraday_universe, cfg)
    dealer_gamma_source_parity = build_dealer_gamma_source_selection_parity_audit(root, dealer_gamma_eod_actual_feature_lineage, dealer_gamma_intraday_selection_audit, cfg)
    expiry_calendar_panel, expiry_conditioned_panel, expiry_post_panel, expiry_audit, expiry_outcome_audit, calendar_availability_audit = build_dealer_gamma_expiry_event_panel(root, daily_outcomes, cfg)
    expiry_calendar_panel = attach_daily_baseline(expiry_calendar_panel, open_baseline)
    expiry_conditioned_panel = attach_daily_baseline(expiry_conditioned_panel, open_baseline)
    expiry_classification_integrity_gate = build_expiry_classification_integrity_gate_audit(root, expiry_classification, nyse_calendar)
    expiry_classification_historical_availability = build_expiry_classification_historical_availability_audit(root, expiry_classification, nyse_calendar, daily_outcomes)
    expiry_classification_primary_eligibility = expiry_classification_historical_availability.copy()

    min_cfg = cfg.get("minimum_samples", {})
    cta_oos, cta_folds = run_oos_comparison(
        cta_panel,
        module="CTA_Vol",
        test_family="cta_vol_primary",
        feature_sets={
            "CTA_only": mappings.get("cta_only", []),
            "Vol_only": mappings.get("vol_only", []),
            "CTA_plus_Vol": mappings.get("cta_plus_vol", []),
        },
        outcomes=["next_session_absolute_return", "next_session_high_low_range_pct", "forward_realized_vol_5d"],
        baseline_cols=base_cfg.get("daily", []),
        cfg=cfg,
        min_oos_rows=int(min_cfg.get("cta_vol_min_oos_rows_per_target", 252)),
        min_test_months=int(min_cfg.get("cta_vol_min_test_months", 6)),
    )
    lev_oos, lev_folds = run_oos_comparison(
        lev_panel,
        module="LeveragedETF",
        test_family="leveraged_etf_primary",
        feature_sets={"LeveragedETF_pressure": mappings.get("leveraged_etf", [])},
        outcomes=["intraday_absolute_return_1530_to_close", "intraday_range_1530_to_close"],
        baseline_cols=base_cfg.get("intraday", []),
        cfg=cfg,
        min_oos_rows=int(min_cfg.get("leveraged_etf_min_oos_rows", 126)),
        min_test_months=int(min_cfg.get("leveraged_etf_min_test_months", 6)),
    )
    dealer_state_oos, dealer_state_folds = run_oos_comparison(
        dealer_state_panel,
        module="DealerGamma",
        test_family="dealer_gamma_state_primary",
        feature_sets={"DealerGamma_state_model": mappings.get("dealer_gamma_state", [])},
        outcomes=["next_session_high_low_range_pct", "next_session_absolute_return", "forward_realized_vol_5d"],
        baseline_cols=base_cfg.get("daily", []),
        cfg=cfg,
        min_oos_rows=int(min_cfg.get("dealer_gamma_min_oos_rows", 100)),
        min_test_months=int(min_cfg.get("dealer_gamma_min_test_months", 6)),
    )
    dealer_distance_oos, dealer_distance_folds = run_oos_comparison(
        dealer_distance_panel,
        module="DealerGamma",
        test_family="dealer_gamma_distance_local_flip",
        feature_sets={"DealerGamma_distance_model": mappings.get("dealer_gamma_distance", [])},
        outcomes=["next_session_high_low_range_pct", "next_session_absolute_return", "forward_realized_vol_5d"],
        baseline_cols=base_cfg.get("daily", []),
        cfg=cfg,
        min_oos_rows=int(min_cfg.get("dealer_gamma_min_oos_rows", 100)),
        min_test_months=int(min_cfg.get("dealer_gamma_min_test_months", 6)),
    )
    expiry_calendar_oos, expiry_calendar_folds = run_oos_comparison(
        expiry_calendar_panel,
        module="ExpiryCalendar",
        test_family="dealer_gamma_expiry_calendar_event",
        feature_sets={"expiry_event_flags": mappings.get("expiry_event", [])},
        outcomes=["expiry_session_absolute_return_first_regular_bar_open_to_close", "expiry_session_high_low_range_pct", "expiry_session_close_location_value"],
        baseline_cols=base_cfg.get("daily", []),
        cfg=cfg,
        min_oos_rows=int(min_cfg.get("dealer_expiry_min_event_rows_per_comparison_group", 20)),
        min_test_months=1,
    )
    expiry_conditioned_oos, expiry_conditioned_folds = run_oos_comparison(
        expiry_conditioned_panel,
        module="DealerGammaExpiryConditioned",
        test_family="dealer_gamma_expiry_conditioned",
        feature_sets={"expiry_conditioned": mappings.get("expiry_conditioned", [])},
        outcomes=["expiry_session_absolute_return_first_regular_bar_open_to_close", "expiry_session_high_low_range_pct", "expiry_session_close_location_value"],
        baseline_cols=base_cfg.get("daily", []),
        cfg=cfg,
        min_oos_rows=int(min_cfg.get("dealer_expiry_min_event_rows_per_comparison_group", 20)),
        min_test_months=1,
    )
    expiry_post_oos, expiry_post_folds = run_oos_comparison(
        expiry_post_panel,
        module="ExpiryPostSecondary",
        test_family="dealer_gamma_expiry_post_event_secondary",
        feature_sets={"expiry_event_flags": mappings.get("expiry_event", [])},
        outcomes=["post_expiry_next_session_absolute_return", "post_expiry_next_session_high_low_range_pct"],
        baseline_cols=[],
        cfg=cfg,
        min_oos_rows=int(min_cfg.get("dealer_expiry_min_event_rows_per_comparison_group", 20)),
        min_test_months=1,
        primary_or_robustness="secondary",
    )
    group_min_oos = int(min_cfg.get("dealer_expiry_min_oos_rows_per_group", min_cfg.get("dealer_expiry_min_event_rows_per_comparison_group", 20)))
    group_min_months = int(min_cfg.get("dealer_expiry_min_test_months_per_group", 3))
    expiry_group_calendar_oos, expiry_group_calendar_folds, expiry_group_calendar_preds = run_expiry_group_contrast_oos(
        expiry_calendar_panel,
        module="ExpiryCalendar",
        feature_family="ExpiryCalendar",
        feature_name="calendar_group_contrast",
        feature_cols=["event_group_indicator"],
        outcomes=["expiry_session_absolute_return_first_regular_bar_open_to_close", "expiry_session_high_low_range_pct", "expiry_session_close_location_value"],
        baseline_cols=base_cfg.get("expiry_group_contrast", base_cfg.get("daily", [])),
        cfg=cfg,
        min_oos_rows_per_group=group_min_oos,
        min_test_months_per_group=group_min_months,
    )
    expiry_group_conditioned_oos, expiry_group_conditioned_folds, expiry_group_conditioned_preds = run_expiry_group_contrast_oos(
        expiry_conditioned_panel,
        module="DealerGammaExpiryConditioned",
        feature_family="DealerGammaExpiryConditioned",
        feature_name="gamma_conditioned_group_contrast",
        feature_cols=["event_group_indicator", "net_gex_proxy", "pinning_proxy", "local_flip_found_flag", "no_local_flip_flag"],
        outcomes=["expiry_session_absolute_return_first_regular_bar_open_to_close", "expiry_session_high_low_range_pct", "expiry_session_close_location_value"],
        baseline_cols=base_cfg.get("expiry_group_contrast", base_cfg.get("daily", [])),
        cfg=cfg,
        min_oos_rows_per_group=group_min_oos,
        min_test_months_per_group=group_min_months,
    )
    expiry_group_contrast_oos = pd.concat([expiry_group_calendar_oos, expiry_group_conditioned_oos], ignore_index=True)
    expiry_group_contrast_folds = pd.concat([expiry_group_calendar_folds, expiry_group_conditioned_folds], ignore_index=True)
    expiry_group_contrast_predictions = pd.concat([expiry_group_calendar_preds, expiry_group_conditioned_preds], ignore_index=True)
    expiry_group_contrast_descriptive = build_expiry_group_contrast_descriptive_oos(expiry_group_contrast_predictions)
    dealer_oos = pd.concat([dealer_state_oos, dealer_distance_oos], ignore_index=True)
    expiry_oos = pd.concat([expiry_calendar_oos, expiry_conditioned_oos, expiry_post_oos], ignore_index=True)
    summary = pd.concat([cta_oos, lev_oos, dealer_state_oos, dealer_distance_oos, expiry_calendar_oos, expiry_conditioned_oos, expiry_post_oos], ignore_index=True)
    descriptive_summary = pd.concat([
        summarize_association(cta_panel, "CTA_Vol", "next_session_absolute_return", "cta_exposure_change_proxy", "descriptive"),
        summarize_association(lev_panel, "LeveragedETF", "intraday_absolute_return_1530_to_close", "aggregate_pressure_usd", "descriptive"),
        summarize_association(dealer_panel, "DealerGamma", "next_session_high_low_range_pct", "gamma_flip_distance_pct", "descriptive"),
    ], ignore_index=True)

    data_quality = pd.DataFrame([
        {"module": "CTA_Vol", "sample_count": len(cta_panel), "coverage_rate": len(cta_panel) / max(len(daily_outcomes), 1), "verdict": "passed" if len(cta_panel) else "insufficient_data"},
        {"module": "LeveragedETF", "sample_count": len(lev_panel), "coverage_rate": np.nan, "verdict": "passed" if len(lev_panel) else "insufficient_data"},
        {"module": "DealerGamma", "sample_count": len(dealer_panel), "coverage_rate": np.nan, "verdict": "passed" if len(dealer_panel) else "insufficient_data"},
        {"module": "ExpiryCalendar", "sample_count": len(expiry_calendar_panel), "coverage_rate": np.nan, "verdict": "passed" if len(expiry_calendar_panel) else "insufficient_data"},
        {"module": "DealerGammaExpiryConditioned", "sample_count": len(expiry_conditioned_panel), "coverage_rate": np.nan, "verdict": "passed" if len(expiry_conditioned_panel) else "insufficient_data"},
        {"module": "ExpiryPostSecondary", "sample_count": len(expiry_post_panel), "coverage_rate": np.nan, "verdict": "passed" if len(expiry_post_panel) else "insufficient_data"},
    ])
    inventory = source_inventory(root)
    cta_panel = ensure_columns(cta_panel, PANEL_COMMON_COLUMNS)
    lev_panel = ensure_columns(lev_panel, PANEL_COMMON_COLUMNS)
    dealer_panel = ensure_columns(dealer_panel, PANEL_COMMON_COLUMNS)
    dealer_state_panel = ensure_columns(dealer_state_panel, PANEL_COMMON_COLUMNS)
    dealer_distance_panel = ensure_columns(dealer_distance_panel, PANEL_COMMON_COLUMNS)
    expiry_calendar_panel = ensure_columns(expiry_calendar_panel, PANEL_COMMON_COLUMNS)
    expiry_conditioned_panel = ensure_columns(expiry_conditioned_panel, PANEL_COMMON_COLUMNS)
    expiry_post_panel = ensure_columns(expiry_post_panel, PANEL_COMMON_COLUMNS)
    feature_join = pd.concat([
        cta_panel.assign(module="CTA_Vol") if not cta_panel.empty else pd.DataFrame(),
        lev_panel.assign(module="LeveragedETF") if not lev_panel.empty else pd.DataFrame(),
        dealer_panel.assign(module="DealerGamma") if not dealer_panel.empty else pd.DataFrame(),
        expiry_calendar_panel.assign(module="ExpiryCalendar") if not expiry_calendar_panel.empty else pd.DataFrame(),
        expiry_conditioned_panel.assign(module="DealerGammaExpiryConditioned") if not expiry_conditioned_panel.empty else pd.DataFrame(),
        expiry_post_panel.assign(module="ExpiryPostSecondary") if not expiry_post_panel.empty else pd.DataFrame(),
    ], ignore_index=True)
    feature_join = ensure_columns(feature_join, PANEL_COMMON_COLUMNS)
    if not feature_join.empty:
        feature_join["max_feature_age_hours"] = cfg.get("max_feature_age_hours", 96)
    no_lookahead, no_lookahead_status = build_no_lookahead_audit(feature_join)
    post_selection_panel_audit = build_raw_feature_candidate_quality_audit(feature_join, cfg)
    source_candidate_audit, source_candidate_summary = build_source_feature_candidate_audits(root, daily_outcomes, cfg)
    cta_vol_selector_parity = build_cta_vol_selector_parity_audit(root, cta_panel, cfg)
    selection_parity_audit = build_source_selection_parity_audit(source_candidate_audit, {
        "DealerGamma": dealer_panel,
        "DealerGammaExpiryConditioned": expiry_conditioned_panel,
    })
    selection_parity_audit = pd.concat([cta_vol_selector_parity, selection_parity_audit, lev_selection_parity, dealer_gamma_source_parity], ignore_index=True)
    selector_result_audit = build_selector_result_audit(source_candidate_audit, lev_input_audit)
    scope_integrity_gate_audit = build_scope_integrity_gate_audit(selection_parity_audit, lev_primary_input_integrity, expiry_classification_integrity_gate)
    market_level_panel = build_market_level_feature_panel(
        eod_decision_universe=canonical_market_level_eod_universe,
        intraday_decision_universe=canonical_market_level_intraday_universe,
        daily_baseline=daily_baseline,
        cta_panel=cta_panel,
        dealer_panel=dealer_panel,
        lev_panel=lev_panel,
        dealer_intraday_selection=dealer_gamma_intraday_selection_audit,
        dealer_eod_selection_audit=dealer_gamma_eod_selection_audit,
    )
    market_level_component_provenance = build_market_level_component_provenance_status(
        market_level_panel=market_level_panel,
        cta_vol_selector_parity=cta_vol_selector_parity,
        leveraged_selector_parity=lev_selection_parity,
        leveraged_primary_integrity=lev_primary_input_integrity,
        dealer_eod_panel=dealer_gamma_eod_selection_audit,
        dealer_intraday_selection=dealer_gamma_intraday_selection_audit,
        dealer_eod_actual_feature_lineage=dealer_gamma_eod_actual_feature_lineage,
        dealer_gamma_source_parity=dealer_gamma_source_parity,
    )
    market_level_integrity = build_market_level_model_scope_integrity(market_level_panel, market_level_component_provenance)
    market_level_decision_bucket_audit, market_level_target_clock_gate_audit = classify_market_level_decision_buckets(
        canonical_eod_decision_universe=canonical_market_level_eod_universe,
        canonical_intraday_decision_universe=canonical_market_level_intraday_universe,
        universe_integrity_audit=market_level_decision_universe_integrity_audit,
        intraday_universe_gate_audit=market_level_intraday_universe_gate,
        market_level_panel=market_level_panel,
        market_level_scope_integrity=market_level_integrity,
        model_spec=market_level_model_spec(),
        base_cfg=base_cfg,
    )
    market_level_universe_coverage_reconciliation = build_market_level_universe_coverage_reconciliation(
        canonical_market_level_eod_universe,
        canonical_market_level_intraday_universe,
        market_level_decision_universe_integrity_audit,
        market_level_panel,
        market_level_component_provenance,
        market_level_integrity,
        market_level_decision_bucket_audit,
    )
    market_level_predictions, market_level_fold_coefficients, market_level_fold_audit, market_level_metrics, market_level_incremental, market_level_regime, market_level_quality = run_market_level_oos_backtest(
        market_level_panel,
        market_level_decision_bucket_audit,
        market_level_target_clock_gate_audit,
        market_level_universe_coverage_reconciliation,
        cfg,
        base_cfg,
    )
    dealer_oos = pd.concat([dealer_state_oos, dealer_distance_oos], ignore_index=True)
    expiry_oos = pd.concat([expiry_calendar_oos, expiry_conditioned_oos, expiry_post_oos], ignore_index=True)
    summary = pd.concat([cta_oos, lev_oos, dealer_state_oos, dealer_distance_oos, expiry_calendar_oos, expiry_conditioned_oos, expiry_post_oos], ignore_index=True)
    module_quality_audit = build_module_data_quality_propagation_audit(no_lookahead, {
        "CTA_Vol": cta_oos,
        "CTA": cta_oos,
        "VolControl": lev_oos.iloc[0:0].copy(),
        "LeveragedETF": lev_oos,
        "DealerGamma": dealer_oos,
        "ExpiryCalendar": expiry_calendar_oos,
        "DealerGammaExpiryConditioned": expiry_conditioned_oos,
        "ExpiryPostSecondary": expiry_post_oos,
    }, source_candidate_summary.rename(columns={
        "excluded_future_timestamp_count": "excluded_future_timestamp_count",
        "excluded_missing_timestamp_count": "excluded_missing_timestamp_count",
        "excluded_age_count": "excluded_age_count",
        "excluded_quality_count": "excluded_quality_count",
        "excluded_target_mismatch_count": "excluded_target_mismatch_count",
        "selected_row_count": "selected_row_count",
        "raw_candidate_row_count": "raw_candidate_row_count",
        "eligible_row_count": "eligible_row_count",
    }))
    expiry_group_oos = expiry_group_contrast_oos.copy()
    refresh_rows = refresh_status_rows(refresh_daily_prices, refresh_intraday_prices, run_gamma_surrogate_exploration)
    if refresh_rows:
        data_quality = pd.concat([data_quality, pd.DataFrame(refresh_rows).rename(columns={"status": "verdict"})], ignore_index=True)
    insufficient = ",".join(data_quality.loc[data_quality["verdict"].astype(str).isin(["insufficient_data", "not_supported"]), "module"].astype(str))
    gate = {
        "market_impact_data_gate": market_data_gate(feature_join, no_lookahead_status),
        "cta_vol_primary_research_gate": research_gate_from_oos(cta_oos, run_cta_vol_analysis),
        "leveraged_etf_primary_research_gate": research_gate_from_oos(lev_oos, run_leveraged_etf_analysis),
        "dealer_gamma_primary_research_gate": research_gate_from_oos(dealer_oos, run_dealer_observed_analysis),
        "dealer_gamma_state_research_execution_gate": research_gate_from_oos(dealer_state_oos, run_dealer_observed_analysis),
        "dealer_gamma_distance_research_execution_gate": research_gate_from_oos(dealer_distance_oos, run_dealer_observed_analysis),
        "dealer_gamma_expiry_research_gate": research_gate_from_oos(expiry_oos, True),
        "dealer_gamma_expiry_calendar_research_execution_gate": research_gate_from_oos(expiry_calendar_oos, True),
        "dealer_gamma_expiry_conditioned_research_execution_gate": research_gate_from_oos(expiry_conditioned_oos, True),
        "dealer_gamma_expiry_post_event_secondary_research_execution_gate": research_gate_from_oos(expiry_post_oos, True),
        "actionization_gate": False,
        "no_lookahead_status": no_lookahead_status,
        "insufficient_data_modules": insufficient,
    }
    gate.update({
        "cta_vol_research_execution_gate": research_gate_from_oos(cta_oos, run_cta_vol_analysis),
        "cta_vol_evidence_verdict": ",".join(sorted(set(cta_oos.get("evidence_verdict", pd.Series(dtype=str)).astype(str)))) if not cta_oos.empty else "insufficient_data",
        "leveraged_etf_research_execution_gate": research_gate_from_oos(lev_oos, run_leveraged_etf_analysis),
        "leveraged_etf_evidence_verdict": ",".join(sorted(set(lev_oos.get("evidence_verdict", pd.Series(dtype=str)).astype(str)))) if not lev_oos.empty else "insufficient_data",
        "dealer_gamma_state_evidence_verdict": ",".join(sorted(set(dealer_state_oos.get("evidence_verdict", pd.Series(dtype=str)).astype(str)))) if not dealer_state_oos.empty else "insufficient_data",
        "dealer_gamma_distance_evidence_verdict": ",".join(sorted(set(dealer_distance_oos.get("evidence_verdict", pd.Series(dtype=str)).astype(str)))) if not dealer_distance_oos.empty else "insufficient_data",
        "dealer_gamma_expiry_calendar_evidence_verdict": ",".join(sorted(set(expiry_calendar_oos.get("evidence_verdict", pd.Series(dtype=str)).astype(str)))) if not expiry_calendar_oos.empty else "insufficient_data",
        "dealer_gamma_expiry_conditioned_evidence_verdict": ",".join(sorted(set(expiry_conditioned_oos.get("evidence_verdict", pd.Series(dtype=str)).astype(str)))) if not expiry_conditioned_oos.empty else "insufficient_data",
        "dealer_gamma_expiry_post_event_secondary_evidence_verdict": ",".join(sorted(set(expiry_post_oos.get("evidence_verdict", pd.Series(dtype=str)).astype(str)))) if not expiry_post_oos.empty else "insufficient_data",
    })
    manifest = {
        "analysis_id": f"market_impact_{pd.Timestamp.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}",
        "version": VERSION,
        "analysis_base_commit_sha": os.environ.get("GITHUB_SHA", ""),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "rules_version": cfg.get("version"),
        "walk_forward": build_walk_forward_manifest(len(feature_join), cfg),
        "actionization_allowed": False,
        "gates": gate,
        "refresh_status": refresh_rows,
        "gamma_surrogate_status": "not_implemented" if run_gamma_surrogate_exploration else "not_run",
        "market_level_oos": {
            "artifact_version": "market_level_v1",
            "actionization_gate": False,
            "decision_universe_policy": MARKET_LEVEL_DECISION_UNIVERSE_POLICY,
            "dealer_gamma_source_contract_revision": DEALER_GAMMA_SOURCE_CONTRACT_REVISION,
            "dealer_gamma_selection_policy_revision": DEALER_GAMMA_SELECTION_POLICY_REVISION,
            "market_level_integrity_revision": MARKET_LEVEL_INTEGRITY_REVISION,
            "decision_bucket_candidate_source": MARKET_LEVEL_BUCKET_CANDIDATE_SOURCE_POLICY,
            "eod_decision_universe_policy": MARKET_LEVEL_EOD_UNIVERSE_POLICY,
            "intraday_decision_universe_policy": MARKET_LEVEL_INTRADAY_UNIVERSE_POLICY,
            "intraday_panel_fallback_allowed": False,
            "universe_duplicate_key_policy": UNIVERSE_DUPLICATE_KEY_POLICY,
            "universe_coverage_reconciliation_granularity": MARKET_LEVEL_COVERAGE_RECONCILIATION_GRANULARITY,
            "coverage_mismatch_policy": COVERAGE_MISMATCH_POLICY,
            "oos_requires_universe_coverage_reconciliation": True,
            "oos_bucket_policy": MARKET_LEVEL_OOS_BUCKET_POLICY,
            "target_clock_gate_missing_policy": TARGET_CLOCK_GATE_MISSING_POLICY,
            "eod_gamma_parity_input_policy": EOD_ACTUAL_FEATURE_LINEAGE_POLICY,
            "leveraged_close_1600_role": LEVERAGED_CLOSE_1600_ROLE,
            "raw_eod_universe_row_count": int(len(raw_market_level_eod_universe)),
            "canonical_eod_universe_row_count": int(len(canonical_market_level_eod_universe)),
            "raw_intraday_universe_row_count": int(len(raw_market_level_intraday_universe)),
            "canonical_intraday_universe_row_count": int(len(canonical_market_level_intraday_universe)),
            "duplicate_universe_key_count": int(pd.to_numeric(market_level_decision_universe_integrity_audit.get("duplicate_detected", pd.Series(dtype=int)), errors="coerce").fillna(0).sum()) if not market_level_decision_universe_integrity_audit.empty else 0,
            "coverage_reconciliation_mismatch_count": int(market_level_universe_coverage_reconciliation.get("coverage_reconciliation_status", pd.Series(dtype=str)).astype(str).ne("matched").sum()) if not market_level_universe_coverage_reconciliation.empty else 0,
            "coverage_reconciliation_mismatch_groups": ";".join(
                market_level_universe_coverage_reconciliation.loc[
                    market_level_universe_coverage_reconciliation.get("coverage_reconciliation_status", pd.Series(dtype=str)).astype(str).ne("matched"),
                    ["target_market", "model_clock", "model_scope", "outcome"],
                ].astype(str).drop_duplicates().agg("|".join, axis=1).head(50).tolist()
            ) if not market_level_universe_coverage_reconciliation.empty else "",
            "matched_requires_actual_vs_fresh": True,
            "eod_actual_feature_lineage_policy": EOD_ACTUAL_FEATURE_LINEAGE_POLICY,
            "intraday_input_audit_universe_policy": INTRADAY_INPUT_AUDIT_UNIVERSE_POLICY,
            "calendar_fallback_allowed": False,
            "leveraged_self_match_allowed": False,
            "legacy_global_blocks_used_anywhere_in_run": False,
            "legacy_global_blocks_used_for_market_level": False,
            "market_level_gate_source": "decision_bucket_target_clock_and_coverage_v1_1_15",
        },
    }

    write_table(inventory, out / "source_inventory.csv")
    (out / "source_inventory.md").write_text("# Source Inventory\n\n" + markdown_table(inventory) + "\n", encoding="utf-8")
    data_quality.to_csv(out / "data_quality_audit.csv", index=False)
    availability = pd.concat([availability, lev_audit, dealer_audit], ignore_index=True)
    availability = ensure_columns(availability, FEATURE_AUDIT_COLUMNS)
    lev_audit = ensure_columns(lev_audit, LEVERAGED_AUDIT_COLUMNS)
    expiry_audit = ensure_columns(expiry_audit, EXPIRY_SNAPSHOT_AUDIT_COLUMNS)
    expiry_outcome_audit = ensure_columns(expiry_outcome_audit, EXPIRY_INTRADAY_OUTCOME_AUDIT_COLUMNS)
    availability.to_csv(out / "feature_availability_audit.csv", index=False)
    (out / "feature_availability_audit.md").write_text("# Feature Availability Audit\n\n" + markdown_table(availability) + "\n", encoding="utf-8")
    write_table(feature_join, out / "feature_outcome_join_audit.csv", out / "feature_outcome_join_audit.parquet")
    (out / "feature_outcome_join_audit.md").write_text("# Feature Outcome Join Audit\n\n" + markdown_table(feature_join) + "\n", encoding="utf-8")
    no_lookahead.to_csv(out / "no_lookahead_audit.csv", index=False)
    (out / "no_lookahead_audit.md").write_text("# No Lookahead Audit\n\n" + markdown_table(no_lookahead) + "\n", encoding="utf-8")
    write_table(source_candidate_audit, out / "source_feature_candidate_audit.csv")
    write_table(source_candidate_summary, out / "source_feature_candidate_quality_summary.csv")
    (out / "source_feature_candidate_quality_summary.md").write_text("# Source Feature Candidate Quality Summary\n\n" + markdown_table(source_candidate_summary) + "\n", encoding="utf-8")
    write_table(selector_result_audit, out / "selector_result_audit.csv")
    write_table(selection_parity_audit, out / "source_selection_parity_audit.csv")
    write_table(cta_vol_selector_parity, out / "cta_vol_source_selection_parity_audit.csv")
    write_table(scope_integrity_gate_audit, out / "scope_integrity_gate_audit.csv")
    write_table(post_selection_panel_audit, out / "post_selection_panel_quality_audit.csv")
    write_table(post_selection_panel_audit, out / "raw_feature_candidate_quality_audit.csv")
    (out / "raw_feature_candidate_quality_audit.md").write_text("# Post-Selection Panel Quality Audit\n\n" + markdown_table(post_selection_panel_audit) + "\n", encoding="utf-8")
    write_table(daily_outcomes, out / "daily_market_outcomes.csv", out / "daily_market_outcomes.parquet")
    write_table(cta_panel, out / "cta_vol_primary_panel.csv", out / "cta_vol_primary_panel.parquet")
    write_table(cta_oos, out / "cta_vol_primary_oos_results.csv")
    write_table(cta_folds, out / "cta_vol_primary_fold_audit.csv")
    write_table(lev_panel, out / "leveraged_etf_primary_panel.csv", out / "leveraged_etf_primary_panel.parquet")
    write_table(lev_oos, out / "leveraged_etf_primary_oos_results.csv")
    write_table(lev_audit, out / "leveraged_etf_intraday_data_audit.csv")
    write_table(lev_audit, out / "leveraged_etf_universe_completeness_audit.csv")
    write_table(lev_audit, out / "leveraged_etf_intraday_timestamp_audit.csv")
    write_table(lev_audit, out / "leveraged_etf_aum_availability_audit.csv")
    write_table(lev_audit, out / "leveraged_etf_volume_baseline_audit.csv")
    write_table(dealer_panel, out / "dealer_gamma_observed_primary_panel.csv", out / "dealer_gamma_observed_primary_panel.parquet")
    write_table(dealer_oos, out / "dealer_gamma_observed_primary_oos_results.csv")
    write_table(dealer_state_oos, out / "dealer_gamma_state_primary_oos_results.csv")
    write_table(dealer_distance_oos, out / "dealer_gamma_distance_local_flip_oos_results.csv")
    write_table(dealer_sample_audit, out / "dealer_gamma_sample_composition_audit.csv")
    write_table(dealer_audit, out / "dealer_gamma_observed_join_audit.csv")
    write_table(expiry_calendar_panel, out / "dealer_gamma_expiry_event_panel.csv")
    write_table(expiry_oos, out / "dealer_gamma_expiry_event_oos_results.csv")
    write_table(expiry_audit, out / "dealer_gamma_expiry_event_audit.csv")
    write_table(expiry_audit, out / "expiry_dealer_gamma_selection_audit_v1.csv")
    write_table(expiry_calendar_panel, out / "dealer_gamma_expiry_calendar_event_panel.csv")
    write_table(expiry_calendar_oos, out / "dealer_gamma_expiry_calendar_event_oos_results.csv")
    write_table(expiry_conditioned_panel, out / "dealer_gamma_expiry_conditioned_panel.csv")
    write_table(expiry_conditioned_oos, out / "dealer_gamma_expiry_conditioned_oos_results.csv")
    write_table(expiry_calendar_panel, out / "dealer_gamma_expiry_calendar_intraday_panel.csv")
    write_table(expiry_calendar_oos, out / "dealer_gamma_expiry_calendar_intraday_oos_results.csv")
    write_table(expiry_conditioned_panel, out / "dealer_gamma_expiry_conditioned_intraday_panel.csv")
    write_table(expiry_conditioned_oos, out / "dealer_gamma_expiry_conditioned_intraday_oos_results.csv")
    write_table(expiry_post_panel, out / "dealer_gamma_expiry_post_event_secondary_panel.csv")
    write_table(expiry_post_oos, out / "dealer_gamma_expiry_post_event_secondary_oos_results.csv")
    write_table(expiry_audit, out / "dealer_gamma_expiry_snapshot_join_audit.csv")
    write_table(expiry_outcome_audit, out / "expiry_intraday_outcome_audit.csv")
    write_table(expiry_calendar_panel, out / "expiry_intraday_outcome_panel.csv")
    write_table(calendar_availability_audit, out / "calendar_availability_contract_audit.csv")
    write_table(module_quality_audit, out / "module_data_quality_propagation_audit.csv")
    write_table(expiry_group_contrast_folds, out / "expiry_group_contrast_fold_audit.csv")
    write_table(expiry_group_contrast_predictions, out / "expiry_group_contrast_oos_predictions.csv")
    write_table(expiry_group_contrast_oos, out / "expiry_group_contrast_oos_results.csv")
    write_table(expiry_group_contrast_descriptive, out / "expiry_group_contrast_descriptive_oos.csv")
    write_table(expiry_group_oos, out / "expiry_group_sample_sufficiency_audit.csv")
    write_table(expiry_group_oos, out / "dealer_gamma_expiry_group_oos_results.csv")
    write_table(build_expiry_classification_coverage_audit(root, expiry_classification, nyse_calendar), out / "expiry_classification_coverage_audit.csv")
    write_table(expiry_classification, out / "expiry_classification_universe.csv")
    write_table(build_expiry_classification_provenance_audit(root, expiry_classification, nyse_calendar), out / "expiry_classification_provenance_audit.csv")
    write_table(lev_input_audit, out / "leveraged_etf_input_candidate_audit.csv")
    write_table(lev_input_summary, out / "leveraged_etf_input_candidate_summary.csv")
    write_table(lev_universe_input_audit, out / "leveraged_etf_universe_input_completeness_audit.csv")
    write_table(lev_selection_parity, out / "leveraged_etf_source_selection_parity_audit.csv")
    write_table(lev_panel_component_manifest, out / "leveraged_etf_panel_selection_components_v1.csv")
    write_table(lev_primary_input_integrity, out / "leveraged_etf_primary_input_integrity_audit.csv")
    write_table(lev_primary_input_integrity, out / "leveraged_etf_primary_input_integrity.csv")
    write_table(lev_primary_input_gate_summary, out / "leveraged_etf_primary_input_gate_summary.csv")
    write_table(lev_aum_selector_parity, out / "leveraged_etf_aum_selector_parity_audit.csv")
    write_table(lev_bar_semantics_gate, out / "leveraged_etf_bar_semantics_gate_audit.csv")
    write_table(expiry_classification_integrity_gate, out / "expiry_classification_integrity_gate_audit.csv")
    write_table(expiry_classification_historical_availability, out / "expiry_classification_historical_availability_audit.csv")
    write_table(expiry_classification_primary_eligibility, out / "expiry_classification_primary_eligibility_audit.csv")
    write_table(market_level_panel, out / "market_level_feature_panel_v1.csv")
    write_table(market_level_eod_universe, out / "market_level_eod_decision_universe_v1.csv")
    write_table(market_level_intraday_universe, out / "market_level_intraday_decision_universe_v1.csv")
    write_table(market_level_decision_universe_integrity_audit, out / "market_level_decision_universe_integrity_audit_v1.csv")
    write_table(market_level_intraday_universe_gate, out / "market_level_intraday_universe_gate_audit_v1.csv")
    write_table(market_level_component_provenance, out / "market_level_component_provenance_status_v1.csv")
    write_table(market_level_integrity, out / "market_level_model_scope_integrity_v1.csv")
    write_table(market_level_integrity, out / "market_level_decision_integrity_snapshot_v1.csv")
    write_table(market_level_decision_bucket_audit, out / "market_level_decision_bucket_audit_v1.csv")
    write_table(market_level_target_clock_gate_audit, out / "market_level_target_clock_gate_audit_v1.csv")
    write_table(market_level_universe_coverage_reconciliation, out / "market_level_universe_coverage_reconciliation_v1.csv")
    write_table(market_level_predictions, out / "market_level_oos_predictions_v1.csv")
    write_table(market_level_fold_coefficients, out / "market_level_oos_fold_coefficients_v1.csv")
    write_table(market_level_fold_audit, out / "market_level_oos_fold_audit_v1.csv")
    write_table(market_level_metrics, out / "market_level_oos_metrics_v1.csv")
    write_table(market_level_incremental, out / "market_level_incremental_comparison_v1.csv")
    write_table(market_level_regime, out / "market_level_regime_summary_v1.csv")
    write_table(market_level_quality, out / "market_level_data_quality_audit_v1.csv")
    write_table(dealer_gamma_eod_selection_audit, out / "dealer_gamma_eod_selection_audit_v1.csv")
    write_table(dealer_gamma_eod_actual_feature_lineage, out / "dealer_gamma_eod_actual_feature_lineage_v1.csv")
    write_table(dealer_gamma_eod_feature_hydration_audit, out / "dealer_gamma_eod_feature_hydration_audit_v1.csv")
    write_table(dealer_gamma_source_parity, out / "dealer_gamma_source_selection_parity_audit_v1.csv")
    with (out / "market_level_model_spec_v1.json").open("w", encoding="utf-8") as f:
        json.dump(market_level_model_spec(), f, indent=2, sort_keys=True)
    (out / "market_level_backtest_report_v1.md").write_text(market_level_report_text(market_level_metrics, market_level_quality), encoding="utf-8")
    provider_bar_semantics_audit = build_provider_bar_semantics_validation_audit(root, cfg.get("targets", []))
    write_table(build_nyse_session_calendar_audit(load_nyse_calendar(root), root), out / "nyse_session_calendar_audit.csv")
    write_table(build_nyse_calendar_continuity_audit(root, load_nyse_calendar(root)), out / "nyse_calendar_continuity_audit.csv")
    write_table(provider_bar_semantics_audit, out / "provider_bar_semantics_validation_audit.csv")
    write_table(pd.concat([cta_folds, lev_folds, dealer_state_folds, dealer_distance_folds, expiry_calendar_folds, expiry_conditioned_folds, expiry_post_folds], ignore_index=True), out / "feature_fold_audit.csv")
    write_table(descriptive_summary, out / "descriptive_association_summary.csv")
    write_table(cta_panel, out / "cta_vol_market_impact_panel.csv", out / "cta_vol_market_impact_panel.parquet")
    write_table(lev_panel, out / "leveraged_etf_intraday_panel.csv", out / "leveraged_etf_intraday_panel.parquet")
    write_table(dealer_panel, out / "dealer_gamma_observed_panel.csv", out / "dealer_gamma_observed_panel.parquet")
    write_table(dealer_gamma_intraday_selection_audit, out / "dealer_gamma_intraday_selection_audit_v1.csv")
    summary.to_csv(out / "model_comparison_summary.csv", index=False)
    expiry_calendar_out = expiry_calendar.copy()
    if not expiry_calendar_out.empty:
        expiry_calendar_out["holiday_adjusted_audited"] = expiry_calendar_out.get("holiday_adjusted_flag", False).astype(str).str.lower().isin(["true", "1", "yes"])
    expiry_calendar_out.to_csv(out / "dealer_gamma_expiry_event_study.csv", index=False)
    with (out / "analysis_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    (root / "market_impact_backtest_gate_audit.md").write_text(gate_audit_text(gate), encoding="utf-8")
    write_reports(root, cta_oos, lev_oos, dealer_oos, expiry_oos, expiry_group_oos, source_candidate_summary, calendar_availability_audit, provider_bar_semantics_audit, expiry_group_contrast_folds, gate, refresh_rows)
    return {
        "source_inventory": out / "source_inventory.csv",
        "feature_availability_audit": out / "feature_availability_audit.csv",
        "feature_outcome_join_audit": out / "feature_outcome_join_audit.csv",
        "no_lookahead_audit": out / "no_lookahead_audit.csv",
        "model_comparison_summary": out / "model_comparison_summary.csv",
        "cta_vol_primary_oos_results": out / "cta_vol_primary_oos_results.csv",
        "leveraged_etf_primary_oos_results": out / "leveraged_etf_primary_oos_results.csv",
        "dealer_gamma_observed_primary_oos_results": out / "dealer_gamma_observed_primary_oos_results.csv",
        "dealer_gamma_expiry_event_oos_results": out / "dealer_gamma_expiry_event_oos_results.csv",
        "nyse_session_calendar_audit": out / "nyse_session_calendar_audit.csv",
        "expiry_intraday_outcome_audit": out / "expiry_intraday_outcome_audit.csv",
        "source_feature_candidate_audit": out / "source_feature_candidate_audit.csv",
        "source_feature_candidate_quality_summary": out / "source_feature_candidate_quality_summary.csv",
        "selector_result_audit": out / "selector_result_audit.csv",
        "source_selection_parity_audit": out / "source_selection_parity_audit.csv",
        "cta_vol_source_selection_parity_audit": out / "cta_vol_source_selection_parity_audit.csv",
        "scope_integrity_gate_audit": out / "scope_integrity_gate_audit.csv",
        "raw_feature_candidate_quality_audit": out / "raw_feature_candidate_quality_audit.csv",
        "module_data_quality_propagation_audit": out / "module_data_quality_propagation_audit.csv",
        "expiry_group_contrast_oos_results": out / "expiry_group_contrast_oos_results.csv",
        "expiry_group_contrast_descriptive_oos": out / "expiry_group_contrast_descriptive_oos.csv",
        "expiry_group_sample_sufficiency_audit": out / "expiry_group_sample_sufficiency_audit.csv",
        "dealer_gamma_expiry_group_oos_results": out / "dealer_gamma_expiry_group_oos_results.csv",
        "calendar_availability_contract_audit": out / "calendar_availability_contract_audit.csv",
        "nyse_calendar_continuity_audit": out / "nyse_calendar_continuity_audit.csv",
        "provider_bar_semantics_validation_audit": out / "provider_bar_semantics_validation_audit.csv",
        "expiry_classification_coverage_audit": out / "expiry_classification_coverage_audit.csv",
        "expiry_classification_provenance_audit": out / "expiry_classification_provenance_audit.csv",
        "leveraged_etf_input_candidate_audit": out / "leveraged_etf_input_candidate_audit.csv",
        "leveraged_etf_input_candidate_summary": out / "leveraged_etf_input_candidate_summary.csv",
        "leveraged_etf_universe_input_completeness_audit": out / "leveraged_etf_universe_input_completeness_audit.csv",
        "leveraged_etf_source_selection_parity_audit": out / "leveraged_etf_source_selection_parity_audit.csv",
        "leveraged_etf_panel_selection_components_v1": out / "leveraged_etf_panel_selection_components_v1.csv",
        "leveraged_etf_primary_input_integrity_audit": out / "leveraged_etf_primary_input_integrity_audit.csv",
        "leveraged_etf_primary_input_integrity": out / "leveraged_etf_primary_input_integrity.csv",
        "leveraged_etf_primary_input_gate_summary": out / "leveraged_etf_primary_input_gate_summary.csv",
        "leveraged_etf_aum_selector_parity_audit": out / "leveraged_etf_aum_selector_parity_audit.csv",
        "leveraged_etf_bar_semantics_gate_audit": out / "leveraged_etf_bar_semantics_gate_audit.csv",
        "expiry_classification_integrity_gate_audit": out / "expiry_classification_integrity_gate_audit.csv",
        "expiry_classification_historical_availability_audit": out / "expiry_classification_historical_availability_audit.csv",
        "expiry_classification_primary_eligibility_audit": out / "expiry_classification_primary_eligibility_audit.csv",
        "market_level_feature_panel_v1": out / "market_level_feature_panel_v1.csv",
        "market_level_eod_decision_universe_v1": out / "market_level_eod_decision_universe_v1.csv",
        "market_level_intraday_decision_universe_v1": out / "market_level_intraday_decision_universe_v1.csv",
        "market_level_decision_universe_integrity_audit_v1": out / "market_level_decision_universe_integrity_audit_v1.csv",
        "market_level_intraday_universe_gate_audit_v1": out / "market_level_intraday_universe_gate_audit_v1.csv",
        "market_level_component_provenance_status_v1": out / "market_level_component_provenance_status_v1.csv",
        "market_level_model_scope_integrity_v1": out / "market_level_model_scope_integrity_v1.csv",
        "market_level_decision_integrity_snapshot_v1": out / "market_level_decision_integrity_snapshot_v1.csv",
        "market_level_decision_bucket_audit_v1": out / "market_level_decision_bucket_audit_v1.csv",
        "market_level_target_clock_gate_audit_v1": out / "market_level_target_clock_gate_audit_v1.csv",
        "market_level_universe_coverage_reconciliation_v1": out / "market_level_universe_coverage_reconciliation_v1.csv",
        "market_level_oos_predictions_v1": out / "market_level_oos_predictions_v1.csv",
        "market_level_oos_fold_coefficients_v1": out / "market_level_oos_fold_coefficients_v1.csv",
        "market_level_oos_fold_audit_v1": out / "market_level_oos_fold_audit_v1.csv",
        "market_level_oos_metrics_v1": out / "market_level_oos_metrics_v1.csv",
        "market_level_incremental_comparison_v1": out / "market_level_incremental_comparison_v1.csv",
        "market_level_regime_summary_v1": out / "market_level_regime_summary_v1.csv",
        "market_level_data_quality_audit_v1": out / "market_level_data_quality_audit_v1.csv",
        "market_level_model_spec_v1": out / "market_level_model_spec_v1.json",
        "market_level_backtest_report_v1": out / "market_level_backtest_report_v1.md",
        "dealer_gamma_eod_selection_audit_v1": out / "dealer_gamma_eod_selection_audit_v1.csv",
        "dealer_gamma_eod_actual_feature_lineage_v1": out / "dealer_gamma_eod_actual_feature_lineage_v1.csv",
        "dealer_gamma_eod_feature_hydration_audit_v1": out / "dealer_gamma_eod_feature_hydration_audit_v1.csv",
        "dealer_gamma_intraday_selection_audit_v1": out / "dealer_gamma_intraday_selection_audit_v1.csv",
        "dealer_gamma_source_selection_parity_audit_v1": out / "dealer_gamma_source_selection_parity_audit_v1.csv",
        "expiry_dealer_gamma_selection_audit_v1": out / "expiry_dealer_gamma_selection_audit_v1.csv",
        "gate": root / "market_impact_backtest_gate_audit.md",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--refresh-daily-prices", action="store_true")
    parser.add_argument("--refresh-intraday-prices", action="store_true")
    parser.add_argument("--skip-cta-vol-analysis", action="store_true")
    parser.add_argument("--skip-leveraged-etf-analysis", action="store_true")
    parser.add_argument("--skip-dealer-observed-analysis", action="store_true")
    parser.add_argument("--run-gamma-surrogate-exploration", action="store_true")
    args = parser.parse_args()
    outputs = run(
        Path(args.root),
        refresh_daily_prices=args.refresh_daily_prices,
        refresh_intraday_prices=args.refresh_intraday_prices,
        run_cta_vol_analysis=not args.skip_cta_vol_analysis,
        run_leveraged_etf_analysis=not args.skip_leveraged_etf_analysis,
        run_dealer_observed_analysis=not args.skip_dealer_observed_analysis,
        run_gamma_surrogate_exploration=args.run_gamma_surrogate_exploration,
    )
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
