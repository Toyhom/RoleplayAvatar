"""Measure warm streaming latency and throughput of a running local LLM service."""

import argparse
import asyncio
import json
import math
import os
import time
from pathlib import Path

import httpx

from roleplay_avatar.agents import sse_events


def percentile(values, fraction):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


async def measure(client, url, payload, backend):
    start = time.perf_counter()
    first, last, text, gaps, usage = None, None, "", [], {}
    async with client.stream("POST", url, json=payload) as response:
        response.raise_for_status()
        events = response.aiter_lines() if backend == "local" else sse_events(response.aiter_lines())
        async for data in events:
            if not data or data == "[DONE]":
                continue
            item = json.loads(data)
            if "error" in item:
                raise RuntimeError("Inference service returned an error")
            if item.get("usage"):
                usage = item["usage"]
            chunk = item.get("text", "") if backend == "local" else (
                (item.get("choices") or [{}])[0].get("delta", {}).get("content") or ""
            )
            if chunk:
                now = time.perf_counter()
                if first is None:
                    first = now
                if last is not None:
                    gaps.append(now - last)
                last = now
                text += chunk
    if not text:
        raise RuntimeError("Inference returned no visible text")
    result = {"ttft_s": first - start, "elapsed_s": time.perf_counter() - start,
              "characters": len(text), "inter_chunk_p95_s": percentile(gaps, 0.95),
              "usage": usage}
    return result


async def benchmark(url, model, *, backend="openai", requests=8, concurrency=1, max_tokens=128,
                    prompt="Describe a quiet forest in five sentences.", template_kwargs=None, warmups=1):
    if min(requests, concurrency, max_tokens) < 1 or warmups < 0:
        raise ValueError("Request, concurrency and token counts must be positive")
    messages = [{"role": "user", "content": prompt}]
    payload = {"max_tokens": max_tokens, "temperature": 0}
    if backend == "local":
        payload.update(persona="You are a concise storytelling companion.", messages=messages)
        route = "/chat"
    else:
        payload.update(model=model, messages=[{"role": "system", "content": "You are a concise storytelling companion."},
                                            *messages], stream=True, stream_options={"include_usage": True})
        if template_kwargs:
            payload["chat_template_kwargs"] = template_kwargs
        route = "/chat/completions"
    key = os.environ.get("AVATAR_LLM_API_KEY")
    headers = {"Authorization": "Bearer " + key} if key else {}
    async with httpx.AsyncClient(trust_env=False, timeout=300, headers=headers,
                                 limits=httpx.Limits(max_connections=concurrency + 1)) as client:
        endpoint = url.rstrip("/") + route
        for _ in range(warmups):
            await asyncio.gather(*(measure(client, endpoint, payload, backend)
                                   for _ in range(min(concurrency, requests))))
        semaphore = asyncio.Semaphore(concurrency)

        async def run():
            async with semaphore:
                try:
                    return await measure(client, endpoint, payload, backend)
                except (httpx.HTTPError, RuntimeError, ValueError) as error:
                    return {"error": type(error).__name__}

        started = time.perf_counter()
        results = await asyncio.gather(*(run() for _ in range(requests)))
        elapsed = time.perf_counter() - started
    success = [r for r in results if "error" not in r]
    tokens = [r["usage"].get("completion_tokens") for r in success]
    summary = {"backend": backend, "model": model, "requests": requests, "concurrency": concurrency,
               "max_tokens": max_tokens, "warmups": warmups,
               "warmup_concurrency": min(concurrency, requests), "prompt": prompt,
               "template_kwargs": template_kwargs or {}, "completed": len(success), "failed": requests - len(success),
               "wall_s": elapsed, "ttft_p50_s": percentile([r["ttft_s"] for r in success], 0.5),
               "ttft_p95_s": percentile([r["ttft_s"] for r in success], 0.95),
               "latency_p50_s": percentile([r["elapsed_s"] for r in success], 0.5),
               "latency_p95_s": percentile([r["elapsed_s"] for r in success], 0.95),
               "characters_per_s": sum(r["characters"] for r in success) / elapsed,
               "output_tokens_per_s": sum(tokens) / elapsed if tokens and all(t is not None for t in tokens) else None,
               "results": results}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="OpenAI /v1 base URL or native service base URL")
    parser.add_argument("--model", default="roleplay")
    parser.add_argument("--backend", choices=["openai", "local"], default="openai")
    parser.add_argument("--requests", type=int, default=8)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--prompt", default="Describe a quiet forest in five sentences.")
    parser.add_argument("--template-kwargs", type=json.loads, default={})
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(benchmark(args.url, args.model, backend=args.backend, requests=args.requests,
                                  concurrency=args.concurrency, max_tokens=args.max_tokens, prompt=args.prompt,
                                  template_kwargs=args.template_kwargs, warmups=args.warmups))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "results"}, indent=2))
    if result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
