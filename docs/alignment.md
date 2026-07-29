# Behavior and documentation alignment

This table maps the current public behavior contract. Dated validation evidence
records volatile run results.

| Contract item | Normative level | Implementation | Test | Docs/example | Status |
|---|---|---|---|---|---|
| Clean-root publication excludes legacy commits and private evidence | Required | Distinct repository and Git database | Final full-ref audit | README status and publication evidence | Implemented; final public audit pending |
| Agent installs a verified complete skill transactionally | Required | `scripts/install_skill.py` | Fresh install, no-op, lock, corruption, rollback | README Agent installation | Implemented |
| Ordinary execution has no network dependency | Required | Local manifest verification | Offline status and install tests | README Agent workflow; SECURITY | Implemented |
| Repair accepts only approved NASA bytes | Required | `manage_references.py repair` | Cache, truncation, type, redirect, digest tests | README and SECURITY | Implemented |
| NPR document identity and current authority remain separate | Required | Local digest plus `check-current` | Marker pass and fail tests; scheduled live probe | README profiles; NOTICE | Implemented |
| New NASA bytes never become approved automatically | Required | Manifest digest is immutable during repair | Mismatch and corruption tests | CONTRIBUTING reference update procedure | Implemented |
| General requirements work remains available without NASA authority | Required | Independent lifecycle profile selection | Existing general-profile tests | README profile table; SKILL failure behavior | Implemented |
| Human judgment and approval remain mandatory | Required | Checker release gates and digest-bound records | Existing approval and stale-review tests | README limitations; SKILL release behavior | Implemented |
| Public CI uses standard isolated hosted runners with least privilege | Required | `.github/workflows/ci.yml` | Public PR and main runs | SECURITY supply-chain controls | Post-publication evidence pending |
| NASA source and endorsement boundaries are explicit | Required | Manifest and unchanged PDFs | Hash and page/metadata inspection | NOTICE and README limitations | Implemented |
| Repository code license is owner-selected | Required decision | No license file | Repository metadata audit | README status; NOTICE | Intentionally no license |
