"""LLM access: provider switch, fallback chain, response cache and a daily call cap.

Every answer is cached by (task, prompt, schema, image). When the free quota runs out, or when
LLM_PROVIDER=replay, only cached answers are served, so the hosted demo keeps working for the
judges even with no key. Models were chosen from a 2026-10-21 probe on the demo receipt:
gemini-3.5-flash-lite with thinkingLevel=minimal read it correctly in 2.7 s (24 s with default
thinking); gemma-4-31b-it was also correct and has a much larger free daily quota.
"""
import base64
import hashlib
import json
import logging
import socket
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from .db import now_iso

log = logging.getLogger("uvicorn.error")  # uvicorn's logger, so lines show up in the server log
# Model -> extra generationConfig. Gemma ignores thinking settings, so it gets none.
GEMINI_MODELS: dict[str, dict[str, Any]] = {
    "gemini-3.5-flash-lite": {"thinkingConfig": {"thinkingLevel": "minimal"}},
    "gemma-4-31b-it": {},
}
DEFAULT_CHAIN = ["gemini-3.5-flash-lite", "gemma-4-31b-it"]


class AIUnavailable(Exception):
    """No cached answer and no live model could produce one."""


@dataclass
class Answer:
    data: dict[str, Any]
    model: str
    cached: bool
    seconds: float = 0.0  # how long the live call took; 0 for cached answers


class Provider(Protocol):
    def generate_json(self, *, prompt: str, schema: dict, image: bytes | None, mime: str | None) -> tuple[dict, str]: ...


class GeminiProvider:
    """Google Gemini API (generativelanguage.googleapis.com), trying each model in order."""

    HOST = "generativelanguage.googleapis.com"

    def __init__(self, api_key: str, models: list[str] | None = None, timeout: float = 60.0,
                 transport: httpx.BaseTransport | None = None):
        # Bind to IPv4: a container without working IPv6 can stall on IPv6 attempts before falling back.
        transport = transport or httpx.HTTPTransport(local_address="0.0.0.0", retries=1)
        self._http = httpx.Client(base_url=f"https://{self.HOST}/v1beta", timeout=timeout,
                                  headers={"x-goog-api-key": api_key}, transport=transport)
        self.models = models or DEFAULT_CHAIN

    def warm_up(self) -> None:
        """Open the connection early and log how long each step takes. On a fresh Render container
        the first generate call took 25-44 s (later ones ~3 s). Listing models costs no quota."""
        started = time.monotonic()
        try:
            families = ",".join(sorted({"v6" if info[0] == socket.AF_INET6 else "v4"
                                        for info in socket.getaddrinfo(self.HOST, 443, type=socket.SOCK_STREAM)}))
        except OSError as e:
            families = f"dns error: {e}"
        resolved = time.monotonic()
        try:
            r = self._http.get("/models", params={"pageSize": 1})
            log.info("gemini warm-up: dns %.1fs (%s), first request %.1fs, HTTP %s", resolved - started,
                     families, time.monotonic() - resolved, r.status_code)
        except httpx.HTTPError as e:
            log.warning("gemini warm-up failed after %.1fs (%s): %s", time.monotonic() - started, families, e)

    def generate_json(self, *, prompt: str, schema: dict, image: bytes | None, mime: str | None) -> tuple[dict, str]:
        parts: list[dict[str, Any]] = [{"text": prompt}]
        if image is not None:
            parts.append({"inline_data": {"mime_type": mime or "image/jpeg", "data": base64.b64encode(image).decode()}})
        errors = []
        for model in self.models:
            body = {
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema,
                                     "temperature": 0, **GEMINI_MODELS.get(model, {})},
            }
            started = time.monotonic()
            try:
                r = self._http.post(f"/models/{model}:generateContent", json=body)
            except httpx.HTTPError as e:
                log.warning("gemini %s failed after %.1fs: %s", model, time.monotonic() - started, e)
                errors.append(f"{model}: {e}")
                continue
            log.info("gemini %s HTTP %s in %.1fs", model, r.status_code, time.monotonic() - started)
            if r.status_code != 200:  # 429 quota, 503 overloaded, ...: try the next model
                errors.append(f"{model}: HTTP {r.status_code}")
                continue
            try:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text), model
            except (KeyError, IndexError, ValueError) as e:
                errors.append(f"{model}: unreadable answer ({e})")
        raise AIUnavailable("; ".join(errors) or "no models configured")


class ReplayProvider:
    """Never calls out: used when there is no key, so only cached answers work."""

    def generate_json(self, **_: Any) -> tuple[dict, str]:
        raise AIUnavailable("live AI is off (LLM_PROVIDER=replay); only demo receipts have answers")


@dataclass
class LLM:
    provider: Provider
    daily_cap: int = 300

    def lookup(self, conn: sqlite3.Connection, *, task: str, prompt: str, schema: dict,
               image: bytes | None = None) -> Answer | None:
        """A cached answer, or None. Never calls a model."""
        row = conn.execute("SELECT response, model FROM llm_cache WHERE key = ?",
                           (cache_key(task, prompt, schema, image),)).fetchone()
        return Answer(json.loads(row["response"]), row["model"], cached=True) if row else None

    def ask(self, conn: sqlite3.Connection, *, task: str, prompt: str, schema: dict,
            image: bytes | None = None, mime: str | None = None) -> Answer:
        key = cache_key(task, prompt, schema, image)
        cached = self.lookup(conn, task=task, prompt=prompt, schema=schema, image=image)
        if cached:
            return cached

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        used = conn.execute("SELECT calls FROM llm_usage WHERE day = ?", (today,)).fetchone()
        if used and used["calls"] >= self.daily_cap:
            raise AIUnavailable(f"today's AI budget ({self.daily_cap} calls) is used up; demo receipts still work")
        conn.execute("INSERT INTO llm_usage (day, calls) VALUES (?, 1) "
                     "ON CONFLICT(day) DO UPDATE SET calls = calls + 1", (today,))

        started = time.monotonic()
        data, model = self.provider.generate_json(prompt=prompt, schema=schema, image=image, mime=mime)
        seconds = round(time.monotonic() - started, 1)
        conn.execute("INSERT OR REPLACE INTO llm_cache (key, task, model, response, created_at) VALUES (?, ?, ?, ?, ?)",
                     (key, task, model, json.dumps(data), now_iso()))
        return Answer(data, model, cached=False, seconds=seconds)


def cache_key(task: str, prompt: str, schema: dict, image: bytes | None) -> str:
    h = hashlib.sha256()
    for part in (task, prompt, json.dumps(schema, sort_keys=True)):
        h.update(part.encode())
        h.update(b"\x00")
    if image is not None:
        h.update(hashlib.sha256(image).digest())
    return h.hexdigest()


def make_llm(provider_name: str, api_key: str, daily_cap: int) -> LLM:
    if provider_name == "gemini" and api_key:
        return LLM(GeminiProvider(api_key), daily_cap=daily_cap)
    return LLM(ReplayProvider(), daily_cap=daily_cap)
