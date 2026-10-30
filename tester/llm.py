"""Single entry point for every LLM call.

Every call is appended to a JSONL log (raw prompt + response) and cached by
content hash, so runs can be audited and replayed offline with LLM_REPLAY=1.
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "llm_cache"
LOG_PATH = ROOT / "runs" / "llm_calls.jsonl"


class LLMError(RuntimeError):
    pass


# Errors that mean "try another model" rather than "the request is wrong".
RETRYABLE = ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "timed out")


class LLM:
    def __init__(self, model: str | None = None, replay: bool | None = None):
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
        fallbacks = os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-3-flash-preview,gemini-3.1-flash-lite")
        self.models = [self.model] + [m.strip() for m in fallbacks.split(",") if m.strip() and m.strip() != self.model]
        self.replay = replay if replay is not None else os.environ.get("LLM_REPLAY") == "1"
        self._client = None

    def _gemini(self):
        if self._client is None:
            from google import genai
            from google.genai import types

            key = os.environ.get("GEMINI_API_KEY")
            if not key:
                raise LLMError("GEMINI_API_KEY is not set (see .env.example)")
            self._client = genai.Client(
                api_key=key,
                http_options=types.HttpOptions(
                    timeout=120_000, retry_options=types.HttpRetryOptions(attempts=2)
                ),
            )
        return self._client

    def generate(self, prompt: str, *, system: str = "", schema=None,
                 temperature: float = 0.2, purpose: str = "") -> str:
        """Return the model's text. With `schema` (a Pydantic model or type), the reply is JSON."""
        schema_name = getattr(schema, "__name__", str(schema)) if schema else None
        key = hashlib.sha256(
            json.dumps([self.model, system, prompt, schema_name, temperature]).encode()
        ).hexdigest()[:16]
        cache_file = CACHE_DIR / f"{key}.json"

        started = time.time()
        errors = []
        if cache_file.exists():
            cached = json.loads(cache_file.read_text())
            text, source, used = cached["response"], "cache", cached["model"]
        elif self.replay:
            raise LLMError(f"Replay mode: no cached response for {purpose or key}")
        else:
            try:
                text, used = self._call_with_fallback(prompt, system, schema, temperature, errors)
            except LLMError as exc:
                self._log({
                    "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "purpose": purpose, "models_tried": self.models, "source": "failed",
                    "error": str(exc), "fallback_errors": errors, "cache_key": key,
                    "latency_s": round(time.time() - started, 2), "prompt": prompt,
                })
                raise
            source = "live"
            CACHE_DIR.mkdir(exist_ok=True)
            cache_file.write_text(json.dumps(
                {"model": used, "purpose": purpose, "prompt": prompt, "response": text},
                indent=2, ensure_ascii=False,
            ))

        self._log({
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "purpose": purpose,
            "model": used,
            "source": source,
            "fallback_errors": errors,
            "cache_key": key,
            "latency_s": round(time.time() - started, 2),
            "system": system,
            "prompt": prompt,
            "response": text,
        })
        return text

    def _call_with_fallback(self, prompt, system, schema, temperature, errors) -> tuple[str, str]:
        for model in self.models:
            try:
                return self._call_gemini(model, prompt, system, schema, temperature), model
            except LLMError as exc:
                errors.append(f"{model}: {str(exc)[:200]}")
                if not any(code in str(exc) for code in RETRYABLE):
                    raise
        raise LLMError("All models failed:\n" + "\n".join(errors))

    def _call_gemini(self, model, prompt, system, schema, temperature) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system or None,
            response_mime_type="application/json" if schema else None,
            response_schema=schema,
        )
        try:
            response = self._gemini().models.generate_content(
                model=model, contents=prompt, config=config
            )
        except Exception as exc:  # network, quota, bad model name
            raise LLMError(f"{model} call failed: {exc}") from exc
        if not response.text:
            raise LLMError(f"{model} returned an empty response")
        return response.text

    @staticmethod
    def _log(entry: dict):
        LOG_PATH.parent.mkdir(exist_ok=True)
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
