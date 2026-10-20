# Package manifest

This ZIP contains additive security-testing preparation files for FinPilot. It does not overwrite application source files or modify dependency manifests.

- `docker/docker-compose.security-test.yml`: isolated loopback-only test stack.
- `security-testing/tests/`: black-box security smoke tests.
- `security-testing/scripts/`: PowerShell environment/test/scanner commands.
- `security-testing/*.md` and `VULNERABILITY_REGISTER.csv`: plan, checklist, workflow, and tracker.
