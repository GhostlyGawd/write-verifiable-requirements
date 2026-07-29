---
name: write-verifiable-requirements
description: Write, rewrite, review, validate, and trace clear, atomic, testable requirements and acceptance criteria. Use for requirements engineering, requirements specifications, stakeholder expectations, NASA Systems Engineering Handbook requirements-lifecycle work, NASA-style shall requirements, NPR 7123.1 evidence preparation, verification or validation matrices, source traceability, ambiguity or conflict checks, and RFC 2119/RFC 8174 BCP 14 normative language. Do not use only because a user asks for concise or clear prose.
---

# Write Verifiable Requirements

Preserve source intent. Expose missing decisions. Do not infer product, safety,
legal, technical, tailoring, or approval decisions.

Set `<SKILL_ROOT>` to the absolute directory that contains this `SKILL.md`.
Resolve all skill files and commands from `<SKILL_ROOT>`, not from the user's
current working directory.

## Required workflow

1. Select `write`, `rewrite`, `review`, or `trace`.
2. Select the language profile separately from the lifecycle profile.
3. Run `python <SKILL_ROOT>/scripts/manage_references.py status`. Load
   [reference-manifest.json](references/reference-manifest.json),
   [requirements-rules.yaml](references/requirements-rules.yaml), and
   [requirements-schema.md](references/requirements-schema.md). Load
   [nasa-reference-coverage.yaml](references/nasa-reference-coverage.yaml) and
   the NASA references only when the selected lifecycle profile requires them.
4. Confirm source authorities and precedence, objective, boundary, readers,
   product layer, lifecycle phase, controlled terms, protected values,
   constraints, and approval authority.
5. For a NASA lifecycle profile, require a passing local reference status and
   use the bundled
   [handbook](references/nasa-systems-engineering-handbook-rev2.pdf). For an NPR
   assessment, also use the bundled [NPR](references/npr-7123.1d-change-2.pdf).
   Run `python <SKILL_ROOT>/scripts/manage_references.py --json check-current`
   before a current-NPR claim. This explicit command accesses NODIS. Copy its
   unchanged `authority` object to `npr_process_evidence.current_authority_record`.
6. Elicit stakeholder expectations before technical requirements. Separate
   needs, goals, objectives, ConOps, MOEs, constraints, and assumptions from
   binding requirements.
7. Separate product requirements from rationale, design, plans, personnel
   tasks, examples, verification procedures, and validation activities.
8. Record a source-transformation mapping before drafting. Show the exact
   source clause, the proposed requirement interpretation, all added or removed
   conditions, and the authority for each transformation.
9. Give each requirement one stable identifier, subject, obligation, source,
   owner, rationale, parent trace, allocation, and objective verification plan.
10. Record ambiguity, conflicts, missing decisions, interfaces, derived
   requirements, completeness assessments, baselines, and changes. Do not hide
   them in rewritten text.
11. Keep requirement verification separate from product validation.
12. Run `python <SKILL_ROOT>/scripts/check_requirements.py INPUT --format both --output-dir OUTPUT_DIR`.
13. Correct deterministic failures and repeat the check.
14. Obtain genuine human reviews for every required dimension against the
   reported content digest.
15. Record genuine baseline approval from the declared authority, rerun the
   checker, and release clean text only when it reports
   `BASELINED — AUTHORIZED APPROVAL RECORDED`.

## Source hierarchy

Use project-defined precedence when authorized. Otherwise use:

1. Law, regulation, and safety authority
2. Approved source data and binding contracts
3. Approved architecture and interfaces
4. Approved stakeholder expectations, ConOps, and project terminology
5. Applicable NASA directive and approved tailoring
6. Selected language profile
7. General writing guidance

Stop when controlling sources conflict. Quote the conflict, identify its
decision authority, and keep the affected item unresolved.

