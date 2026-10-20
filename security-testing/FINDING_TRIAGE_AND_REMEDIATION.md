# Finding Triage and Remediation Workflow

## Status definitions

- **New:** finding recorded; not yet validated.
- **Triaged:** reproducibility, affected assets, impact, and severity reviewed.
- **In Progress:** remediation owner and target date assigned; fix underway.
- **Fix Ready:** fix or mitigation is available for verification.
- **Retest:** tester is repeating the original steps and regression checks.
- **Closed:** retest passed and evidence is linked, or the finding is demonstrated not to be valid with reviewer approval.
- **Accepted Risk:** a named risk owner approved a time-bounded exception with rationale and compensating controls. This is not the same as fixed.
- **Reopened:** retest failed or the issue recurred.

## Triage requirements

For each report, capture:

1. A unique identifier such as `SEC-0001`; title; discovery date; reporter; affected endpoint/component, version, and environment.
2. Severity (Critical/High/Medium/Low/Informational) with rationale. Use the organization's approved CVSS version and scoring policy if CVSS is required; do not infer a precise score from severity alone.
3. Preconditions and impact: confidentiality, integrity, availability, tenant/customer impact, regulatory or fraud exposure, and realistic exploitability.
4. Sanitized reproduction steps and request/response/log evidence sufficient to reproduce without including secrets or customer data.
5. Owner, fix recommendation, target date, fix/PR/commit reference, and retest owner.

## Suggested priority targets (confirm with bank/security policy)

These are starter targets, not regulatory requirements. Agree them before the assessment and replace them with the bank's policy where one exists.

| Severity | Suggested handling | Suggested remediation target |
|---|---|---|
| Critical | Immediate security escalation; assess containment and exposure | Mitigate immediately; target fix within 24 hours where feasible |
| High | Escalate to service/security owner promptly | 7 calendar days |
| Medium | Assign an owner and track in the normal security backlog | 30 calendar days |
| Low | Remediate or document why compensating controls are sufficient | 90 calendar days |
| Informational | Record and decide whether action or documentation is warranted | By next planned review |

A bank-specific incident response policy, legal requirement, or contract overrides these starter targets. Do not delay containment of an actively exploited issue while waiting for a target date.

## Retest and closure

1. The owner links the code/config change and any added regression test.
2. The tester reruns the original reproduction steps in an equivalent authorized environment.
3. Retest records **Pass**, **Fail**, or **Blocked**, with evidence and test build/version.
4. Pass: reviewer confirms risk is addressed, records residual risk and closes the finding.
5. Fail: set status to **Reopened**, attach current evidence, and return to the owner.
6. Blocked: keep the finding open; document dependency and next action.
7. Accepted risk requires named approver, rationale, compensating controls, expiry/review date, and evidence of approval. It must not be represented as closed/fixed.

## Report handling

Store reports in access-controlled locations, sanitize secrets and personally identifiable information, and share only with approved recipients. Do not put bearer tokens, passwords, MFA seeds, customer records, or private keys into tickets or the CSV register. Use a secure evidence reference instead.
