# Dogfood hardening validation — 2026-07-29

This dated record contains validation evidence for the requirements-skill
hardening branch. Normative behavior remains in the skill, scripts, schema,
tests, and behavior-alignment table.

## Confirmed findings addressed

- Source authorities now require revision and location identity. Each authority
  also requires either a lowercase SHA-256 digest or a reason that source bytes
  are unavailable.
- Current NPR evidence now uses the canonical `check-current` authority record.
  The checker rejects stale, future, incomplete, expired, non-NODIS, or
  wrong-manifest records.
- JSON reports now expose `state_code`, `operation_succeeded`, and
  `release_permitted`. Release permission is not inferred from an exit code.
- Directory reports use a content-digest suffix. Writes are atomic and do not
  replace an existing artifact without explicit `--overwrite`.
- Template emission is available from any working directory through the
  absolute skill-root command in `SKILL.md`.
- `policy.allow_implicit_invocation` is explicitly enabled.

## Local validation

- Automated tests: 77 passed.
- Bundled NASA reference identity and integrity: `PASS`.
- Transactional installer dry run: `PASS`.
- `--emit-template shall`: `PASS`.
- Digest-qualified JSON and Markdown report creation: `PASS`.
- Default collision refusal and explicit overwrite: `PASS`.
- Stale, future, and wrong-manifest NPR authority rejection: `PASS`.
- Missing and invalid source identity binding: `PASS`.

## Documentation alignment

Changed surfaces:

- `README.md`: portable commands, canonical NPR evidence transfer, report
  behavior, and machine-readable release decision.
- `write-verifiable-requirements/SKILL.md`: absolute commands, authority-record
  handling, output naming, and overwrite policy.
- `requirements-schema.md`: source identity fields and current-authority record.
- `docs/alignment.md`: implementation-to-test-to-document mappings.

Reviewed but unaffected:

- `SECURITY.md`: network and download boundaries did not change. The existing
  explicit NODIS access boundary remains accurate.
- `NOTICE.md`: NASA document identity, provenance, and non-endorsement claims
  did not change.
- `CONTRIBUTING.md`: reference-byte acceptance and manifest-update authority did
  not change.
- `docs/agent-flow.svg`: the installation and execution stages did not change.
  The new fields refine artifacts inside the existing check stage.

## Boundaries

The checker validates declared records and selected patterns. It does not prove
source authenticity when source bytes are unavailable. A response digest
records the bytes observed by `check-current`; it is not a NASA signature.
Human reviewers remain responsible for source fidelity, technical meaning,
applicability, feasibility, safety, verification adequacy, and approval.

## Blind retest correction

A fresh agent preserved the contract and security obligations, kept the
architecture limitation unresolved, and did not add latency or staleness
criteria. An independent reviewer found that “no exception is permitted” could
be read as a permanent prohibition even though the sources established only
that no exception was currently authorized.

The skill now requires the bounded statement “not currently authorized; none
was added” and prohibits converting absent authority into a permanent
prohibition. The repository contract test pins this distinction.
