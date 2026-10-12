"""Provider-metered with/without proof: total input, not pack estimates.

`select` reports a local pack estimate — it cannot know the calling
agent's system prompt, conversation history, or tool plumbing, so its
number is never a total call size. This module closes that gap: it sends
arm A (every eligible chunk, the no-selection baseline) and arm B (the
harness-selected pack) as single-shot chat/completions calls through a
local OpenAI-compatible proxy and reports the PROVIDER-COUNTED input
tokens from each response's usage object. Same envelope both arms (model,
temperature 0, max_tokens, roles) — the only difference is the context
handed over. Fresh single-shot calls carry no conversation history; each
arm is one independent call.

Arm B rendering varies with --formats: `standard` (the default pack
rendering) and `toon` (the same pack in TOON-subset compact form, so the
TOON structure tax is measured in provider-counted input, not estimates).
`headroom` rewrites the full dump through the headroom package when it is
installed, and refuses cleanly when it is not.

Free-only: any model slug outside FREE_MODELS is refused, so a paid model
can never be invoked by accident. The proxy key comes from the
CLIPROXY_KEY environment variable (never a file, never committed).
Tokens sent/received only — no cost claim, ever.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from . import tokens as tokens_mod

# Free-only allowlist: slugs served by the local pool at zero cost.
FREE_MODELS = (
    "muse-spark-1.3-contributor-free",
    "nemotron-3-ultra-free",
    "mimo-v2.6-flash-free",
    "OR-Laguna",
    "poolside/laguna-s-2.1:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-lightning:free",
    "qwen/qwen3.8-27b:free",
    "z-ai/glm-5.2:free",
)

# Context windows in tokens. Pool-advertised values are exact; the
# OpenRouter free-route values are conservative assumptions, stated here.
MODEL_WINDOWS = {
    "muse-spark-1.3-contributor-free": (1048576, "pool-advertised"),
    "nemotron-3-ultra-free": (1000000, "pool-advertised"),
    "mimo-v2.6-flash-free": (200000, "pool-advertised"),
    "OR-Laguna": (128000, "assumed"),
    "poolside/laguna-s-2.1:free": (128000, "assumed"),
    "nvidia/nemotron-3-ultra-550b-a55b:free": (128000, "assumed"),
    "nvidia/nemotron-3.5-lightning:free": (128000, "assumed"),
    "qwen/qwen3.8-27b:free": (32000, "assumed"),
    "z-ai/glm-5.2:free": (128000, "assumed"),
}

FORMATS = ("standard", "toon", "headroom")

RETRYABLE = {429, 502, 503, 529}


def refuse_unless_free(model: str) -> None:
    """Raise unless ``model`` is a free-only allowlisted slug."""
    if model not in FREE_MODELS:
        raise ValueError(
            f"refusing non-free model {model!r}; allowlist: {sorted(FREE_MODELS)}")


def window_gate(model: str, estimator_tokens: int) -> dict:
    """Measure-then-fit: skip packs that cannot fit the model's window."""
    window, source = MODEL_WINDOWS.get(model, (32000, "assumed-fallback"))
    return {"window": window, "window_source": source,
            "fits": estimator_tokens < window}


def estimator_input_tokens(messages: list) -> int:
    """Pinned local count of the exact message contents about to be sent."""
    return sum(tokens_mod.count(m.get("content", "")) for m in messages)


def post_chat(model: str, body: dict, key: str, base_url: str,
              timeout_s: int = 120, max_attempts: int = 4,
              pace_s: float = 2.0) -> dict:
    """POST one chat/completions call; retry transient upstream errors."""
    url = base_url.rstrip("/") + "/v1/chat/completions"
    payload = json.dumps(body).encode("utf-8")
    attempts, last_error = 0, None
    start_all = time.perf_counter()
    while attempts < max_attempts:
        attempts += 1
        req = urllib.request.Request(
            url, data=payload,
            headers={"Authorization": f"Bearer {key}",
                      "Content-Type": "application/json"},
            method="POST")
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and data.get("error") and not data.get("choices"):
                last_error = (f"provider error in 200 body: "
                              f"{json.dumps(data.get('error'))[:300]}")
                raise _RetryableBody(last_error)
            return {"ok": True, "status": resp.status, "response": data,
                    "attempts": attempts,
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                    "elapsed_ms": round((time.perf_counter() - start_all) * 1000, 2)}
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8")[:500]
            except Exception:  # noqa: BLE001
                detail = ""
            last_error = f"HTTP {e.code}: {detail}"
            if e.code not in RETRYABLE or attempts >= max_attempts:
                break
            time.sleep(pace_s * attempts)
        except _RetryableBody as e:
            last_error = str(e)
            if attempts >= max_attempts:
                break
            time.sleep(pace_s * attempts * 2)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_error = f"{type(e).__name__}: {e}"
            if attempts >= max_attempts:
                break
            time.sleep(pace_s * attempts)
    return {"ok": False, "error": last_error or "unknown error",
            "attempts": attempts,
            "elapsed_ms": round((time.perf_counter() - start_all) * 1000, 2)}