Do not silently combine source clauses. Keep materially different
interpretations unresolved. If a lower-precedence source prevents a
higher-precedence requirement from being satisfied, record a source conflict;
do not reduce it to a feasibility note. Do not add an unsourced grace period,
population, exception, threshold, condition, or assumption to a requirement or
verification method. Describe an absent authority as “not currently
authorized; none was added.” Do not convert absence of current authority into a
permanent prohibition such as “not permitted.”

## Profile and authority rules

- `shall` controls obligation wording only.
- `bcp14` controls uppercase RFC requirement levels only.
- `general` applies core artifact-quality gates.
- `nasa-se-handbook-rev2` applies all requirements-lifecycle guidance mapped in
  the coverage file. The handbook is guidance, not a NASA compliance standard.
- `nasa-npr-7123.1d` adds current-directive, applicability, complete compliance
  matrix, SEMP, tailoring or customization, and ETA evidence gates.

Never state that an artifact, skill, or automated report is NASA-approved,
NASA-certified, or organizationally compliant. The checker reports artifact
readiness only.

## Output modes

- `write`: Structured requirements and unresolved decisions.
- `rewrite`: Revised requirements, source-change table, and unresolved items.
- `review`: Findings and proposed corrections without silent edits.
- `trace`: Source, hierarchy, verification, and validation matrices.
- `clean`: Requirement text only, after all gates pass.

Use only these statuses:

- `DRAFT — SOURCE OR DECISIONS INCOMPLETE`
- `NOT READY — REQUIREMENT QUALITY CHECK FAILED`
- `READY FOR BASELINE REVIEW`
- `BASELINED — AUTHORIZED APPROVAL RECORDED`

## Release and failure behavior

Release requires complete context, definitive sources, consistent profiles,
unique IDs, bidirectional traceability, objective verification, separate
validation planning, applicable completeness evidence, no open decisions,
current digest-matched human reviews, and authorized baseline approval. NASA
profiles also require their lifecycle and authority records. One open gate
blocks clean output.

When a source, term, value, meaning, interface, constraint, method, applicability,
or approval is uncertain:

1. Preserve the authoritative statement.
2. Quote the uncertainty and possible interpretations.
3. Name the decision and authority that are necessary.
4. Record the item as open.
5. Keep the output in draft or not-ready status.

Scripts verify structure and selected patterns only. They do not prove semantic
correctness, completeness, feasibility, safety, technical validation, or NASA
procedural compliance.

Read the report fields `state_code`, `operation_succeeded`, and
`release_permitted`. Do not infer release permission from the process exit
code.

## Cross-skill routing

- Use `analyze-competing-hypotheses` for competing factual or causal
  explanations. Treat its judgments as assumptions until an authority accepts
  them as requirement sources.
- Resolve requirement intent before an ASD-STE100 rewrite. Protect normative
  keywords, values, units, conditions, permissions, and prohibitions.
- After an ASD-STE100 wording change, rerun the requirement checks and bind the
  result to the new content digest.

## Reference operations

- Normal writing and review use verified local files. Do not access the network
  during ordinary skill execution.
- If `status` fails, the `general` profile can continue without a NASA claim.
  Block the affected NASA profile.
- Run `python <SKILL_ROOT>/scripts/manage_references.py repair` only for an
  explicit repair.
  It downloads only approved bytes from manifest-listed HTTPS hosts, verifies
  size, PDF signature, and SHA-256, and installs atomically.
- Never change a manifest digest automatically. Stage and review new NASA bytes,
  update the rule mapping, and rerun all acceptance tests before approval.
- A matching PDF digest proves document identity. It does not prove that an NPR
  is current, applicable, tailored, or satisfied.
- Run `python <SKILL_ROOT>/scripts/check_requirements.py --emit-template shall`
  (or `bcp14`) to create a structured starting artifact. A template is not
  approval evidence.
- Reports in an output directory use digest-qualified names. The checker writes
  them atomically and does not replace an existing artifact unless the user
  explicitly supplies `--overwrite`.
