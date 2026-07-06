from __future__ import annotations

import re
from typing import Any

import pandas as pd


DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "lookback_hours": 48,
    "max_news_items": 8,
    "suppress_pushover_emergency": True,
}

# Precision is intentionally preferred over recall. A false positive here would
# suppress a legitimate immediate-review alert, while an unknown headline stays
# on the normal RS98 route.
EARNINGS_GUIDANCE_PATTERNS = (
    r"\braises? (full[ -]?year |fy\d{2,4} )?(guidance|outlook|forecast)\b",
    r"\bboosts? (full[ -]?year |fy\d{2,4} )?(guidance|outlook|forecast)\b",
    r"\bup(?:ward)?ly revis(?:es|ed) (guidance|outlook|forecast)\b",
    r"\bearnings beat\b",
    r"\bbeats? (earnings|estimates|expectations)\b",
)

CONTRACT_PARTNERSHIP_HIGH_CONFIDENCE_PATTERNS = (
    r"\bawarded? (?:a |an )?(?:multi[ -]?year )?(?:contract|deal)\b",
    r"\bwins? (?:a |an )?(?:major |multi[ -]?year )?(?:contract|deal|award)\b",
    r"\b(?:selected by|chosen by)\b",
    r"\b(?:signs?|secures?) (?:a |an )?(?:multi[ -]?year )?(?:contract|deal|agreement)\b",
    r"\b(?:announces?|enters?) (?:a |an )?(?:strategic )?(?:partnership|collaboration|alliance)\b",
    r"\bpartners? with\b",
    r"\b(?:receives?|lands?) (?:a |an )?(?:purchase )?order\b",
    r"\b(?:customer win|new customer|customer agreement)\b",
    r"\b(?:supply agreement|supply deal)\b",
)

CONTRACT_PARTNERSHIP_LOW_CONFIDENCE_TERMS = (
    "contract",
    "partnership",
    "partner",
    "collaboration",
    "alliance",
    "award",
    "purchase order",
    "order",
    "customer",
)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_timestamp(value: Any) -> pd.Timestamp:
    if value is None or value == "":
        return pd.NaT
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            unit = "ms" if abs(float(value)) > 10_000_000_000 else "s"
            return pd.to_datetime(value, unit=unit, utc=True)
        parsed = pd.to_datetime(value, utc=True, errors="coerce")
        return parsed if pd.notna(parsed) else pd.NaT
    except Exception:
        return pd.NaT


