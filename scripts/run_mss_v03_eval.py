#!/usr/bin/env python3
"""Measure and evaluate the MSS/0.3 candidate with the registered models.

``--token-check`` sends one one-token request per model and exists only to
measure each provider's real input-token accounting before the full test.
Paid calls always require an explicit cap.
"""

from __future__ import annotations

import argparse
import json
import random
import time
import urllib.error
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from run_openrouter_cross_model_eval import (
    APIRequestError,
    CHAT_URL,
    EVAL_DIR,
    SYSTEM_PROMPT,
    estimate_input_tokens,
    live_price,
    load_api_key,
    read_json,
    request_json,
    write_json,
)


ROOT = Path(__file__).resolve().parents[1]
POC_DIR = ROOT / "data" / "songs" / "jieyue" / "experiments" / "mss-v0.3-poc"
RESULTS_DIR = POC_DIR / "openrouter-results"
CANDIDATE_PATH = POC_DIR / "outputs" / "mss_v03_800.txt"
BASELINE_RUN = EVAL_DIR / "cross-model-results" / "20261015T065625Z.manifest.json"
CONDITION = "d_mss_v03"


def build_prompt() -> str:
    baseline = (EVAL_DIR / "conditions" / "a_lyrics_only.txt").read_text(encoding="utf-8").strip()
    candidate = CANDIDATE_PATH.read_text(encoding="utf-8").strip()
    questions = (EVAL_DIR / "questions.blind.md").read_text(encoding="utf-8").strip()
    return f"{baseline}\n\n附加音乐材料：\n{candidate}\n\n以下是需要回答的问题：\n{questions}"


def baseline_tokens() -> dict[str, int]:
    manifest = read_json(BASELINE_RUN)
    values: dict[str, list[int]] = {}
    result_dir = BASELINE_RUN.parent
    for job in manifest["jobs"]:
        if job["condition"] != "a_lyrics_only" or job["status"] != "ok":
            continue
        record = read_json(result_dir / job["file"])
        values.setdefault(job["family"], []).append(int(record["usage"]["prompt_tokens"]))
    return {family: round(sum(items) / len(items)) for family, items in values.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--token-check", action="store_true")
    parser.add_argument("--approved-cap-usd", type=Decimal)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = read_json(EVAL_DIR / "openrouter-plan.json")
    prompt = build_prompt()
    baselines = baseline_tokens()
    repetitions = [(1, plan["seeds"][0])] if args.token_check else list(
        enumerate(plan["seeds"], start=1)
    )
    jobs = [
        {
            "model": model["id"],
            "family": model["family"],
            "repetition": repetition,
            "seed": seed,
        }
        for model in plan["models"]
        for repetition, seed in repetitions
    ]
    random.Random(20261015).shuffle(jobs)

    if args.execute and args.approved_cap_usd is None:
        raise SystemExit("--execute requires --approved-cap-usd")
    if args.approved_cap_usd is not None and args.approved_cap_usd > Decimal("5"):
        raise SystemExit("The user-approved cumulative ceiling is $5")

    api_key = load_api_key() if args.execute else ""
    prices = (
        {model["id"]: live_price(model["id"], api_key) for model in plan["models"]}
        if args.execute
        else {
            model["id"]: type("Price", (), {
                "prompt": Decimal(str(model["prompt_usd_per_million_tokens"])) / Decimal(1_000_000),
                "completion": Decimal(str(model["completion_usd_per_million_tokens"])) / Decimal(1_000_000),
            })()
            for model in plan["models"]
        }
    )
    # Gemini omits usage for a one-token reasoning response, so keep the probe
    # tiny but large enough for every provider to return accounting metadata.
    max_tokens = 16 if args.token_check else int(plan["max_completion_tokens_per_call"])
    input_estimate = estimate_input_tokens(prompt, int(plan["conservative_input_tokens_per_call"]))
    worst_case = sum(
        input_estimate * prices[job["model"]].prompt + max_tokens * prices[job["model"]].completion
        for job in jobs
    )
    summary = {
        "mode": "execute" if args.execute else "dry-run",
        "run_type": "token-check" if args.token_check else "full",
        "inference_calls": len(jobs),
        "candidate_utf8_bytes": len(CANDIDATE_PATH.read_bytes()),
        "worst_case_estimated_usd": float(worst_case),
        "approved_cap_usd": float(args.approved_cap_usd or 0),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.execute:
        return 0
    if worst_case > args.approved_cap_usd:
        raise SystemExit(f"Worst-case estimate ${worst_case:.6f} exceeds the supplied cap")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "plan": summary,
        "baseline_prompt_tokens": baselines,
        "candidate_snapshot": CANDIDATE_PATH.read_text(encoding="utf-8"),
        "jobs": [],
    }
    manifest_path = RESULTS_DIR / f"{run_id}.manifest.json"
    actual_cost = Decimal("0")
    for index, job in enumerate(jobs, start=1):
        reasoning = (
            {"max_tokens": 8 if args.token_check else 256, "exclude": True}
            if job["family"] == "Gemini"
            else {"effort": "none", "exclude": True}
        )
        payload = {
            "model": job["model"],
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": plan["temperature"],
            "seed": job["seed"],
            "max_tokens": max_tokens,
            "reasoning": reasoning,
            "usage": {"include": True},
        }
        started = time.monotonic()
        try:
            response = request_json(CHAT_URL, api_key, payload=payload)
            usage = response.get("usage") or {}
            call_cost = Decimal(str(usage.get("cost") or "0"))
            actual_cost += call_cost
            choice = response.get("choices", [{}])[0]
            if not usage.get("prompt_tokens"):
                raise APIRequestError("Provider returned no prompt-token usage")
            record = {
                **job,
                "condition": CONDITION,
                "status": "ok",
                "elapsed_ms": round((time.monotonic() - started) * 1000),
                "response_id": response.get("id"),
                "resolved_model": response.get("model"),
                "provider": response.get("provider"),
                "usage": usage,
                "candidate_token_delta": int(usage.get("prompt_tokens", 0)) - baselines[job["family"]],
                "finish_reason": choice.get("finish_reason"),
                "native_finish_reason": choice.get("native_finish_reason"),
                "content": (choice.get("message") or {}).get("content", ""),
            }
        except (APIRequestError, urllib.error.URLError, TimeoutError) as error:
            record = {**job, "condition": CONDITION, "status": "error", "error": str(error)}
        result_path = RESULTS_DIR / (
            f"{run_id}.{index:02d}.{job['family'].lower()}.{CONDITION}.r{job['repetition']}.json"
        )
        write_json(result_path, record)
        manifest["jobs"].append(
            {**job, "condition": CONDITION, "file": result_path.name, "status": record["status"]}
        )
        manifest["actual_cost_usd"] = float(actual_cost)
        write_json(manifest_path, manifest)
        delta = record.get("candidate_token_delta", "error")
        print(f"[{index}/{len(jobs)}] {job['family']} r{job['repetition']}: {record['status']} delta={delta}")
        if actual_cost > args.approved_cap_usd:
            raise SystemExit("Actual reported cost exceeded the supplied cap; stopped")

    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(manifest_path, manifest)
    print(f"Finished. OpenRouter reported cost: ${actual_cost}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
