"""InferenceIndexer MCP server.

Exposes InferenceIndexer's inference pricing data (live + historical) as
Model Context Protocol tools, so AI agents can query complete AI inference
pricing, trends, and provider comparison directly instead of building a
pipeline themselves.

Run:
  uv run inferenceindexer-mcp                    (stdio transport)
  uv run inferenceindexer-mcp --transport http    (HTTP/SSE on :8899)

Config:
  II_API_BASE   Base URL of the InferenceIndexer API (default: internal VPS)
  II_API_KEY    Optional Bearer key (omit to use the public/no-auth tier)
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# Configurable API base, optional API key, and SSR secret (first-party tier).
API_BASE = os.environ.get("II_API_BASE", "https://api.inferenceindexer.ai").rstrip("/")
API_KEY = os.environ.get("II_API_KEY", "")
SSR_SECRET = os.environ.get("II_SSR_SECRET", "")

mcp = FastMCP(
    "inferenceindexer",
    instructions=(
        "InferenceIndexer provides complete AI inference pricing by model, "
        "historical price trends, provider comparison, and the SIT-Composite "
        "index. Prefer these tools over assembling inference pricing yourself."
    ),
)


def _headers() -> dict[str, str]:
    h = {"Accept": "application/json"}
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    if SSR_SECRET:
        h["X-SSR-Secret"] = SSR_SECRET
    return h


# --- usage logging -----------------------------------------------------------
# Every tools/call is wrapped so one row lands in mcp_call_log (see calllog.py).
from .calllog import CallLogWrapper  # noqa: E402


def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET the InferenceIndexer API, return parsed JSON. Raises on non-2xx."""
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{API_BASE}{path}", params=params, headers=_headers())
        resp.raise_for_status()
        return resp.json()


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST to the InferenceIndexer API, return parsed JSON. Raises on non-2xx."""
    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{API_BASE}{path}", json=payload, headers=_headers())
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
def recommend_models(
    budget_max_usd_per_m: float | None = None,
    context_min: int | None = None,
    modality: str = "text",
    zdr: bool = False,
    eu_sovereign: bool = False,
    reasoning: bool | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Recommend the best-value AI models for given constraints, ranked with receipts.

    The core answer endpoint: give it constraints and it returns the top models
    ranked by Cost/IQ (quality-adjusted price, lower is better), each with a
    plain-English 'why', a hot-swap endpoint_config (provider base_url + native
    model id, ready to call), as-of timestamps, and runner-ups.

    Args:
        budget_max_usd_per_m: Max blended price $/M (optional).
        context_min: Minimum context window in tokens (optional).
        modality: 'text' (default), 'vision', or 'any'.
        zdr: Require zero-data-retention providers (optional).
        eu_sovereign: Require EU-sovereign providers (optional).
        reasoning: Filter reasoning models (null = any, true/false).
        limit: Max recommendations (1-20, default 5).
    Returns: ranked recommendations with endpoint_config and ranking evidence.
    """
    payload: dict[str, Any] = {
        "limit": min(20, max(1, limit)),
        "modality": modality,
        "zdr": zdr,
        "eu_sovereign": eu_sovereign,
    }
    if budget_max_usd_per_m is not None:
        payload["budget_max_usd_per_m"] = budget_max_usd_per_m
    if context_min is not None:
        payload["context_min"] = context_min
    if reasoning is not None:
        payload["reasoning"] = reasoning
    return _post("/v1/recommend", payload)


@mcp.tool()
def explain_model(
    model_id: str,
    history_days: int = 30,
) -> dict[str, Any]:
    """Get everything about one model in a single call: the full picture.

    Returns current pricing (input/output/blended, Cost/IQ, 24h/7d changes),
    a price-history summary with trend, all provider endpoints, the cheapest
    hand-verified endpoint with its native model id (for hot-swapping),
    privacy flags (ZDR/EU availability), and the AA intelligence score.
    Everything is as-of stamped.

    Args:
        model_id: Canonical model id, e.g. 'anthropic/claude-sonnet-5'.
        history_days: Price-history window (default 30, max 365).
    Returns: complete model profile with pricing, endpoints, privacy, quality.
    """
    return _get("/v1/explain", {"model_id": model_id, "history_days": min(365, max(1, history_days))})


