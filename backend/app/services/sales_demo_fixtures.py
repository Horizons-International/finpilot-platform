"""Deterministic fictional fixtures for the isolated sales demo."""

from typing import Any

from app.schemas.sales_demo import SalesDemoRecordType

SCENARIO_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "key": "customer-onboarding",
        "name": "Individual and business onboarding",
        "description": (
            "Compare the onboarding paths and risk context for a retail customer "
            "and a business customer."
        ),
        "focus_areas": [
            "Customer profiles",
            "Business KYB context",
            "Onboarding status",
        ],
        "steps": [
            "Open the verified individual profile.",
            "Compare the pending customer.",
            "Open the business profile and review its synthetic registration context.",
        ],
    },
    {
        "key": "verification-outcomes",
        "name": "Verification outcomes",
        "description": (
            "Demonstrate approved, rejected and manual-review results using "
            "deterministic mock responses."
        ),
        "focus_areas": [
            "Identity verification",
            "Review queue",
            "Decision explainability",
        ],
        "steps": [
            "Open verification examples.",
            "Compare the approved and rejected outcomes.",
            "Show how a manual-review outcome is routed.",
        ],
    },
    {
        "key": "compliance-risk-case",
        "name": "Elevated-risk compliance case",
        "description": (
            "Review a synthetic high-risk business case and its recommended "
            "follow-up actions."
        ),
        "focus_areas": ["Risk cases", "Case prioritization", "Evidence review"],
        "steps": [
            "Open the open high-risk case.",
            "Review the recorded indicators.",
            "Discuss the suggested evidence and review steps.",
        ],
    },
    {
        "key": "aml-alert-review",
        "name": "AML alert review",
        "description": (
            "Explore a fictional cross-border velocity alert without connecting "
            "to transaction networks."
        ),
        "focus_areas": ["AML alerts", "Transaction context", "Investigation workflow"],
        "steps": [
            "Open the synthetic alert.",
            "Review the alert signals.",
            "Walk through the proposed investigation checklist.",
        ],
    },
    {
        "key": "ai-risk-recommendation",
        "name": "AI-assisted risk recommendation",
        "description": (
            "Show a pre-generated, clearly labeled synthetic recommendation and "
            "its evidence summary."
        ),
        "focus_areas": ["Risk explanation", "Confidence", "Human review"],
        "steps": [
            "Open the recommendation.",
            "Inspect its factors and confidence.",
            "Explain that the item is illustrative and not a live model call.",
        ],
    },
    {
        "key": "investigation-summary",
        "name": "Investigation summary",
        "description": (
            "Demonstrate a fictional case summary for a compliance investigator."
        ),
        "focus_areas": ["Investigation notes", "Narrative summary", "Next actions"],
        "steps": [
            "Open the summary.",
            "Compare observations and unresolved questions.",
            "Review proposed next actions.",
        ],
    },
    {
        "key": "usage-dashboard",
        "name": "Usage and operational dashboard",
        "description": (
            "Review a sample usage snapshot with customer, verification, API and AI "
            "counts."
        ),
        "focus_areas": ["Analytics", "Usage trends", "Operational reporting"],
        "steps": [
            "Open the demo dashboard.",
            "Review synthetic monthly volumes.",
            "Discuss which metrics would be tailored for a live customer.",
        ],
    },
    {
        "key": "compliance-report",
        "name": "Monthly compliance report",
        "description": (
            "Inspect a static report sample built from seeded synthetic values."
        ),
        "focus_areas": ["Compliance reporting", "Period totals", "Audit readiness"],
        "steps": [
            "Open the report record.",
            "Review the sample period and totals.",
            "Show the report sections and suggested follow-up.",
        ],
    },
    {
        "key": "enhanced-due-diligence-workflow",
        "name": "Enhanced due diligence workflow",
        "description": (
            "Walk through a pre-defined workflow scenario; it does not execute "
            "real tasks or external actions."
        ),
        "focus_areas": ["Workflow stages", "Task handoffs", "Reviewer sign-off"],
        "steps": [
            "Inspect the configured stages.",
            "Review the synthetic task handoffs.",
            "Explain where a production tenant would require an authorized sign-off.",
        ],
    },
)


