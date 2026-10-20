"""Configurable Locust performance scenarios for FinPilot's FastAPI API.

All write-producing workloads are disabled by default. Enable them only against
an isolated test/staging environment populated with synthetic fixtures.
"""

from __future__ import annotations

import logging
import os
import random
from typing import Any
from uuid import uuid4

from locust import HttpUser, between, task

from performance.perf_helpers import (
    build_risk_analysis_payload,
    extract_access_token,
    parse_bool,
    parse_csv_ids,
)

logger = logging.getLogger(__name__)

# A small synthetic PDF; use only in a non-production performance environment.
_SAMPLE_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 80]/Contents 4 0 R"
    b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 43>>stream\n"
    b"BT /F1 12 Tf 10 40 Td (FinPilot performance fixture) Tj ET\n"
    b"endstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


class FinPilotPerformanceUser(HttpUser):
    """Mixed weighted workload targeting representative FinPilot API endpoints."""

    wait_time = between(
        float(os.getenv("PERF_WAIT_MIN_SECONDS", "0.2")),
        float(os.getenv("PERF_WAIT_MAX_SECONDS", "1.0")),
    )

    def on_start(self) -> None:
        self._auth_failed = False
        self.email = os.getenv("PERF_EMAIL", "").strip()
        self.password = os.getenv("PERF_PASSWORD", "")
        self.token = os.getenv("PERF_ACCESS_TOKEN", "").strip()
        self.customer_ids = parse_csv_ids(os.getenv("PERF_CUSTOMER_IDS"))
        single_customer = os.getenv("PERF_CUSTOMER_ID", "").strip()
        if single_customer and single_customer not in self.customer_ids:
            self.customer_ids.append(single_customer)
        self.verification_case_ids = parse_csv_ids(
            os.getenv("PERF_VERIFICATION_CASE_IDS")
        )
        single_case = os.getenv("PERF_VERIFICATION_CASE_ID", "").strip()
        if single_case and single_case not in self.verification_case_ids:
            self.verification_case_ids.append(single_case)
        self.document_ids = parse_csv_ids(os.getenv("PERF_DOCUMENT_IDS"))
        single_document = os.getenv("PERF_DOCUMENT_ID", "").strip()
        if single_document and single_document not in self.document_ids:
            self.document_ids.append(single_document)
        self.document_type_id = os.getenv("PERF_DOCUMENT_TYPE_ID", "").strip()
        self.customer_test_phone_numbers = parse_csv_ids(
            os.getenv("PERF_TEST_PHONE_NUMBERS")
        )
        self.fixture_customer_id = os.getenv("PERF_CUSTOMER_ID", "").strip()
        self.fixture_verification_case_id = os.getenv(
            "PERF_VERIFICATION_CASE_ID", ""
        ).strip()
        self.allow_customer_creation = parse_bool(
            os.getenv("PERF_ENABLE_CUSTOMER_CREATION")
        )
        self.allow_workflow_writes = parse_bool(
            os.getenv("PERF_ENABLE_WORKFLOW_WRITES")
        )
        self.allow_verification_writes = parse_bool(
            os.getenv("PERF_ENABLE_VERIFICATION_WRITES")
        )
        self.allow_document_uploads = parse_bool(
            os.getenv("PERF_ENABLE_DOCUMENT_UPLOADS")
        )
        self.allow_report_writes = parse_bool(os.getenv("PERF_ENABLE_REPORT_WRITES"))
        self.allow_ai = parse_bool(os.getenv("PERF_ENABLE_AI"))

        if not self.token and not (self.email and self.password):
            logger.error(
                "Missing performance credentials. Set PERF_EMAIL and PERF_PASSWORD, "
                "or set PERF_ACCESS_TOKEN for token-only testing."
            )
            self._abort_startup()
            return
        if not self.token and not self._authenticate():
            self._abort_startup()
            return

    def _abort_startup(self) -> None:
        """Stop promptly when a user cannot authenticate instead of idling headless."""
        self._auth_failed = True
        runner = self.environment.runner
        if runner is not None:
            logger.error(
                "Stopping the Locust run because authentication setup failed. "
                "See the login failure message and performance/results/*_failures.csv."
            )
            runner.quit()

    def _safe_response_summary(self, response: Any) -> str:
        """Describe an API error without logging credentials or bearer tokens."""
        try:
            payload = response.json()
        except (ValueError, TypeError):
            return (
                "non-JSON response; "
                f"content-type={response.headers.get('content-type', 'unknown')!r}; "
                f"body_length={len(response.text)}"
            )

        if isinstance(payload, dict):
            for key in ("message", "detail", "error"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    summary = value.strip()
                    for secret in (self.password, self.email):
                        if secret:
                            summary = summary.replace(secret, "[redacted]")
                    return summary[:300]
                if isinstance(value, list):
                    # Keep validation context, but never print submitted input values.
                    parts: list[str] = []
                    for item in value[:3]:
                        if isinstance(item, dict):
                            kind = item.get("type")
                            location = item.get("loc")
                            message = item.get("msg")
                            parts.append(
                                f"type={kind!r}, loc={location!r}, msg={message!r}"
                            )
                    if parts:
                        summary = "; ".join(parts)
                        for secret in (self.password, self.email):
                            if secret:
                                summary = summary.replace(secret, "[redacted]")
                        return summary[:300]
            data = payload.get("data")
            data_keys = sorted(data.keys()) if isinstance(data, dict) else []
            return f"JSON keys={sorted(payload.keys())}; data keys={data_keys}"

        return f"JSON response type={type(payload).__name__}"

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _authenticate(self) -> bool:
        """Log in, retain the token, and record a sanitized failure explanation."""
        if not self.email or not self.password:
            return bool(self.token)
        with self.client.post(
            "/api/v1/auth/login",
            name="POST /api/v1/auth/login",
            json={"email": self.email, "password": self.password},
            catch_response=True,
        ) as response:
            request_id = response.headers.get("x-request-id")
            request_suffix = f"; request_id={request_id}" if request_id else ""
            if response.status_code != 200:
                detail = self._safe_response_summary(response)
                reason = (
                    f"Login returned HTTP {response.status_code}: "
                    f"{detail}{request_suffix}"
                )
                logger.error("Performance authentication failed: %s", reason)
                response.failure(reason)
                return False
            try:
                token = extract_access_token(response.json())
            except (ValueError, TypeError):
                token = None
            if not token:
                detail = self._safe_response_summary(response)
                reason = (
                    "Login returned HTTP 200 but no non-empty data.access_token "
                    f"was found ({detail}){request_suffix}"
                )
                logger.error("Performance authentication failed: %s", reason)
                response.failure(reason)
                return False
            self.token = token
            response.success()
            return True

    def _request(
        self,
        method: str,
        path: str,
        *,
        name: str,
        expected: tuple[int, ...] = (200,),
        **kwargs: Any,
    ):
        if self._auth_failed:
            return None
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.update(self.auth_headers)
        with self.client.request(
            method,
            path,
            name=name,
            headers=headers,
            catch_response=True,
            **kwargs,
        ) as response:
            if response.status_code not in expected:
                response.failure(f"Unexpected HTTP {response.status_code}")
            else:
                response.success()
        return response

    def _choose(self, values: list[str]) -> str | None:
        return random.choice(values) if values else None

    @task(5)
    def liveness(self) -> None:
        self._request("GET", "/health", name="GET /health")

    @task(5)
    def readiness_database_check(self) -> None:
        self._request("GET", "/ready", name="GET /ready")

    @task(2 if os.getenv("PERF_EMAIL") and os.getenv("PERF_PASSWORD") else 0)
    def reauthenticate(self) -> None:
        # Measures login latency under concurrent load, not just one-time startup.
        if self.email and self.password:
            self._authenticate()

    @task(5)
    def customer_search_and_large_page(self) -> None:
        self._request(
            "GET",
            "/api/v1/customers?page=1&page_size=100&sort_by=created_at&sort_order=desc",
            name="GET /api/v1/customers (page_size=100)",
        )

    @task(3)
    def compliance_case_report(self) -> None:
        self._request(
            "GET",
            "/api/v1/reports/compliance-cases",
            name="GET /api/v1/reports/compliance-cases",
        )

    @task(2)
    def aml_alert_report(self) -> None:
        self._request(
            "GET",
            "/api/v1/reports/aml-alerts",
            name="GET /api/v1/reports/aml-alerts",
        )

    @task(2)
    def customer_risk_report(self) -> None:
        self._request(
            "GET",
            "/api/v1/reports/customer-risk",
            name="GET /api/v1/reports/customer-risk",
        )

    @task(2)
    def report_export_history(self) -> None:
        self._request(
            "GET",
            "/api/v1/reports/exports?page=1&page_size=100",
            name="GET /api/v1/reports/exports",
        )

    @task(1)
    def ai_interaction_history(self) -> None:
        self._request(
            "GET",
            "/api/v1/ai-assistant/interactions",
            name="GET /api/v1/ai-assistant/interactions",
        )

    @task(1)
    def transaction_risk_history(self) -> None:
        self._request(
            "GET",
            "/api/v1/transaction-risk-analysis?limit=50",
            name="GET /api/v1/transaction-risk-analysis",
        )

    @task(2 if os.getenv("PERF_CUSTOMER_ID") or os.getenv("PERF_CUSTOMER_IDS") else 0)
    def verification_case_list(self) -> None:
        customer_id = self._choose(self.customer_ids)
        if not customer_id:
            return
        self._request(
            "GET",
            f"/api/v1/customers/{customer_id}/verification-cases",
            name="GET /api/v1/customers/{customer_id}/verification-cases",
        )

    @task(1 if os.getenv("PERF_CUSTOMER_ID") or os.getenv("PERF_CUSTOMER_IDS") else 0)
    def onboarding_read(self) -> None:
        customer_id = self._choose(self.customer_ids)
        if not customer_id:
            return
        self._request(
            "GET",
            f"/api/v1/customers/{customer_id}/onboarding",
            name="GET /api/v1/customers/{customer_id}/onboarding",
        )

    @task(
        1
        if os.getenv("PERF_CUSTOMER_ID") and os.getenv("PERF_VERIFICATION_CASE_ID")
        else 0
    )
    def verification_document_list(self) -> None:
        # Use a known matching customer/case pair; randomly pairing unrelated IDs
        # would turn a valid performance request into an artificial 404.
        customer_id = self.fixture_customer_id
        case_id = self.fixture_verification_case_id
        if not customer_id or not case_id:
            return
        self._request(
            "GET",
            f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/documents",
            name=(
                "GET /api/v1/customers/{customer_id}/verification-cases/"
                "{case_id}/documents"
            ),
        )

    @task(1 if os.getenv("PERF_DOCUMENT_ID") or os.getenv("PERF_DOCUMENT_IDS") else 0)
    def extraction_result_read(self) -> None:
        document_id = self._choose(self.document_ids)
        if not document_id:
            return
        self._request(
            "GET",
            f"/api/v1/documents/{document_id}/extraction",
            name="GET /api/v1/documents/{document_id}/extraction",
        )

    @task(
        1
        if parse_bool(os.getenv("PERF_ENABLE_CUSTOMER_CREATION"))
        and os.getenv("PERF_TEST_PHONE_NUMBERS")
        else 0
    )
    def create_customer_fixture(self) -> None:
        # Creates durable rows; explicitly enable with phone numbers accepted by
        # FinPilot's phone validator. Emails are unique per request; phone numbers
        # are selected from a configured test-only pool rather than fabricated.
        if not self.allow_customer_creation or not self.customer_test_phone_numbers:
            return
        suffix = uuid4().hex[:12]
        payload = {
            "first_name": "Performance",
            "last_name": f"Test{suffix[:6]}",
            "email": f"perf-{suffix}@example.test",
            "phone_number": random.choice(self.customer_test_phone_numbers),
            "status": "NEW",
        }
        self._request(
            "POST",
            "/api/v1/customers",
            name="POST /api/v1/customers (synthetic fixture)",
            expected=(201,),
            json=payload,
        )

    @task(1 if parse_bool(os.getenv("PERF_ENABLE_WORKFLOW_WRITES")) else 0)
    def start_customer_onboarding(self) -> None:
        if not self.allow_workflow_writes:
            return
        customer_id = self._choose(self.customer_ids)
        if not customer_id:
            return
        self._request(
            "POST",
            f"/api/v1/customers/{customer_id}/onboarding",
            name="POST /api/v1/customers/{customer_id}/onboarding",
            expected=(200, 201, 202),
        )

    @task(1 if parse_bool(os.getenv("PERF_ENABLE_VERIFICATION_WRITES")) else 0)
    def create_verification_request(self) -> None:
        if not self.allow_verification_writes:
            return
        customer_id = self._choose(self.customer_ids)
        if not customer_id:
            return
        self._request(
            "POST",
            f"/api/v1/customers/{customer_id}/verification-cases",
            name="POST /api/v1/customers/{customer_id}/verification-cases",
            expected=(201,),
            json={"verification_type": "IDENTITY"},
        )

    @task(
        1
        if parse_bool(os.getenv("PERF_ENABLE_DOCUMENT_UPLOADS"))
        and os.getenv("PERF_CUSTOMER_ID")
        and os.getenv("PERF_VERIFICATION_CASE_ID")
        and os.getenv("PERF_DOCUMENT_TYPE_ID")
        else 0
    )
    def upload_verification_document(self) -> None:
        if not self.allow_document_uploads:
            return
        # These IDs must describe the same customer/case in the test tenant.
        customer_id = self.fixture_customer_id
        case_id = self.fixture_verification_case_id
        if not customer_id or not case_id or not self.document_type_id:
            return
        self._request(
            "POST",
            f"/api/v1/customers/{customer_id}/verification-cases/{case_id}/documents",
            name=(
                "POST /api/v1/customers/{customer_id}/verification-cases/"
                "{case_id}/documents"
            ),
            expected=(201,),
            data={"document_type_id": self.document_type_id},
            files={
                "file": (
                    "finpilot-performance-fixture.pdf",
                    _SAMPLE_PDF,
                    "application/pdf",
                )
            },
        )

    @task(1 if parse_bool(os.getenv("PERF_ENABLE_REPORT_WRITES")) else 0)
    def create_report_export(self) -> None:
        if not self.allow_report_writes:
            return
        self._request(
            "POST",
            "/api/v1/reports/exports",
            name="POST /api/v1/reports/exports (async CSV)",
            expected=(200, 201, 202),
            json={
                "report_type": "OPERATIONAL_PERFORMANCE",
                "format": "CSV",
                "filters": {},
                "prefer_async": True,
            },
        )

    @task(1 if parse_bool(os.getenv("PERF_ENABLE_AI")) else 0)
    def ask_ai_assistant(self) -> None:
        if not self.allow_ai:
            return
        customer_id = self._choose(self.customer_ids)
        payload: dict[str, Any] = {
            "ai_function": "COMPLIANCE_REVIEW",
            "question": (
                "For performance testing only, summarize the typical compliance "
                "checks for a synthetic test request. Do not invent customer facts."
            ),
            "retrieval_limit": 5,
        }
        if customer_id:
            payload["customer_id"] = customer_id
        self._request(
            "POST",
            "/api/v1/ai-assistant/ask",
            name="POST /api/v1/ai-assistant/ask (AI workload)",
            expected=(201,),
            json=payload,
        )

    @task(
        1
        if parse_bool(os.getenv("PERF_ENABLE_AI"))
        and (os.getenv("PERF_DOCUMENT_ID") or os.getenv("PERF_DOCUMENT_IDS"))
        else 0
    )
    def analyze_document(self) -> None:
        if not self.allow_ai:
            return
        document_id = self._choose(self.document_ids)
        if not document_id:
            return
        self._request(
            "POST",
            f"/api/v1/document-fraud/documents/{document_id}/analyze",
            name="POST /api/v1/document-fraud/documents/{document_id}/analyze",
            expected=(201,),
            json={"use_ai": True},
        )

    @task(
        1
        if parse_bool(os.getenv("PERF_ENABLE_AI"))
        and (os.getenv("PERF_CUSTOMER_ID") or os.getenv("PERF_CUSTOMER_IDS"))
        else 0
    )
    def analyze_transaction_risk(self) -> None:
        if not self.allow_ai:
            return
        customer_id = self._choose(self.customer_ids)
        if not customer_id:
            return
        self._request(
            "POST",
            "/api/v1/transaction-risk-analysis/analyze",
            name="POST /api/v1/transaction-risk-analysis/analyze (AI workload)",
            expected=(201,),
            json=build_risk_analysis_payload(customer_id),
        )