class _RetryableBody(Exception):
    """HTTP-200 body carrying a provider error instead of choices."""


def extract_metered(response: dict) -> dict:
    """Pull provider-counted usage + output text from a response."""
    usage = (response or {}).get("usage") or {}
    choices = (response or {}).get("choices") or [{}]
    msg = (choices[0] or {}).get("message") or {}
    details_in = usage.get("prompt_tokens_details") or {}
    details_out = usage.get("completion_tokens_details") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cached_tokens": details_in.get("cached_tokens"),
        "reasoning_tokens": details_out.get("reasoning_tokens"),
        "model_served": (response or {}).get("model"),
        "finish_reason": (choices[0] or {}).get("finish_reason"),
        "output_text": msg.get("content"),
    }


def build_bodies(task_text: str, repository_id: str, pipeline,
                 model: str, token_budget: int,
                 formats: list, exclude_paths: list | None = None) -> dict:
    """Serialize arm A + one arm-B per format with the identical envelope.

    Arm A is the harness's own no-selection baseline (every indexed chunk
    concatenated) — not a claim about what any IDE, TUI, or agent sends.
    """
    from . import schemas
    from .providers.openai_compat import render_openai_chat

    req = schemas.SelectRequest(
        repository_id=repository_id, task=task_text,
        token_budget=token_budget, exclude_paths=exclude_paths or [])
    storage = pipeline._storage_for(repository_id)
    chunks = storage.load_chunks()
    pkg_b = pipeline.select_context(req)
    ev_a = [{
        "path": c.path, "start_line": c.start_line, "end_line": c.end_line,
        "symbol": c.symbol, "content": c.content, "category": "supporting",
        "selection_reasons": [], "score": 0,
    } for c in chunks]
    pkg_a = schemas.EvidencePackage(
        request_id="metered-arm-a", repository_id=pkg_b.repository_id,
        task=pkg_b.task, policy_version=pkg_b.policy_version,
        index_version=pkg_b.index_version, model_version=pkg_b.model_version,
        metrics={}, redaction_summary={}, evidence=ev_a, markdown="",
        execution={})

    bodies: dict[str, dict] = {}
    std = render_openai_chat(pkg_a, model=model)
    bodies["A_full"] = {
        "messages": std["messages"],
        "estimator_tokens": estimator_input_tokens(std["messages"]),
        "renderer": "standard",
    }
    for fmt in formats:
        if fmt == "standard":
            rendered = render_openai_chat(pkg_b, model=model)
            bodies["B_harness"] = {
                "messages": rendered["messages"],
                "estimator_tokens": estimator_input_tokens(rendered["messages"]),
                "renderer": "standard",
            }
        elif fmt == "toon":
            from .providers.compact import render_compact
            messages = [{"role": "system", "content": render_compact(pkg_b)},
                        {"role": "user", "content": task_text}]
            bodies["T_toon"] = {
                "messages": messages,
                "estimator_tokens": estimator_input_tokens(messages),
                "renderer": "compact-ours",
            }
        elif fmt == "headroom":
            try:
                import headroom  # noqa: F401
            except ImportError as e:
                raise ValueError(
                    "format 'headroom' needs the headroom package installed; "
                    "it is not") from e
            dump = "\n\n".join(c.content for c in chunks)
            hr = headroom.compress(
                [{"role": "tool", "name": "repo_dump", "content": dump}])
            m0 = hr.messages[0]
            hr_text = m0["content"] if isinstance(m0, dict) else m0.get("content", "")
            messages = [{"role": "system", "content": hr_text},
                        {"role": "user", "content": task_text}]
            bodies["H_headroom"] = {
                "messages": messages,
                "estimator_tokens": estimator_input_tokens(messages),
                "renderer": "headroom",
                "format_extra": {
                    "tokens_before": hr.tokens_before,
                    "tokens_after": hr.tokens_after,
                    "ratio": round(hr.compression_ratio, 4)},
            }
        else:
            raise ValueError(f"unknown format {fmt!r}; expected one of {FORMATS}")
    for spec in bodies.values():
        spec["gate"] = window_gate(model, spec["estimator_tokens"])
    return bodies


