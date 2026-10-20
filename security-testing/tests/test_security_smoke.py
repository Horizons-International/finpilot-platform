"""Non-destructive black-box security checks for the isolated FinPilot test API."""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Iterator
from urllib.parse import urlsplit

import httpx
import pytest


def _validated_base_url() -> str:
    """Refuse non-loopback targets to reduce accidental out-of-scope testing."""
    raw = os.getenv("SECURITY_TEST_BASE_URL", "http://127.0.0.1:18080").strip()
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError("SECURITY_TEST_BASE_URL must use http:// or https://")
    if not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError(
            "SECURITY_TEST_BASE_URL must be a simple URL without credentials"
        )
    host = parsed.hostname.casefold()
    is_loopback = host == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise RuntimeError(
            "These automated checks are restricted to localhost/loopback targets. "
            "Do not remove this guard for an unapproved target."
        )
    if parsed.query or parsed.fragment:
        raise RuntimeError("SECURITY_TEST_BASE_URL must not include query or fragment")
    return raw.rstrip("/")


@pytest.fixture(scope="module")
def api() -> Iterator[httpx.Client]:
    """Connect only after confirming the isolated test API is listening."""
    base_url = _validated_base_url()
    client = httpx.Client(
        base_url=base_url,
        timeout=httpx.Timeout(5.0),
        follow_redirects=False,
    )
    try:
        # Probe TCP rather than GET /health: the isolated Compose stack uses a
        # deliberately tiny per-route request limit, and a preflight HTTP call
        # would consume one of the requests the tests are meant to measure.
        parsed = urlsplit(base_url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            with socket.create_connection((parsed.hostname, port), timeout=3.0):
                pass
        except OSError as exc:
            pytest.fail(
                "The security-test API is not reachable at "
                f"{base_url}. These are black-box tests and require the isolated "
                "Compose API to be running first. From the repository root run "
                r"'.\security-testing\scripts\start-security-test-env.ps1'. "
                "Then check 'docker compose --project-name finpilot-security-test "
                "--file docker/docker-compose.security-test.yml ps -a' and the "
                "security-backend logs. Original connection error: "
                f"{exc}",
                pytrace=False,
            )
        yield client
    finally:
        client.close()


def test_api_health_has_security_headers(api: httpx.Client) -> None:
    response = api.get("/health")
    assert response.status_code == 200, response.text[:500]

    expected_headers = {
        "x-request-id",
        "x-content-type-options",
        "x-frame-options",
        "referrer-policy",
        "permissions-policy",
        "cross-origin-opener-policy",
        "cross-origin-resource-policy",
        "cache-control",
        "pragma",
        "content-security-policy",
    }
    missing = sorted(
        name for name in expected_headers if not response.headers.get(name)
    )
    assert not missing, f"Missing security headers: {', '.join(missing)}"
    assert response.headers["x-content-type-options"].lower() == "nosniff"
    assert response.headers["x-frame-options"].upper() == "DENY"
    assert response.headers["cache-control"].lower() == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_anonymous_requests_cannot_access_privileged_security_routes(
    api: httpx.Client,
) -> None:
    admin_response = api.get("/api/v1/auth/admin-only")
    assert admin_response.status_code == 401, (
        "Expected anonymous admin-only request to be rejected with 401; "
        f"received {admin_response.status_code}"
    )

    events_response = api.get("/api/v1/security/events")
    assert events_response.status_code == 401, (
        "Expected anonymous security-events request to be rejected with 401; "
        f"received {events_response.status_code}"
    )


def test_login_rejects_malformed_input_at_schema_boundary(api: httpx.Client) -> None:
    response = api.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": "short"},
    )
    assert response.status_code == 422, (
        "Invalid input should be rejected by schema validation before authentication; "
        f"received {response.status_code}"
    )


def test_route_rate_limit_returns_429_and_retry_after(api: httpx.Client) -> None:
    """The dedicated Compose lab sets a route threshold of three requests."""
    probe_path = "/__security_testing_rate_limit_probe__"
    responses = [api.get(probe_path) for _ in range(4)]
    statuses = [response.status_code for response in responses]
    assert statuses[:3] == [404, 404, 404], (
        "The isolated route threshold is expected to permit three requests; "
        f"observed statuses: {statuses}"
    )
    limited = responses[3]
    assert limited.status_code == 429, (
        "The fourth request should be rate limited in the dedicated test stack; "
        f"received {limited.status_code}"
    )
    assert limited.headers.get("retry-after", "").isdigit(), (  # fmt: skip
        "A rate-limited response should include a numeric Retry-After header"
    )
    assert int(limited.headers["retry-after"]) >= 1
