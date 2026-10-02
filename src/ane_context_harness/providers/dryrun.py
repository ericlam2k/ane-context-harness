"""Stage 0/1 of the provider evaluation: MOCK + DRY-RUN ONLY — never network.

Serializes an EvidencePackage for a provider and reports the DERIVED cost of
the request under a stated price, plus whether a live call would be allowed
under the configured spend cap. No socket, no HTTP client, no credentials:
``dry_run`` is safe to run in tests with the network removed entirely.
"""
from __future__ import annotations

import json

from .. import tokens as tokens_mod
from . import serialize

# Same headline price as evaluation.DERIVED reporting; purely illustrative.
DEFAULT_USD_PER_MILLION_INPUT = 3.00


def derived_request_cost_usd(provider: str, package, *,
                             usd_per_million: float = DEFAULT_USD_PER_MILLION_INPUT,
                             **serialize_kwargs) -> tuple[dict, int, float]:
    """Serialize ``package`` for ``provider``; return (body, tokens, cost).

    Cost is DERIVED from token counts × the stated price — never billed.
    """
    body = serialize(provider, package, **serialize_kwargs)
    text = body if isinstance(body, str) else json.dumps(body, sort_keys=True)
    n_tokens = tokens_mod.count(text)
    cost = round(n_tokens * usd_per_million / 1_000_000, 6)
    return body, n_tokens, cost


def dry_run(provider: str, package, *,
            usd_per_million: float = DEFAULT_USD_PER_MILLION_INPUT,
            max_provider_spend_usd: float = 0.0,
            **serialize_kwargs) -> dict:
    """Stage-1 dry run: zero network calls, derived cost, cap check.

    ``max_provider_spend_usd`` mirrors config ``limits.max_provider_spend_usd``;
    the default 0.0 means live calls are disabled and ``live_run_allowed`` is
    always False. The check compares the cap against this request's DERIVED
    estimate only (stage 2 additionally pre-flights the whole run).
    """
    body, n_tokens, cost = derived_request_cost_usd(
        provider, package, usd_per_million=usd_per_million, **serialize_kwargs)
    cap = float(max_provider_spend_usd)
    return {
        "stage": "1-dry-run",
        "provider": provider,
        "network_calls": 0,
        "request": body,
        "request_tokens": n_tokens,
        "estimated_cost_usd_derived": cost,
        "usd_per_million_input": usd_per_million,
        "max_provider_spend_usd": cap,
        "live_run_allowed": bool(cap > 0.0 and cost <= cap),
        "cost_status": "DERIVED from token counts × stated price; not billed",
        "note": "no network performed; stage 2 requires explicit approval "
                "and max_provider_spend_usd > 0",
    }