CUSTOMER_SEEDS: tuple[dict[str, Any], ...] = (
    {
        "external_reference": "DEMO-IND-001",
        "first_name": "Alex",
        "last_name": "Morgan",
        "email": "alex.morgan@example.com",
        "phone_number": "+15550101001",
        "status": "VERIFIED",
        "attributes": {
            "customer_type": "INDIVIDUAL",
            "segment": "RETAIL",
            "source": "SALES_DEMO_SYNTHETIC",
            "risk_band": "LOW",
            "country_of_residence": "GB",
        },
    },
    {
        "external_reference": "DEMO-IND-002",
        "first_name": "Jordan",
        "last_name": "Lee",
        "email": "jordan.lee@example.com",
        "phone_number": "+15550101002",
        "status": "PENDING_VERIFICATION",
        "attributes": {
            "customer_type": "INDIVIDUAL",
            "segment": "PREMIUM_RETAIL",
            "source": "SALES_DEMO_SYNTHETIC",
            "risk_band": "MEDIUM",
            "country_of_residence": "GB",
        },
    },
    {
        "external_reference": "DEMO-IND-003",
        "first_name": "Taylor",
        "last_name": "Reed",
        "email": "taylor.reed@example.com",
        "phone_number": "+15550101003",
        "status": "REJECTED",
        "attributes": {
            "customer_type": "INDIVIDUAL",
            "segment": "RETAIL",
            "source": "SALES_DEMO_SYNTHETIC",
            "risk_band": "HIGH",
            "country_of_residence": "GB",
        },
    },
    {
        "external_reference": "DEMO-BIZ-001",
        "first_name": "Casey",
        "last_name": "Finance Team",
        "email": "operations@meridian-commerce.example.com",
        "phone_number": "+15550101004",
        "status": "VERIFIED",
        "attributes": {
            "customer_type": "BUSINESS",
            "business_name": "Meridian Commerce Ltd (Synthetic Demo Entity)",
            "business_registration_reference": "DEMO-REG-48120",
            "industry": "Wholesale and retail",
            "source": "SALES_DEMO_SYNTHETIC",
            "risk_band": "HIGH",
            "country_of_registration": "GB",
            "is_synthetic": True,
        },
    },
)