def run_metered(task_text: str, repository_id: str, pipeline, model: str,
                key: str, base_url: str, token_budget: int, formats: list,
                exclude_paths: list | None = None,
                max_tokens: int = 256, temperature: float = 0.0,
                pace_s: float = 2.0) -> list:
    """Send every arm once; return one record per arm with metered usage."""
    refuse_unless_free(model)
    arms = build_bodies(task_text, repository_id, pipeline, model,
                        token_budget, formats, exclude_paths)
    order = ["A_full"] + [a for a in arms if a != "A_full"]
    records = []
    for arm in order:
        spec = arms[arm]
        rec: dict[str, Any] = {"arm": arm, "model": model,
                               "renderer": spec["renderer"],
                               "estimator_input_tokens": spec["estimator_tokens"],
                               "window_gate": spec["gate"],
                               "temperature": temperature,
                               "max_tokens": max_tokens}
        if "format_extra" in spec:
            rec["format_extra"] = spec["format_extra"]
        if not spec["gate"]["fits"]:
            rec.update({"ok": False, "skipped": True,
                        "error": "estimator pack exceeds model window"})
        else:
            body = {"model": model, "messages": spec["messages"],
                    "temperature": temperature, "max_tokens": max_tokens}
            res = post_chat(model, body, key, base_url, pace_s=pace_s)
            rec.update(res)
            if res.get("ok"):
                if isinstance(res["response"], dict) and res["response"].get("error") \
                        and not res["response"].get("choices"):
                    rec.update({"ok": False,
                                "error": f"provider error in 200 body: "
                                         f"{json.dumps(res['response'].get('error'))[:200]}"})
                else:
                    rec["metered"] = extract_metered(res["response"])
        records.append(rec)
        time.sleep(pace_s)
    return records


def summarize(records: list) -> dict:
    """Per-arm provider-counted totals + each arm's delta vs arm A.

    Every comparison shows the quantity AND the percent — the reporting
    rule for all with/without claims.
    """
    arms = {}
    for r in records:
        met = r.get("metered") or {}
        if r.get("ok") and met.get("prompt_tokens") is not None:
            arms[r["arm"]] = {
                "metered_input": met.get("prompt_tokens"),
                "metered_output": met.get("completion_tokens"),
                "metered_cached": met.get("cached_tokens"),
                "model_served": met.get("model_served"),
                "finish_reason": met.get("finish_reason"),
                "estimator_input": r.get("estimator_input_tokens"),
            }
        else:
            arms[r["arm"]] = {"ok": False,
                              "error": r.get("error", "no metered usage")}
    ref = (arms.get("A_full") or {}).get("metered_input")
    for arm, row in arms.items():
        if arm == "A_full" or not row.get("metered_input") or not ref:
            row["delta_vs_A_qty"] = None
            row["delta_vs_A_pct"] = None
            continue
        qty = ref - row["metered_input"]
        row["delta_vs_A_qty"] = qty
        row["delta_vs_A_pct"] = round(qty / ref * 100, 2)
    return {"arms": arms, "reference_arm": "A_full",
            "reference_metered_input": ref}


def meter_footer(summary: dict, model: str) -> str:
    """One-line provider-counted with/without verdict, qty + % always."""
    from .summary import fmt_tokens
    arms = summary.get("arms", {})
    ref = summary.get("reference_metered_input")
    parts = []
    for arm, row in arms.items():
        if arm == "A_full" or not row.get("metered_input"):
            continue
        qty, pct = row["delta_vs_A_qty"], row["delta_vs_A_pct"]
        parts.append(f"{arm} {fmt_tokens(row['metered_input'])} "
                     f"(-{fmt_tokens(qty)}, -{pct}%)")
    if ref is None or not parts:
        return (f"ane-harness meter: no provider-counted usage on {model} "
                f"(all arms failed or were window-skipped)")
    return (f"ane-harness meter: provider-counted total input on {model}: "
            f"without harness {fmt_tokens(ref)} vs {'; '.join(parts)}")
