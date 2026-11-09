"""Narrate each scene with Gemini text-to-speech (Interactions API), one WAV per scene.

    python tools/demo_video/tts.py            # skips scenes that already have audio
    python tools/demo_video/tts.py --force 4-receipt

Free tier: 3 requests a minute and 10 a day per TTS model, so calls are spaced out.
"""
import base64
import json
import sys
import time
import wave
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "backend"))
from app.config import load_settings  # noqa: E402

OUT = HERE / "out" / "audio"
URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


def synthesize(key: str, model: str, voice: str, style: str, text: str) -> bytes:
    body = {
        "model": model,
        "input": [{"type": "user_input", "content": [{"type": "text", "text": text,
                                                      "annotations": [{"type": "speech_metadata", "style": style}]}]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }
    r = httpx.post(URL, headers={"x-goog-api-key": key}, json=body, timeout=180)
    r.raise_for_status()
    for step in r.json()["steps"]:
        for part in step.get("content", []):
            if part.get("type") == "audio":
                return base64.b64decode(part["data"])
    raise RuntimeError("no audio in the response")


def seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def main() -> None:
    spec = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
    force = set(sys.argv[sys.argv.index("--force") + 1:]) if "--force" in sys.argv else set()
    key = load_settings().gemini_api_key
    OUT.mkdir(parents=True, exist_ok=True)
    last_call = 0.0
    total = 0.0
    for scene in spec["scenes"]:
        path = OUT / f"{scene['id']}.wav"
        if not path.exists() or scene["id"] in force:
            wait = 22 - (time.monotonic() - last_call)  # stay under 3 requests a minute
            if last_call and wait > 0:
                time.sleep(wait)
            last_call = time.monotonic()
            path.write_bytes(synthesize(key, spec["model"], spec["voice"], spec["style"], scene["text"]))
        d = seconds(path)
        total += d
        print(f"{scene['id']:10} {d:5.1f}s  {len(scene['text'].split())} words", flush=True)
    print(f"total narration {total:.1f}s")


if __name__ == "__main__":
    main()
