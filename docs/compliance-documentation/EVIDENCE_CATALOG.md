# Compliance evidence catalog

Create one evidence record per independently reviewable artifact or control assertion. Keep the evidence itself in controlled file storage or an approved evidence repository; the `source_reference` field should be a safe internal identifier or access-controlled location, not a secret or raw customer data.

| Evidence area | Suggested records | Typical proof |
|---|---|---|
| Security — Access control | `ACCESS_CONTROL` | Role matrix, access-review result, negative authorization test, tenant-isolation test report |
| Security — Encryption | `ENCRYPTION` | Encryption/key-management standard, database TLS configuration review, file storage encryption evidence, key rotation approval (never the key) |
| Security — Monitoring | `MONITORING` | Security event samples with secrets redacted, alert configuration review, monitoring test result |
| Compliance — KYC | `KYC_PROCESS` | Approved KYC procedure, checklist version, synthetic workflow test report |
| Compliance — AML | `AML_MONITORING` | AML rule/change approval, monitoring run evidence, alert-handling sample using synthetic or anonymized data |
| Compliance — Case management | `CASE_MANAGEMENT` | Case lifecycle procedure, approval/review evidence, segregation-of-duties test |
| Operations — Incident management | `INCIDENT_MANAGEMENT` | Incident response plan, tabletop exercise record, post-incident action register |
| Operations — Business continuity | `BUSINESS_CONTINUITY` | BCP, recovery test, RTO/RPO approval and achieved measurements |
| Operations — Change management | `CHANGE_MANAGEMENT` | Change request, reviewer approval, deployment record, rollback result |

For each record, capture the responsible collector, capture time, relevant document version, description, and source reference. Record the test build/environment and date in the referenced artifact. Do not upload active secrets, authentication tokens, MFA seeds, signing keys, database passwords, or unredacted bank customer information.