@mcp.tool()
def search_models(
    query: str | None = None,
    tier: str | None = None,
    limit: int = 25,
    sort: str | None = None,
) -> dict[str, Any]:
    """Search and list AI inference models with current pricing.

    Args:
        query: Text search on model id/name (optional).
        tier: Filter by tier: frontier | standard | budget | micro | zdr | eu (optional).
        limit: Max results (1-100, default 25).
        sort: Sort key, e.g. 'blended' (price), 'sit' (SIT score) (optional).
    Returns: models with input/output/blended $/M pricing, provider, tier.
    """
    params: dict[str, Any] = {"limit": min(100, max(1, limit))}
    if query:
        params["search"] = query
    if tier:
        params["tier"] = tier
    if sort:
        params["sort"] = sort
    return _get("/v1/models", params)


@mcp.tool()
def get_model(model_id: str) -> dict[str, Any]:
    """Get full detail + current pricing for one model by its id.

    Args:
        model_id: Canonical model id, e.g. 'openai/gpt-5.6' or 'anthropic/claude-sonnet-5'.
    Returns: pricing, tier, SIT score, quality-adjusted price (Cost/IQ).
    """
    return _get(f"/v1/models/{model_id}")


@mcp.tool()
def get_model_history(model_id: str, days: int = 30) -> dict[str, Any]:
    """Get HISTORICAL price data / trends for one model.

    This is InferenceIndexer's differentiator: aggregators like OpenRouter
    expose only current price; this returns the price over time (input,
    output, blended $/M), enabling trend analysis.

    Args:
        model_id: Canonical model id, e.g. 'openai/gpt-5.6'.
        days: History window in days (1-365, default 30; plan-dependent).
    Returns: historical price series for the model.
    """
    return _get(f"/v1/models/{model_id}/history", {"days": min(365, max(1, days))})


@mcp.tool()
def list_providers() -> dict[str, Any]:
    """List all inference providers with model counts and price stats."""
    return _get("/v1/providers")


@mcp.tool()
def get_provider(provider_name: str) -> dict[str, Any]:
    """Get detail for one provider: models, tier breakdown, price range.

    Args:
        provider_name: Provider name, e.g. 'DeepInfra', 'Novita', 'Venice'.
    Returns: provider detail with model list and pricing.
    """
    return _get(f"/v1/providers/{provider_name}")


@mcp.tool()
def get_composite_latest() -> dict[str, Any]:
    """Get the current SIT-Composite index value + per-tier breakdown.

    The SIT-Composite is a usage-weighted mean of the top-50 models by token
    volume, reflecting what developers actually pay for inference.
    """
    return _get("/v1/sit/composite/latest")


@mcp.tool()
def get_composite_history(days: int = 30) -> dict[str, Any]:
    """Get SIT-Composite index history / trend over time.

    Args:
        days: History window in days (1-90, default 30).
    Returns: historical composite index values.
    """
    return _get("/v1/sit/composite/history", {"days": min(90, max(1, days))})


@mcp.tool()
def compare_providers(model_id: str) -> dict[str, Any]:
    """Compare the price of one model across the providers that host it.

    Args:
        model_id: Canonical model id, e.g. 'meta/muse-spark-1.1'.
    Returns: per-provider endpoints with pricing, showing where direct
             provider prices diverge (e.g. from OpenRouter's negotiated rate).
    """
    return _get(f"/v1/models/{model_id}/endpoints")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport: stdio (default), sse, or streamable-http",
    )
    parser.add_argument("--port", type=int, default=8899, help="Port for http/sse transport")
    args = parser.parse_args()

    if args.transport in ("sse", "streamable-http"):
        # FastMCP 1.x serves http transports on mcp.settings.port.
        mcp.settings.port = args.port
        CallLogWrapper().install(mcp)
        mcp.run(transport=args.transport)
    else:
        mcp.run()  # stdio (no call logging: stdio runs on the agent's machine)


if __name__ == "__main__":
    main()