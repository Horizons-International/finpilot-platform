"""Safely verify PERF_EMAIL/PERF_PASSWORD against the configured FinPilot API."""

from __future__ import annotations

import os
from typing import Any

import requests


def _safe_summary(payload: Any, *, email: str, password: str) -> str:
    """Summarize error details without echoing request inputs or returned tokens."""
    if not isinstance(payload, dict):
        return f"JSON response type={type(payload).__name__}"

    for key in ("message", "detail", "error"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            summary = value.strip()
            for secret in (password, email):
                if secret:
                    summary = summary.replace(secret, "[redacted]")
            return summary[:300]
        if isinstance(value, list):
            parts: list[str] = []
            for item in value[:3]:
                if isinstance(item, dict):
                    # Intentionally omit Pydantic's `input` field.
                    parts.append(
                        "type={!r}, loc={!r}, msg={!r}".format(
                            item.get("type"), item.get("loc"), item.get("msg")
                        )
                    )
            if parts:
                summary = "; ".join(parts)
                for secret in (password, email):
                    if secret:
                        summary = summary.replace(secret, "[redacted]")
                return summary[:300]

    data = payload.get("data")
    data_keys = sorted(data.keys()) if isinstance(data, dict) else []
    return f"JSON keys={sorted(payload.keys())}; data keys={data_keys}"


def main() -> int:
    base_url = os.getenv("PERF_BASE_URL", "http://127.0.0.1:8000").strip().rstrip("/")
    email = os.getenv("PERF_EMAIL", "").strip()
    password = os.getenv("PERF_PASSWORD", "")
    if not email or not password:
        print("Set PERF_EMAIL and PERF_PASSWORD in this PowerShell session first.")
        return 2

    url = f"{base_url}/api/v1/auth/login"
    print(f"Checking login endpoint: {url}")
    try:
        response = requests.post(
            url,
            json={"email": email, "password": password},
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"Connection failed: {type(exc).__name__}: {exc}")
        print(
            "Check that the API/HAProxy endpoint is "
            "running and PERF_BASE_URL is correct."
        )
        return 2

    print(f"HTTP status: {response.status_code}")
    request_id = response.headers.get("x-request-id")
    if request_id:
        print(f"Request ID: {request_id}")

    try:
        payload = response.json()
    except ValueError:
        payload = None

    data = payload.get("data") if isinstance(payload, dict) else None
    token = data.get("access_token") if isinstance(data, dict) else None
    if response.status_code == 200 and isinstance(token, str) and token:
        print(
            "Login succeeded; response contains data.access_token (token not printed)."
        )
        return 0

    if response.status_code == 200:
        print("Login returned HTTP 200, but data.access_token was not found.")
    if payload is not None:
        print(
            "Response detail: " + _safe_summary(payload, email=email, password=password)
        )
    else:
        print(
            "Response was not JSON; "
            f"content-type={response.headers.get('content-type', 'unknown')!r}; "
            f"body_length={len(response.content)} bytes. Response body omitted."
        )
    print(
        "Use the HTTP status/detail and API logs to distinguish invalid credentials, "
        "request validation, routing/proxy errors, or a server-side exception."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
