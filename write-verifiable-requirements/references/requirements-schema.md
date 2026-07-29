# Structured requirements input

Use UTF-8 YAML or JSON. The checker ignores unrecognized fields as evidence.

## Profiles

Select `language_profile: shall` or `language_profile: bcp14`.

Select one lifecycle profile:

- `general`: Core requirement quality and traceability.
- `nasa-se-handbook-rev2`: Core checks plus all applicable NASA handbook requirements-lifecycle records.
- `nasa-npr-7123.1d`: The handbook records plus NASA authority and process-evidence gates.

The NASA handbook is guidance. A successful artifact check is not NASA
procedural compliance. The NPR profile prepares and gates evidence; it does not
approve tailoring or make an organizational compliance decision.

## Core document fields

- `title`, `objective`, `system_boundary`, `intended_readers`
- `lifecycle_scope`: `{product_layer, lifecycle_phase, included_processes, excluded_processes}`
- `source_authorities`: ordered records with `id`, `title`, `revision`,
  `location`, and `precedence`. Bind each record to source bytes with a
  64-character lowercase SHA-256 `digest`. If source bytes are not available,
  omit `digest` and give a checkable `digest_unavailable_reason`. Do not provide
  both. Placeholder identity values such as `not provided`, `unknown`, and
  `unavailable` do not satisfy `revision` or `location`. A bounded absence
  statement records the gap but is not a source identity value.
- `source_transformations`: records that map an exact source clause to a
  proposed requirement interpretation, list each added or removed condition,
  and identify the authority for the transformation
- `controlled_terms`: `{term, definition, source, approved}` records
- `protected_values`: literal values that must not change
- `approval_authority`: `{approver_id, role, authority_source}` records
- `requirements`, `unresolved`, `reviews`, and `approvals`
- `normative_language_notice`: required only for `bcp14`

## Requirement record

Each requirement contains:

- `id`
- `type`: `functional`, `performance`, `interface`, `constraint`, `safety`,
  `security`, `quality`, or `operational`
- `level`, `owner`, `text`
- `source`: source-authority identifiers
- `source_document`, `source_paragraph`, `source_excerpt`
- `rationale`, `assumptions`
- `parents`: parent requirement identifiers
- `derived`: Boolean
- `derived_basis`: required when `derived` is true
- `allocated_to`: product or function identifiers
- `atomicity_rationale`: required when a conjunction is necessary
- `verification`: the verification-plan fields below

## NASA handbook lifecycle records

The `nasa-se-handbook-rev2` and `nasa-npr-7123.1d` profiles require:

- `stakeholder_context`: stakeholders, decision authority, needs, goals,
  objectives, ConOps references, MOEs, constraints, assumptions, operational
  environments, commitments, and expectation baseline
- `decomposition`: functions, inputs, outputs, sequences, failure modes,
  consequences, allocations, and derived-requirement decisions
- `completeness_assessment`: one record for every category listed in
  `requirements-rules.yaml`; each has `category`, `result`, and `evidence`
- `validation_plan`
- `interfaces`
- `baselines`
- `change_records`
- `data_management`: repository, version convention, decision records, and
  evidence records

An empty record set is permitted only when every inapplicable item has a
checkable `NOT_APPLICABLE` assessment and human review accepts that decision.

## Verification plan

Each requirement has:

- `method`: `inspection`, `analysis`, `demonstration`, or `test`
- `success_criteria`
- `verification_level`
- `verification_lead`
- `facility`
- `phase`
- `acceptance_requirement`: Boolean
- `preflight_acceptance`: Boolean
- `performing_organization`
- `results_state`: `PLANNED`, `PASS`, `FAIL`, or `NOT_RUN`
- `evidence`
- `source_basis`: source identifiers and exact source locations that authorize
  the success criteria, population, threshold, conditions, and exceptions
- `introduced_constraints`: each verification-only constraint and its
  authorizing source; use an empty list when none are introduced
- `discrepancies`: list of discrepancy, nonconformance, waiver, or deviation IDs
- `configuration`: verified product or artifact version

These fields generate the Appendix D-style matrix. Planned evidence is not
completed verification evidence.

## Validation plan

Each record contains:

- `product_id`, `activity`, `objective`, `method`, `facility`, `phase`
- `performing_organization`, `results_state`, `evidence`
- `stakeholder_expectations`, `conops_references`, `moe_references`
- `intended_environment`, `representative_users`

These fields generate the separate Appendix E-style matrix.

## Traceability and change

- Every non-root requirement lists valid `parents`.
- Every derived requirement records `derived_basis`.
- Every parent listed by a requirement exists in the same artifact or in
  `external_parent_requirements`.
- Each interface record identifies `id`, `kind`, `owners`, `controlling_source`,
  `units`, `tolerances`, `compatibility_evidence`, and `change_authority`.
- Each baseline record identifies `id`, `kind`, `version`, `date`, `authority`,
  and `content_digest`.
- Each change record identifies `id`, `status`, `authority`, `reason`, and
  impacts for cost, schedule, architecture, design, interfaces, ConOps,
  parent requirements, child requirements, safety, and risk.

## NPR process-evidence record

The `nasa-npr-7123.1d` profile requires `npr_process_evidence` with:

- `current_authority_record`: the unchanged JSON `authority` object from a
  same-day `manage_references.py --json check-current` result. It contains the
  canonical reference and directive identifiers, result, timezone-aware
  `checked_at`, official authority URL, observed and missing markers,
  expiration result, response SHA-256, and reference-manifest SHA-256.
- `applicability`
- `complete_compliance_matrix`, `compliance_matrix_digest`
- `semp_or_equivalent`, `semp_approval`
- `tailoring_records`, `customization_records`
- `eta_authority`, `eta_decisions`

This record must refer to the complete applicable NPR matrix, not only the
requirements-lifecycle subset in `nasa-reference-coverage.yaml`.

## Unresolved, review, and approval records

Use `{id, statement, decision_needed, owner, due_date, status, resolution}` for
an unresolved record. `OPEN` blocks release.

When an ambiguity or conflict has no authorized decision authority, each
separate `decision_authority` field must state: “The decision authority is not
currently authorized; none was added.” A shortened absence statement is not
equivalent.

Human reviews use:

`{dimension, reviewer_id, role, date, result, evidence, content_digest}`

Core review dimensions are `source_fidelity`, `coverage`, `conflicts`,
`feasibility`, and `verification_adequacy`. NASA lifecycle profiles also
require `validation_adequacy`, `traceability`, `interfaces`, and
`lifecycle_completeness`.

Baseline approvals use:

`{approver_id, role, date, result, evidence, content_digest}`

The checker accepts `APPROVED` only from a declared `baseline_approver`. It
derives status from current evidence. A content change changes the digest and
invalidates earlier reviews and approvals.
