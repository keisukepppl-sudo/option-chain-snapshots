from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_morita_short_v3_5_3_claim_audit.py"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("claim_audit", SCRIPT)
claim_audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["claim_audit"] = claim_audit
spec.loader.exec_module(claim_audit)


def test_sign_test_ignores_ties():
    assert claim_audit.sign_test_p(3, 0) == 0.25


def test_paired_metrics_require_same_units():
    paired = pd.DataFrame({"open_return": [0.01, -0.02], "entry_return": [0.02, -0.01], "difference": [0.01, 0.01]})
    metrics = claim_audit.paired_metrics(paired)
    assert metrics["paired_n"] == 2
    assert metrics["wins"] == 2


def test_final_decision_rejects_failed_gates():
    gate = pd.DataFrame(
        [
            {"rank": "S", "entry": "Open", "gate_status": "FAIL", "paired_0945_supported": ""},
            {"rank": "S", "entry": "09:45", "gate_status": "FAIL", "paired_0945_supported": False},
        ]
    )
    assert claim_audit.final_decision_from_gate(gate) == "REJECT_HISTORICAL_EDGE_CONCENTRATION"


def test_safety_contract_research_only():
    fields = claim_audit.safety_fields()
    assert fields["research_only"] is True
    assert fields["live_order_allowed"] is False
    assert fields["threshold_optimization_allowed"] is False