def _url_from(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _as_text(value.get("url") or value.get("href"))
    return ""


def _normalize_news_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    content = item.get("content")
    if not isinstance(content, dict):
        content = {}
    provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
    headline = _as_text(content.get("title") or item.get("title"))
    source = _as_text(
        provider.get("displayName")
        or provider.get("name")
        or item.get("publisher")
        or item.get("provider")
    )
    published = _coerce_timestamp(
        content.get("pubDate")
        or content.get("displayTime")
        or item.get("providerPublishTime")
        or item.get("published_at")
        or item.get("published")
    )
    url = _url_from(
        content.get("clickThroughUrl")
        or content.get("canonicalUrl")
        or item.get("link")
        or item.get("url")
    )
    return {
        "headline": headline,
        "source": source,
        "published_at_utc": published,
        "url": url,
    }


def _classify_headline(headline: str) -> tuple[str, str, str]:
    normalized = headline.lower()
    if any(re.search(pattern, normalized) for pattern in EARNINGS_GUIDANCE_PATTERNS):
        return "EARNINGS_GUIDANCE", "high", "earnings_or_guidance_headline"
    if any(re.search(pattern, normalized) for pattern in CONTRACT_PARTNERSHIP_HIGH_CONFIDENCE_PATTERNS):
        return "CONTRACT_PARTNERSHIP", "high", "contract_partnership_headline"
    if any(term in normalized for term in CONTRACT_PARTNERSHIP_LOW_CONFIDENCE_TERMS):
        return "CONTRACT_PARTNERSHIP", "low", "ambiguous_contract_partnership_term"
    return "UNKNOWN", "unknown", "no_supported_catalyst_pattern"


def _base_result(fetch_status: str = "not_requested") -> dict[str, Any]:
    return {
        "catalyst_type": "UNKNOWN",
        "catalyst_confidence": "unknown",
        "catalyst_source": "",
        "catalyst_headline": "",
        "catalyst_timestamp_utc": "",
        "catalyst_url": "",
        "catalyst_fetch_status": fetch_status,
        "action_route": "STANDARD_BREAKOUT_REVIEW",
        "action_reason": "unknown_or_no_recent_news",
    }


def catalyst_route_for(ticker: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Classify recent news only for a small set of already-qualified candidates.

    High-confidence contract/partnership/customer-win/order headlines become
    NEWS_SPIKE_WATCH_ONLY. Unknown, unavailable, and low-confidence headlines
    deliberately remain on the normal breakout-review path.
    """
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(config or {})
    if not bool(cfg.get("enabled", True)):
        result = _base_result("disabled")
        result["action_reason"] = "catalyst_routing_disabled"
        return result

    try:
        import yfinance as yf

        yahoo_ticker = yf.Ticker(str(ticker).strip().upper())
        try:
            raw_news = yahoo_ticker.get_news(count=int(cfg.get("max_news_items", 8)), tab="news")
        except TypeError:
            raw_news = yahoo_ticker.get_news(count=int(cfg.get("max_news_items", 8)))
        except Exception:
            raw_news = getattr(yahoo_ticker, "news", [])
    except Exception as exc:
        result = _base_result(f"error:{type(exc).__name__}")
        result["action_reason"] = "news_fetch_failed_kept_standard"
        return result

    if not isinstance(raw_news, list) or not raw_news:
        return _base_result("no_news")

    now = pd.Timestamp.now(tz="UTC")
    lookback_hours = max(1, int(cfg.get("lookback_hours", 48)))
    cutoff = now - pd.Timedelta(hours=lookback_hours)
    normalized = []
    for item in raw_news:
        parsed = _normalize_news_item(item)
        timestamp = parsed.get("published_at_utc")
        if not parsed.get("headline") or pd.isna(timestamp) or timestamp < cutoff:
            continue
        normalized.append(parsed)

    if not normalized:
        return _base_result("no_recent_timestamped_news")

    normalized.sort(key=lambda item: item["published_at_utc"], reverse=True)
    selected: dict[str, Any] | None = None
    selected_type = "UNKNOWN"
    selected_confidence = "unknown"
    selected_reason = "no_supported_catalyst_pattern"
    for item in normalized:
        catalyst_type, confidence, reason = _classify_headline(item["headline"])
        if catalyst_type != "UNKNOWN":
            selected = item
            selected_type = catalyst_type
            selected_confidence = confidence
            selected_reason = reason
            break

    if selected is None:
        result = _base_result("ok_no_supported_pattern")
        latest = normalized[0]
        result.update(
            {
                "catalyst_source": latest["source"],
                "catalyst_headline": latest["headline"],
                "catalyst_timestamp_utc": latest["published_at_utc"].isoformat(),
                "catalyst_url": latest["url"],
            }
        )
        return result

    action_route = "STANDARD_BREAKOUT_REVIEW"
    if selected_type == "CONTRACT_PARTNERSHIP" and selected_confidence == "high":
        action_route = "NEWS_SPIKE_WATCH_ONLY"

    return {
        "catalyst_type": selected_type,
        "catalyst_confidence": selected_confidence,
        "catalyst_source": selected["source"],
        "catalyst_headline": selected["headline"],
        "catalyst_timestamp_utc": selected["published_at_utc"].isoformat(),
        "catalyst_url": selected["url"],
        "catalyst_fetch_status": "ok",
        "action_route": action_route,
        "action_reason": selected_reason,
    }