RECORD_SEEDS: tuple[dict[str, Any], ...] = (
    {
        "record_type": SalesDemoRecordType.COMPLIANCE_CASE.value,
        "scenario_key": "compliance-business-high-risk",
        "title": "Business profile — enhanced review required",
        "summary": "Synthetic elevated-risk case for a fictional business profile.",
        "customer_ref": "DEMO-BIZ-001",
        "data": {
            "case_reference": "DEMO-CASE-1001",
            "status": "OPEN",
            "priority": "HIGH",
            "case_type": "CUSTOMER_REVIEW",
            "risk_score": 82,
            "risk_level": "HIGH",
            "risk_indicators": [
                "Complex ownership declared",
                "Cross-border activity expected",
                "Source-of-funds evidence pending",
            ],
            "recommended_actions": [
                "Request ownership documentation",
                "Verify source of funds",
                "Record reviewer decision",
            ],
            "is_synthetic": True,
        },
    },
    {
        "record_type": SalesDemoRecordType.COMPLIANCE_CASE.value,
        "scenario_key": "compliance-retail-medium-risk",
        "title": "Retail customer — periodic review",
        "summary": (
            "Synthetic medium-risk review showing a standard periodic-check workflow."
        ),
        "customer_ref": "DEMO-IND-002",
        "data": {
            "case_reference": "DEMO-CASE-1002",
            "status": "IN_REVIEW",
            "priority": "MEDIUM",
            "case_type": "PERIODIC_REVIEW",
            "risk_score": 54,
            "risk_level": "MEDIUM",
            "risk_indicators": [
                "Profile update due",
                "Recent activity requires confirmation",
            ],
            "recommended_actions": [
                "Confirm current occupation",
                "Review activity profile",
                "Close with audit note",
            ],
            "is_synthetic": True,
        },
    },
    {
        "record_type": SalesDemoRecordType.AML_ALERT.value,
        "scenario_key": "aml-cross-border-velocity-alert",
        "title": "Cross-border velocity alert",
        "summary": (
            "Fictional alert produced from static sample facts; no payment network "
            "is queried."
        ),
        "customer_ref": "DEMO-BIZ-001",
        "data": {
            "alert_reference": "DEMO-AML-2044",
            "status": "OPEN",
            "severity": "HIGH",
            "typology": "CROSS_BORDER_VELOCITY",
            "sample_transaction_count_24h": 14,
            "sample_total_amount": 48600.0,
            "currency": "GBP",
            "signals": [
                "Unusual frequency versus declared profile",
                "Multiple destination countries in a short window",
            ],
            "is_synthetic": True,
            "disclaimer": (
                "Every transaction and amount in this scenario is invented for "
                "demonstration."
            ),
        },
    },
    {
        "record_type": SalesDemoRecordType.AI_RISK_RECOMMENDATION.value,
        "scenario_key": "ai-high-risk-recommendation",
        "title": "Risk recommendation — additional evidence",
        "summary": (
            "Pre-generated synthetic recommendation intended to demonstrate "
            "explainability."
        ),
        "customer_ref": "DEMO-BIZ-001",
        "data": {
            "risk_score": 82,
            "risk_level": "HIGH",
            "confidence": 0.91,
            "recommendation": (
                "Request additional evidence and route the case for human review."
            ),
            "reason": (
                "The illustrative profile combines higher-risk declared activity with "
                "missing supporting evidence."
            ),
            "risk_factors": [
                "Source-of-funds evidence pending",
                "Cross-border activity",
                "Ownership verification required",
            ],
            "suggested_action": "Enhanced due diligence review",
            "provider_name": "static_demo_fixture",
            "model_call_made": False,
            "is_synthetic": True,
        },
    },
    {
        "record_type": SalesDemoRecordType.INVESTIGATION_SUMMARY.value,
        "scenario_key": "investigation-summary-aml",
        "title": "Investigation summary — DEMO-AML-2044",
        "summary": (
            "Static fictional summary showing how an investigator may structure "
            "findings."
        ),
        "customer_ref": "DEMO-BIZ-001",
        "data": {
            "observations": [
                "Alert volume is above the fictional expected baseline",
                "Counterparty evidence is incomplete",
            ],
            "confirmed_facts": [
                "The alert was generated from fixed synthetic values",
                "No live transaction query was executed",
            ],
            "unresolved_questions": [
                "Can the customer explain the stated activity?",
                "Are beneficiary details supported by evidence?",
            ],
            "next_actions": [
                "Collect supporting invoices",
                "Confirm counterparties",
                "Document the review decision",
            ],
            "is_synthetic": True,
        },
    },
    {
        "record_type": SalesDemoRecordType.DASHBOARD.value,
        "scenario_key": "usage-dashboard-monthly",
        "title": "Monthly product usage dashboard",
        "summary": (
            "Static sample usage snapshot for a fictional bank; values are not live "
            "telemetry."
        ),
        "data": {
            "period": "2026-09",
            "active_users": 146,
            "api_calls": 500000,
            "verification_checks": 25000,
            "ai_requests": 8000,
            "workflow_executions": 1240,
            "reports_generated": 86,
            "top_features": ["Customer onboarding", "Verification", "AML monitoring"],
            "unused_features": ["Advanced portfolio analytics"],
            "is_synthetic": True,
        },
    },
    {
        "record_type": SalesDemoRecordType.REPORT.value,
        "scenario_key": "monthly-compliance-report",
        "title": "Monthly compliance report — sample",
        "summary": "Pre-generated report metadata for a fictional reporting period.",
        "data": {
            "report_reference": "DEMO-REPORT-2026-09",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
            "customers_reviewed": 1240,
            "verification_checks": 25000,
            "alerts_opened": 74,
            "alerts_resolved": 61,
            "high_risk_cases_escalated": 18,
            "format": "DEMO_JSON",
            "downloadable_production_file": False,
            "is_synthetic": True,
        },
    },
    {
        "record_type": SalesDemoRecordType.WORKFLOW.value,
        "scenario_key": "enhanced-due-diligence-workflow",
        "title": "Enhanced due diligence — workflow example",
        "summary": (
            "A static workflow blueprint; viewing it does not trigger real tasks or "
            "messages."
        ),
        "data": {
            "workflow_reference": "DEMO-WF-EDD-01",
            "status": "EXAMPLE_ONLY",
            "steps": [
                {
                    "order": 1,
                    "name": "Collect ownership documents",
                    "owner": "Relationship Manager",
                },
                {
                    "order": 2,
                    "name": "Review source of funds",
                    "owner": "Compliance Officer",
                },
                {
                    "order": 3,
                    "name": "Complete screening review",
                    "owner": "AML Analyst",
                },
                {
                    "order": 4,
                    "name": "Record senior reviewer decision",
                    "owner": "Compliance Manager",
                },
            ],
            "external_actions_enabled": False,
            "is_synthetic": True,
        },
    },
)
