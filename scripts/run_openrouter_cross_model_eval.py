#!/usr/bin/env python3
"""Run the layered-MSS cross-model evaluation through OpenRouter.

The default mode is a free dry run. Paid inference requires both --execute and
an explicit --approved-cap-usd argument. The API key is read only from the
OPENROUTER_API_KEY environment variable and is never written to disk.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "data" / "songs" / "jieyue" / "experiments" / "layered-mss-eval"
PLAN_PATH = EVAL_DIR / "openrouter-plan.json"
RESULTS_DIR = EVAL_DIR / "cross-model-results"
LOCAL_KEY_PATH = ROOT / ".secrets" / "openrouter_api_key"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_URL = "https://openrouter.ai/api/v1/model/{model_id}"
SYSTEM_PROMPT = """你正在参加音乐表示盲测。你只能依据用户给出的材料回答。
材料缺少证据时必须写 unknown；不得借助常识补全乐器、旋律、调性或拍号。
客观事实和自由联想必须明确分开。请按题号逐题作答，保持简洁。
每道客观题最多两句；每道开放题最多 100 个汉字。完整回答全部题目比展开论述更重要。"""


@dataclass(frozen=True)
class Price:
    prompt: Decimal
    completion: Decimal


class APIRequestError(RuntimeError):
    """An OpenRouter HTTP error with its diagnostic response body."""


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    if LOCAL_KEY_PATH.exists():
        if LOCAL_KEY_PATH.stat().st_mode & 0o077:
            raise SystemExit(f"Secret file permissions are too broad: {LOCAL_KEY_PATH}; expected 0600")
        key = LOCAL_KEY_PATH.read_text(encoding="utf-8").strip()
        if key:
            return key
    raise SystemExit(
        "OPENROUTER_API_KEY is not set and .secrets/openrouter_api_key does not exist. "
        "Run: python3 scripts/configure_openrouter_key.py"
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def neutralize_condition(text: str) -> str:
    """Remove experiment-arm names without hiding the supplied representation."""
    return (
        text.replace("附加音乐材料（客观自然语言＋曲线）：", "附加音乐材料：")
        .replace("附加音乐材料（分层 MSS＋曲线）：", "附加音乐材料：")
        .strip()
    )


def build_prompt(condition_name: str) -> str:
    condition = neutralize_condition(
        (EVAL_DIR / "conditions" / f"{condition_name}.txt").read_text(encoding="utf-8")
    )
    questions = (EVAL_DIR / "questions.blind.md").read_text(encoding="utf-8").strip()
    return f"{condition}\n\n以下是需要回答的问题：\n{questions}"


def planned_price(model: dict[str, Any]) -> Price:
    million = Decimal("1000000")
    return Price(
        prompt=Decimal(str(model["prompt_usd_per_million_tokens"])) / million,
        completion=Decimal(str(model["completion_usd_per_million_tokens"])) / million,
    )


def request_json(url: str, api_key: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="GET" if payload is None else "POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/zhizhou-xiee/Musiccc",
            "X-Title": "JieYue MSS evaluation",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise APIRequestError(f"HTTP {error.code}: {body[:4000]}") from error


def live_price(model_id: str, api_key: str) -> Price:
    url = MODEL_URL.format(model_id=urllib.parse.quote(model_id, safe="/"))
    model = request_json(url, api_key)["data"]
    pricing = model["pricing"]
    return Price(prompt=Decimal(pricing["prompt"]), completion=Decimal(pricing["completion"]))


def estimate_input_tokens(text: str, floor: int) -> int:
    # UTF-8 bytes / 3 is deliberately conservative for this Chinese-heavy packet.
    return max(floor, math.ceil(len((SYSTEM_PROMPT + text).encode("utf-8")) / 3))


def estimate_cost(
    plan: dict[str, Any],
    prices: dict[str, Price],
    prompts: dict[str, str],
    jobs: list[dict[str, Any]],
) -> tuple[Decimal, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    total = Decimal("0")
    output_tokens = int(plan["max_completion_tokens_per_call"])
    input_floor = int(plan["conservative_input_tokens_per_call"])
    for model in plan["models"]:
        model_id = model["id"]
        price = prices[model_id]
        model_cost = Decimal("0")
        for job in (item for item in jobs if item["model"] == model_id):
            input_tokens = estimate_input_tokens(prompts[job["condition"]], input_floor)
            model_cost += input_tokens * price.prompt + output_tokens * price.completion
        rows.append(
            {
                "model": model_id,
                "worst_case_usd": float(model_cost),
                "prompt_usd_per_token": str(price.prompt),
                "completion_usd_per_token": str(price.completion),
            }
        )
        total += model_cost
    return total, rows


def build_jobs(
    plan: dict[str, Any], *, smoke: bool = False, only_family: str | None = None
) -> list[dict[str, Any]]:
    jobs = []
    for model in plan["models"]:
        if only_family and model["family"] != only_family:
            continue
        conditions = ["c_mss_layers"] if smoke else plan["conditions"]
        seeds = [plan["seeds"][0]] if smoke else plan["seeds"]
        for condition in conditions:
            for repetition, seed in enumerate(seeds, start=1):
                jobs.append(
                    {
                        "model": model["id"],
                        "family": model["family"],
                        "condition": condition,
                        "repetition": repetition,
                        "seed": seed,
                    }
                )
    random.Random(20261015).shuffle(jobs)
    return jobs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Send paid inference requests.")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run one MSS request per model to verify response settings.",
    )
    parser.add_argument(
        "--only-family",
        choices=("GPT", "Claude", "Gemini"),
        help="Limit a smoke or full run to one registered model family.",
    )
    parser.add_argument(
        "--approved-cap-usd",
        type=Decimal,
        help="Explicit spending approval. Required with --execute.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = read_json(PLAN_PATH)
    prompts = {condition: build_prompt(condition) for condition in plan["conditions"]}
    jobs = build_jobs(plan, smoke=args.smoke, only_family=args.only_family)
    configured_cap = Decimal(str(plan["maximum_approved_cost_usd"]))
    prices = {model["id"]: planned_price(model) for model in plan["models"]}

    if args.execute:
        if args.approved_cap_usd is None:
            raise SystemExit("--execute requires --approved-cap-usd")
        if args.approved_cap_usd > configured_cap:
            raise SystemExit(f"Approved cap ${args.approved_cap_usd} exceeds repository cap ${configured_cap}")
        api_key = load_api_key()
        prices = {model["id"]: live_price(model["id"], api_key) for model in plan["models"]}
    else:
        api_key = ""

    estimated_total, estimate_rows = estimate_cost(plan, prices, prompts, jobs)
    summary = {
        "mode": "execute" if args.execute else "dry-run",
        "run_type": "smoke" if args.smoke else "full",
        "inference_calls": len(jobs),
        "worst_case_estimated_usd": float(estimated_total),
        "cost_cap_usd": float(configured_cap),
        "models": estimate_rows,
        "max_completion_tokens_per_call": plan["max_completion_tokens_per_call"],
        "conservative_input_tokens_per_call": plan["conservative_input_tokens_per_call"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.execute:
        print("Dry run only: no network inference request was sent.")
        return 0
    if estimated_total > args.approved_cap_usd:
        raise SystemExit(
            f"Live-price estimate ${estimated_total:.6f} exceeds approved cap ${args.approved_cap_usd}"
        )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    actual_cost = Decimal("0")
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "plan": summary,
        "jobs": [],
    }
    manifest_path = RESULTS_DIR / f"{run_id}.manifest.json"

    for index, job in enumerate(jobs, start=1):
        reasoning = (
            {"max_tokens": 256, "exclude": True}
            if job["family"] == "Gemini"
            else {"effort": "none", "exclude": True}
        )
        payload = {
            "model": job["model"],
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompts[job["condition"]]},
            ],
            "temperature": plan["temperature"],
            "seed": job["seed"],
            "max_tokens": plan["max_completion_tokens_per_call"],
            "reasoning": reasoning,
            "usage": {"include": True},
        }
        started = time.monotonic()
        try:
            response = request_json(CHAT_URL, api_key, payload=payload)
            elapsed_ms = round((time.monotonic() - started) * 1000)
            usage = response.get("usage") or {}
            call_cost = Decimal(str(usage.get("cost") or "0"))
            actual_cost += call_cost
            choice = response.get("choices", [{}])[0]
            message = choice.get("message") or {}
            record = {
                **job,
                "status": "ok",
                "elapsed_ms": elapsed_ms,
                "response_id": response.get("id"),
                "resolved_model": response.get("model"),
                "provider": response.get("provider"),
                "usage": usage,
                "finish_reason": choice.get("finish_reason"),
                "native_finish_reason": choice.get("native_finish_reason"),
                "content": message.get("content", ""),
            }
        except (APIRequestError, urllib.error.URLError, TimeoutError) as error:
            record = {**job, "status": "error", "error": str(error)}
        result_path = RESULTS_DIR / (
            f"{run_id}.{index:02d}.{job['family'].lower()}.{job['condition']}.r{job['repetition']}.json"
        )
        write_json(result_path, record)
        manifest["jobs"].append({**job, "file": result_path.name, "status": record["status"]})
        manifest["actual_cost_usd"] = float(actual_cost)
        write_json(manifest_path, manifest)
        print(f"[{index}/{len(jobs)}] {job['model']} {job['condition']} r{job['repetition']}: {record['status']}")
        if actual_cost > args.approved_cap_usd:
            raise SystemExit(f"Actual reported cost ${actual_cost} exceeded approved cap; stopped")

    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(manifest_path, manifest)
    print(f"Finished. OpenRouter reported cost: ${actual_cost}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
