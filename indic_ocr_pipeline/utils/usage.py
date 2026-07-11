"""Local usage tracking and quota management for API providers."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import requests

_PT = ZoneInfo("America/Los_Angeles")
WEEK_SECONDS = 7 * 24 * 3600
MAX_RECENT = 500


PROVIDER_INFO: dict[str, dict[str, Any]] = {
    "vision": {
        "label": "Google Cloud Vision",
        "description": "DOCUMENT_TEXT_DETECTION",
        "has_official_usage_api": False,
        "has_official_quota_api": False,
        "local_tracking": True,
    },
    "gemini": {
        "label": "Gemini",
        "description": "Gemini Flash Lite",
        "has_official_usage_api": False,
        "has_official_quota_api": False,
        "local_tracking": True,
    },
    "glm": {
        "label": "GLM-4V",
        "description": "GLM-4V-Flash",
        "has_official_usage_api": False,
        "has_official_quota_api": False,
        "local_tracking": True,
    },
    "iamhc": {
        "label": "IAMHC",
        "description": "Relay (gpt-4o-mini)",
        "has_official_usage_api": False,
        "has_official_quota_api": False,
        "local_tracking": True,
    },
    "groq": {
        "label": "Groq",
        "description": "Llama 3.3 70B",
        "has_official_usage_api": False,
        "has_official_quota_api": False,
        "local_tracking": True,
    },
    "openrouter": {
        "label": "OpenRouter",
        "description": "Gemini 2.0 Flash (free)",
        "has_official_usage_api": True,
        "has_official_quota_api": True,
        "local_tracking": True,
    },
}

PRICING: dict[str, dict[str, Any]] = {
    "vision": {
        "description": "Google Cloud Vision DOCUMENT_TEXT_DETECTION",
        "unit": "per 1000 pages",
        "rate_per_unit": 1.50,
        "free_monthly": 1000,
    },
    "gemini": {
        "description": "Gemini Flash Lite",
        "input_per_1M": 0.075,
        "output_per_1M": 0.30,
        "free_tier": True,
    },
    "glm": {"description": "GLM-4V-Flash", "free_tier": True},
    "groq": {
        "description": "Groq Llama 3.3 70B",
        "input_per_1M": 0.59,
        "output_per_1M": 0.79,
        "free_tier": True,
    },
    "openrouter": {"description": "OpenRouter Gemini 2.0 Flash", "free_tier": True},
}


def _now_pt() -> datetime:
    return datetime.now(_PT)


def _day_id(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=_PT).strftime("%Y-%m-%d")


def _yesterday_id() -> str:
    return (_now_pt() - timedelta(days=1)).strftime("%Y-%m-%d")


def _today_id() -> str:
    return _now_pt().strftime("%Y-%m-%d")


def _week_id(ts: float) -> str:
    dt = datetime.fromtimestamp(ts, tz=_PT)
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _month_id(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=_PT).strftime("%Y-%m")


def _this_month_id() -> str:
    return _now_pt().strftime("%Y-%m")


def _merge_agg(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and k in out and isinstance(out[k], dict):
            out[k] = _merge_agg(out[k], v)
        elif isinstance(v, (int, float)):
            out[k] = out.get(k, 0) + v
        else:
            out.setdefault(k, v)
    return out


def _zero_agg() -> dict:
    return {
        "requests": 0,
        "success": 0,
        "failures": 0,
        "retries": 0,
        "latency_ms": 0,
        "pages": 0,
        "images": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost": 0.0,
    }


def _compute_cost(
    provider: str,
    monthly_used: int,
    pages: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> float:
    p = PRICING.get(provider)
    if not p:
        return 0.0
    if p.get("free_tier"):
        return 0.0
    if provider == "vision":
        free = p.get("free_monthly", 0)
        billable = max(0, monthly_used - free)
        return (billable / 1000) * p["rate_per_unit"]
    cost = 0.0
    cost += (input_tokens / 1_000_000) * p.get("input_per_1M", 0)
    cost += (output_tokens / 1_000_000) * p.get("output_per_1M", 0)
    return cost


class UsageTracker:
    """Tracks per-request API usage across providers with daily/weekly/monthly rollups.

    Args:
        state_path: Path to the JSON file used for persistent state.
    """

    def __init__(self, state_path: Path) -> None:
        self._state_path = Path(state_path)
        self._state = self._load()

    def _load(self) -> dict:
        if self._state_path.exists():
            try:
                return json.loads(self._state_path.read_text())
            except Exception:
                pass
        return {
            "requests": [],
            "aggregates": {"daily": {}, "weekly": {}, "monthly": {}, "lifetime": {}},
        }

    def _save(self) -> None:
        tmp_path = self._state_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(self._state, indent=2))
        os.replace(tmp_path, self._state_path)

    def available(self, provider: str, limit: int = 0) -> bool:
        """Check whether a provider still has quota under the given limit."""
        if limit <= 0:
            return True
        period_id = _this_month_id() if provider == "vision" else _today_id()
        bucket = "monthly" if provider == "vision" else "daily"
        used = self._get_period_count(bucket, period_id, provider, "requests")
        return used < limit

    def consume(self, provider: str) -> None:
        pass  # record_request handles all tracking

    def _get_period_count(self, bucket_name: str, period_id: str, provider: str, field: str) -> int:
        bucket = self._state.get("aggregates", {}).get(bucket_name, {})
        pd = bucket.get(period_id, {}).get(provider, {})
        return pd.get(field, 0)

    def record_request(
        self,
        provider: str,
        model: str = "",
        success: bool = True,
        latency_ms: float = 0,
        retry_count: int = 0,
        error: str = "",
        pages: int = 0,
        images: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Record a single API request and update all rollup aggregates."""
        if provider not in PROVIDER_INFO:
            import logging

            logging.getLogger("usage").warning("Unknown provider %r — tracking anyway", provider)
        now = time.time()
        day = _day_id(now)
        week = _week_id(now)
        month = _month_id(now)

        monthly_used = self._get_monthly_count(
            month, provider, "pages" if provider == "vision" else "requests"
        )
        cost = _compute_cost(provider, monthly_used, pages, input_tokens, output_tokens)

        entry = {
            "t": now,
            "p": provider,
            "m": model,
            "ok": success,
            "l": round(latency_ms, 1),
            "r": retry_count,
            "e": error or None,
            "pg": pages,
            "im": images,
            "it": input_tokens,
            "ot": output_tokens,
            "c": round(cost, 6),
        }
        recent = self._state.setdefault("requests", [])
        recent.append(entry)
        if len(recent) > MAX_RECENT:
            self._state["requests"] = recent[-MAX_RECENT:]

        agg = {
            "requests": 1,
            "success": 1 if success else 0,
            "failures": 0 if success else 1,
            "retries": retry_count,
            "latency_ms": latency_ms,
            "pages": pages,
            "images": images,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
        }

        aggs = self._state.setdefault("aggregates", {})
        for bucket_name, period_id in [("daily", day), ("weekly", week), ("monthly", month)]:
            self._update_period(aggs.setdefault(bucket_name, {}), period_id, provider, agg)

        lifetime = aggs.setdefault("lifetime", {})
        if provider not in lifetime:
            lifetime[provider] = _zero_agg()
        lifetime[provider] = _merge_agg(lifetime[provider], agg)

        self._prune_old(aggs, "daily", 90)
        self._prune_old(aggs, "weekly", 52)
        self._prune_old(aggs, "monthly", 24)
        self._save()

    def _get_monthly_count(self, month: str, provider: str, field: str) -> int:
        monthly = self._state.get("aggregates", {}).get("monthly", {})
        md = monthly.get(month, {})
        pd = md.get(provider, {})
        return pd.get(field, 0)

    def _update_period(self, bucket: dict, period_id: str, provider: str, agg: dict) -> None:
        if period_id not in bucket:
            bucket[period_id] = {}
        if provider not in bucket[period_id]:
            bucket[period_id][provider] = _zero_agg()
        bucket[period_id][provider] = _merge_agg(bucket[period_id][provider], agg)

    @staticmethod
    def _prune_old(aggs: dict, period: str, max_count: int) -> None:
        keys = sorted(aggs.get(period, {}).keys())
        if len(keys) > max_count:
            for k in keys[:-max_count]:
                del aggs[period][k]

    def fetch_openrouter_official_usage(self, api_key: str) -> Optional[dict[str, Any]]:
        """Fetch official usage data from OpenRouter API."""
        if not api_key:
            return None
        try:
            resp = requests.get(
                "https://openrouter.ai/api/v1/key",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            d = resp.json().get("data", {})
            return {
                "available": True,
                "limit": d.get("limit"),
                "limit_remaining": d.get("limit_remaining"),
                "limit_reset": d.get("limit_reset"),
                "usage": d.get("usage"),
                "usage_daily": d.get("usage_daily"),
                "usage_weekly": d.get("usage_weekly"),
                "usage_monthly": d.get("usage_monthly"),
                "is_free_tier": d.get("is_free_tier", False),
            }
        except Exception:
            return None

    def _get_provider_agg(self, bucket: dict, period_id: str, provider: str) -> dict:
        period = bucket.get(period_id, {})
        return dict(period.get(provider, _zero_agg()))

    def dashboard(self, settings: dict | None = None) -> dict[str, Any]:
        """Build a dashboard snapshot of current usage across all providers."""
        now_ts = time.time()
        today = _day_id(now_ts)
        yesterday = _yesterday_id()
        week = _week_id(now_ts)
        month = _month_id(now_ts)

        aggs = self._state.get("aggregates", {})

        prov_result = {}
        for prov in PROVIDER_INFO:
            info = PROVIDER_INFO[prov]
            t = self._get_provider_agg(aggs.get("daily", {}), today, prov)
            y = self._get_provider_agg(aggs.get("daily", {}), yesterday, prov)
            w = self._get_provider_agg(aggs.get("weekly", {}), week, prov)
            m = self._get_provider_agg(aggs.get("monthly", {}), month, prov)
            lt = self._state.get("aggregates", {}).get("lifetime", {}).get(prov, _zero_agg())

            avg_lat = round(t["latency_ms"] / t["requests"], 1) if t["requests"] else 0.0

            prov_result[prov] = {
                "label": info["label"],
                "description": info["description"],
                "has_official_usage_api": info["has_official_usage_api"],
                "has_official_quota_api": info["has_official_quota_api"],
                "local_tracking": info["local_tracking"],
                "today": t,
                "yesterday": y,
                "this_week": w,
                "this_month": m,
                "lifetime": lt,
                "avg_latency_ms": avg_lat,
            }

        recent = self._state.get("requests", [])[-50:]
        recent_reversed = list(reversed(recent))

        return {
            "providers": prov_result,
            "today_id": today,
            "yesterday_id": yesterday,
            "week_id": week,
            "month_id": month,
            "recent_requests": recent_reversed,
        }
