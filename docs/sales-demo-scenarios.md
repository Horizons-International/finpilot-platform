# Sales demo scenarios

| Scenario | What to demonstrate | Data source |
|---|---|---|
| Customer onboarding | Individual vs business profiles, risk bands and onboarding states | `sandbox_customers` attributes |
| Verification outcomes | Approved, rejected and manual-review examples | `sandbox_verifications` static results |
| Compliance review | High-risk case, indicators, evidence needed, reviewer action | `sandbox_demo_records` (`COMPLIANCE_CASE`) |
| AML alert | Cross-border velocity signal, amount/time context, investigation checklist | `sandbox_demo_records` (`AML_ALERT`) |
| AI recommendation | Risk score, confidence, risk factors, suggested next step | `sandbox_demo_records` (`AI_RISK_RECOMMENDATION`) |
| Investigation summary | Observations, confirmed sample facts, outstanding questions and actions | `sandbox_demo_records` (`INVESTIGATION_SUMMARY`) |
| Usage dashboard | Example API, verification, AI, workflow and report volumes | `sandbox_demo_records` (`DASHBOARD`) and dashboard API |
| Compliance report | Reporting period, reviewed customers, alerts and escalations | `sandbox_demo_records` (`REPORT`) |
| Due diligence workflow | Illustrative task stages and role handoffs | `sandbox_demo_records` (`WORKFLOW`) |

The dashboard's `usage_sample` is a static presentation dataset. It is not actual billing, production usage, or a query of the product-usage analytics tables.
