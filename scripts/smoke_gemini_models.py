"""Smoke-test free-tier Gemini generation models (no embeddings, no CoC)."""

from __future__ import annotations

import json
import os
import time

from dotenv import load_dotenv
from google import genai

MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
]

PROMPT = 'Return ONLY valid JSON: {"ok": true, "n": 1}'


def classify(exc: Exception) -> str:
    msg = str(exc)
    lower = msg.lower()
    if "503" in msg or "high demand" in lower or "unavailable" in lower:
        return "503_HIGH_DEMAND"
    if "429" in msg or "resource_exhausted" in lower:
        return "429_RATE_LIMIT"
    if "404" in msg or "not_found" in lower:
        return "404_NOT_FOUND"
    return "ERROR"


def main() -> None:
    load_dotenv()
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    results: list[dict] = []

    for model in MODELS:
        row: dict = {"model": model, "status": None, "preview": None}
        try:
            response = client.models.generate_content(model=model, contents=PROMPT)
            text = (response.text or "").strip().replace("\n", " ")[:120]
            row["status"] = "OK"
            row["preview"] = text
        except Exception as exc:  # noqa: BLE001 — smoke test wants every failure mode
            row["status"] = classify(exc)
            row["preview"] = str(exc)[:180]
        results.append(row)
        print(f"{row['status']:16}  {model}  ::  {row['preview']}")
        time.sleep(2)

    print("---")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
