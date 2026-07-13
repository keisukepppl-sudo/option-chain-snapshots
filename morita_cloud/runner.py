from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

import scanner_notify as sn
import scripts.production_scanner_entry as production_entry
from morita_cloud.cache import build_precompute, load_precompute, manifest_name
from morita_cloud.intraday import fetch_intraday_snapshots_at_cutoff
from morita_cloud.logic import (
    CHECKPOINT_TIMES,
    FINAL_EXECUTION_SLOT,
    WAKE_START,
    checkpoint_candidates,
    checkpoint_timestamp,
    default_state,
    determine_action,
    env_flag,
    market_session,
    new_late_s_candidates,
    normalize_et,
    state_blob_name,
    ticker_lists,
    trading_date_et,
)
from morita_cloud.notifications import (
    checkpoint_message,
    full_discord_message,
    send_notification,
    wake_message,
)
from morita_cloud.state_store import GcsStore, LockUnavailable


@dataclass(frozen=True)
class TickResult:
    status: str
    action: str | None
    trading_date_et: str
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "action": self.action,
            "trading_date_et": self.trading_date_et,
            "details": self.details,
        }


class TickRunner:
    def __init__(
        self,
        store: GcsStore,
        config_path: str = "config.yaml",
        precompute_period: str = "18mo",
        dry_run: bool | None = None,
    ) -> None:
        self.store = store
        self.config_path = config_path
        self.precompute_period = precompute_period
        self.dry_run = env_flag("DRY_RUN", default=True) if dry_run is None else bool(dry_run)
        self.mode = "shadow" if self.dry_run else "live"

    @classmethod
    def from_env(cls) -> "TickRunner":
        return cls(
            GcsStore(os.environ.get("GCS_BUCKET", "")),
            config_path=os.environ.get("SCANNER_CONFIG_PATH", "config.yaml"),
            precompute_period=os.environ.get("PRECOMPUTE_PERIOD", "18mo"),
        )

    def run(
        self,
        timestamp_et: pd.Timestamp | str | None = None,
        force_action: str | None = None,
    ) -> TickResult:
        timestamp = normalize_et(timestamp_et)
        date_et = trading_date_et(timestamp)
        session = market_session(timestamp)
        if session is None:
            return TickResult("market_closed", None, date_et, {"now_et": timestamp.isoformat()})
        _, market_close = session

        try:
            with self.store.lock(f"locks/{date_et}.lock"):
                return self._run_locked(timestamp, market_close, force_action)
        except LockUnavailable as exc:
            return TickResult("busy", None, date_et, {"reason": str(exc)})

    def _run_locked(
        self,
        timestamp: pd.Timestamp,
        market_close: pd.Timestamp,
        force_action: str | None,
    ) -> TickResult:
        date_et = trading_date_et(timestamp)
        state_name = state_blob_name(date_et, self.mode)
        state, generation = self.store.read_json(state_name, default_state(date_et))
        action = determine_action(
            timestamp,
            state,
            self.store.exists(manifest_name(date_et)),
            force_action=force_action,
        )

        if action == "WAKE" and market_close.time().replace(tzinfo=None) < WAKE_START:
            return TickResult("early_close_no_wake", action, date_et, {"market_close_et": market_close.isoformat()})
        if action is None:
            return TickResult("noop", None, date_et, {"now_et": timestamp.isoformat()})

        if action == "PRECOMPUTE":
            manifest = self._ensure_precompute(date_et, force=bool(force_action))
            state.update(
                {
                    "precompute_complete": True,
                    "precompute_manifest": manifest_name(date_et),
                    "precompute_completed_at_et": timestamp.isoformat(),
                }
            )
            self.store.write_json(state_name, state, generation=generation)
            return TickResult("ok", action, date_et, {"manifest": manifest})

        manifest = self._ensure_precompute(date_et)
        state["precompute_complete"] = True
        state["precompute_manifest"] = manifest_name(date_et)
        cutoff = checkpoint_timestamp(timestamp, action) if action in CHECKPOINT_TIMES else timestamp.floor("5min")
        candidates, diagnostics = self._scan_at_cutoff(date_et, cutoff)
        output_name = self._save_scan_output(date_et, action, cutoff, candidates, diagnostics)

        if action in CHECKPOINT_TIMES:
            return self._complete_checkpoint(
                state_name,
                state,
                generation,
                timestamp,
                date_et,
                action,
                cutoff,
                candidates,
                diagnostics,
                output_name,
            )
        return self._complete_wake(
            state_name,
            state,
            generation,
            timestamp,
            date_et,
            cutoff,
            candidates,
            diagnostics,
            output_name,
        )

    def _complete_checkpoint(
        self,
        state_name: str,
        state: dict[str, Any],
        generation: int | None,
        timestamp: pd.Timestamp,
        date_et: str,
        action: str,
        cutoff: pd.Timestamp,
        candidates: pd.DataFrame,
        diagnostics: dict[str, Any],
        output_name: str,
    ) -> TickResult:
        notification = send_notification(
            checkpoint_message(action, candidates, cutoff),
            title=f"Morita Bot {action} JST",
            priority=0 if action == "22:30" else 1,
            discord_message=full_discord_message(
                f"{action} JST S+A Check",
                checkpoint_candidates(candidates),
                cutoff,
            ),
            dry_run=self.dry_run,
        )
        s_tickers, a_tickers = ticker_lists(candidates)
        state.setdefault("slots", {})[action] = {
            "completed": True,
            "completed_at_et": timestamp.isoformat(),
            "decision_cutoff_et": cutoff.isoformat(),
            "s_tickers": s_tickers,
            "a_tickers": a_tickers,
            "notification": notification,
            "output": output_name,
        }
        if action == FINAL_EXECUTION_SLOT:
            state["noon_snapshot_complete"] = True
            state["noon_execution_tickers"] = sorted(set(s_tickers + a_tickers))
        self.store.write_json(state_name, state, generation=generation)
        return TickResult(
            "ok",
            action,
            date_et,
            {
                "s_tickers": s_tickers,
                "a_tickers": a_tickers,
                "notification": notification,
                "output": output_name,
                "diagnostics": diagnostics,
            },
        )

    def _complete_wake(
        self,
        state_name: str,
        state: dict[str, Any],
        generation: int | None,
        timestamp: pd.Timestamp,
        date_et: str,
        cutoff: pd.Timestamp,
        candidates: pd.DataFrame,
        diagnostics: dict[str, Any],
        output_name: str,
    ) -> TickResult:
        late = new_late_s_candidates(candidates, state)
        state["last_wake_scan_at_et"] = timestamp.isoformat()
        state["last_wake_cutoff_et"] = cutoff.isoformat()
        state["last_wake_output"] = output_name
        if late.empty:
            self.store.write_json(state_name, state, generation=generation)
            return TickResult("ok_no_new_s", "WAKE", date_et, {"output": output_name, "diagnostics": diagnostics})

        notification = send_notification(
            wake_message(late, state, cutoff),
            title="Morita Bot NEW S - WAKE",
            priority=2,
            retry=60,
            expire=600,
            sound="siren",
            discord_message=full_discord_message("POST-24:00 JST NEW S", late, cutoff),
            dry_run=self.dry_run,
        )
        sent = state.setdefault("late_s_emergency_sent", {})
        for _, row in late.iterrows():
            ticker = str(row.get("ticker", ""))
            sent[ticker] = {
                "sent_at_et": timestamp.isoformat(),
                "decision_cutoff_et": cutoff.isoformat(),
                "rank": "S",
                "production_adjusted_score": float(row.get("production_adjusted_score", 0) or 0),
                "notification": notification,
            }
        self.store.write_json(state_name, state, generation=generation)
        return TickResult(
            "ok_emergency_sent",
            "WAKE",
            date_et,
            {
                "tickers": sorted(late["ticker"].astype(str).unique().tolist()),
                "notification": notification,
                "output": output_name,
                "diagnostics": diagnostics,
            },
        )

    def _ensure_precompute(self, date_et: str, force: bool = False) -> dict[str, Any]:
        if self.store.exists(manifest_name(date_et)) and not force:
            manifest, _ = self.store.read_json(manifest_name(date_et), {})
            return manifest
        return build_precompute(
            self.store,
            date_et,
            config_path=self.config_path,
            period=self.precompute_period,
        )

    def _scan_at_cutoff(self, date_et: str, cutoff_et: pd.Timestamp) -> tuple[pd.DataFrame, dict[str, Any]]:
        bundle = load_precompute(self.store, date_et)
        tickers = sorted(set(bundle.results["ticker"].astype(str).tolist())) if not bundle.results.empty else []
        intraday = fetch_intraday_snapshots_at_cutoff(tickers, cutoff_et, interval="5m")
        coverage = len(intraday) / len(tickers) if tickers else 1.0
        min_coverage = float(os.environ.get("MIN_INTRADAY_COVERAGE", "0.50"))
        if tickers and coverage < min_coverage:
            raise RuntimeError(
                f"intraday coverage too low: {len(intraday)}/{len(tickers)} "
                f"({coverage:.1%}) < {min_coverage:.1%}"
            )

        config = sn.load_config(Path(self.config_path))
        candidates = production_entry._patched_select_candidates(
            bundle.results,
            bundle.histories,
            config,
            bundle.metadata,
            intraday,
        )
        diagnostics = {
            "base_candidate_count": int(len(tickers)),
            "intraday_snapshot_count": int(len(intraday)),
            "intraday_coverage": coverage,
            "selected_count": int(len(candidates)),
            "cutoff_et": normalize_et(cutoff_et).isoformat(),
            "cutoff_jst": normalize_et(cutoff_et).tz_convert("Asia/Tokyo").isoformat(),
            "precompute_created_at_utc": bundle.manifest.get("created_at_utc"),
            "latest_daily_bar": bundle.manifest.get("latest_daily_bar"),
        }
        return candidates, diagnostics

    def _save_scan_output(
        self,
        date_et: str,
        action: str,
        cutoff_et: pd.Timestamp,
        candidates: pd.DataFrame,
        diagnostics: dict[str, Any],
    ) -> str:
        token = normalize_et(cutoff_et).strftime("%H%M")
        safe_action = action.replace(":", "")
        prefix = f"scans/{date_et}/{safe_action}_{token}_{self.mode}"
        self.store.upload_bytes(f"{prefix}.csv", candidates.to_csv(index=False).encode("utf-8"), content_type="text/csv")
        self.store.upload_bytes(
            f"{prefix}.json",
            json.dumps(diagnostics, ensure_ascii=False, indent=2).encode("utf-8"),
            content_type="application/json",
        )
        return f"{prefix}.csv"
