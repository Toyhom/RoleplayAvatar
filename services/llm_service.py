"""Streaming Transformers service for causal-LM families, multiple GPUs and optional quantization."""

import argparse
import asyncio
import json
import os
import queue
import sys
import threading
import time

sys.modules["flash_attn"] = None
from pathlib import Path

import torch
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    StoppingCriteria,
    StoppingCriteriaList,
    TextIteratorStreamer,
)

parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument("--port", type=int, default=18110)
parser.add_argument("--role", default="roleplay")
parser.add_argument("--device-map", default=None)
parser.add_argument("--dtype", choices=["bfloat16", "float16", "float32"], default=None)
parser.add_argument("--quantization", choices=["none", "int8", "int4"], default=None)
parser.add_argument("--context", type=int)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from roleplay_avatar.models import configured_path, model_options
from roleplay_avatar.text_stream import StopTextFilter, generation_eos_ids

options = model_options(args.role)
torch.manual_seed(options.get("seed", 42))
tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
if options.get("chat_template"):
    tokenizer.chat_template = configured_path(options["chat_template"]).read_text()
if not tokenizer.chat_template:
    raise ValueError("Configure models.<role>.chat_template for a checkpoint without a chat template")
load_options = {
    "torch_dtype": getattr(torch, args.dtype or options.get("dtype", "bfloat16")),
    "device_map": args.device_map or options.get("device_map", "auto"),
    "attn_implementation": "sdpa",
    "local_files_only": True,
}
quantization = args.quantization or options.get("quantization", "none")
if quantization != "none":
    from transformers import BitsAndBytesConfig

    load_options["quantization_config"] = BitsAndBytesConfig(
        load_in_4bit=quantization == "int4",
        load_in_8bit=quantization == "int8",
        bnb_4bit_compute_dtype=load_options["torch_dtype"],
        bnb_4bit_quant_type="nf4",
    )
model = AutoModelForCausalLM.from_pretrained(args.model, **load_options).eval()
eos_ids = generation_eos_ids(
    model.generation_config.eos_token_id, tokenizer.eos_token_id, options.get("eos_token_id")
)
requested_context = args.context if args.context is not None else options.get("context", 8192)
if requested_context < 16:
    raise ValueError("Context must contain at least 16 tokens")
context_limit = min(requested_context, model.config.max_position_embeddings)
lock = asyncio.Lock()
app = FastAPI(title="Roleplay LLM")


class Chat(BaseModel):
    persona: str = Field(max_length=16000)
    messages: list[dict[str, str]]
    max_tokens: int = Field(default=1024, ge=8, le=4096)
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=0.9, gt=0, le=1)
    repetition_penalty: float = Field(default=1.0, ge=0.5, le=2)
    seed: int | None = Field(default=None, ge=0)
    stop: list[str] = Field(default_factory=list, max_length=8)


class Stop(StoppingCriteria):
    def __init__(self, event, stop_strings, start):
        self.event = event
        self.stop_strings = stop_strings
        self.start = start

    def __call__(self, input_ids, scores, **kwargs):
        if self.event.is_set():
            return True
        if self.stop_strings:
            text = tokenizer.decode(input_ids[0, self.start :], skip_special_tokens=True)
            return any(stop in text for stop in self.stop_strings if stop)
        return False


@app.get("/healthz")
def health():
    return {
        "status": "ready",
        "model": Path(args.model).name,
        "device": torch.cuda.get_device_name(),
        "allocated_gib": [
            round(torch.cuda.memory_allocated(i) / 2**30, 3) for i in range(torch.cuda.device_count())
        ],
        "path": args.model,
        "role": args.role,
        "context": context_limit,
    }


@app.post("/chat")
async def chat(payload: Chat, request: Request):
    messages = [{"role": "system", "content": payload.persona}]
    messages.extend(
        [
            {"role": m["role"], "content": m["content"][:5000]}
            for m in payload.messages[-20:]
            if m.get("role") in {"user", "assistant"} and isinstance(m.get("content"), str)
        ]
    )

    async def generate():
        async with lock:
            stop = threading.Event()
            errors = []
            streamer = TextIteratorStreamer(
                tokenizer, skip_prompt=True, skip_special_tokens=True, timeout=0.2
            )
            bounded = list(messages)
            while True:
                prompt = tokenizer.apply_chat_template(
                    bounded,
                    tokenize=False,
                    add_generation_prompt=True,
                    **options.get("template_kwargs", {"enable_thinking": False}),
                )
                inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
                if inputs.input_ids.shape[-1] + payload.max_tokens <= context_limit:
                    break
                if len(bounded) <= 2:
                    yield json.dumps({"error": "ContextLimitExceeded"}) + "\n"
                    return
                del bounded[1:3]  # retain persona and the newest exchange
            inputs = inputs.to(model.get_input_embeddings().weight.device)

            def run():
                try:
                    if payload.seed is not None:
                        torch.manual_seed(payload.seed)
                    with torch.inference_mode():
                        model.generate(
                            **inputs,
                            streamer=streamer,
                            max_new_tokens=payload.max_tokens,
                            do_sample=payload.temperature > 0,
                            temperature=max(0.01, payload.temperature),
                            top_p=payload.top_p,
                            repetition_penalty=payload.repetition_penalty,
                            stopping_criteria=StoppingCriteriaList(
                                [Stop(stop, payload.stop, inputs.input_ids.shape[-1])]
                            ),
                            pad_token_id=tokenizer.eos_token_id,
                            eos_token_id=eos_ids,
                        )
                except Exception as exc:  # noqa: BLE001 -- native generation errors become stream errors
                    errors.append(type(exc).__name__)
                    streamer.end()

            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            text_filter = StopTextFilter(payload.stop)
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        item = await asyncio.to_thread(streamer.text_queue.get, True, 0.2)
                    except queue.Empty:
                        if not thread.is_alive():
                            break
                        continue
                    if item == streamer.stop_signal:
                        break
                    text = text_filter.feed(item)
                    if text:
                        yield json.dumps({"text": text}, ensure_ascii=False) + "\n"
                    if text_filter.stopped:
                        stop.set()
                        break
                remaining = text_filter.finish()
                if remaining:
                    yield json.dumps({"text": remaining}, ensure_ascii=False) + "\n"
                if errors:
                    yield json.dumps({"error": errors[0]}) + "\n"
            finally:
                stop.set()
                await asyncio.shield(asyncio.to_thread(thread.join))

    return StreamingResponse(generate(), media_type="application/x-ndjson")


metadata = {
    "node": os.environ.get("GPUQ_NODE"),
    "job": os.environ.get("GPUQ_JOB_REF"),
    "port": args.port,
    "status": "ready",
    "started": time.time(),
    "model": args.model,
}
(root / "outputs/services").mkdir(parents=True, exist_ok=True)
(root / f"outputs/services/llm-{args.port}.json").write_text(json.dumps(metadata, indent=2))
print("LLM_READY", json.dumps(metadata), flush=True)
uvicorn.run(app, host="127.0.0.1", port=args.port)
