from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "write-verifiable-requirements"
    / "scripts"
    / "check_requirements.py"
)
SPEC = importlib.util.spec_from_file_location("check_requirements", SCRIPT)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


def valid_document(profile: str = "shall") -> dict[str, Any]:
    if profile == "shall":
        text = "The controller shall stop the pump within 2 seconds."
        source_excerpt = "The controller must stop the pump within 2 seconds."
    else:
        text = "Each protocol message MUST include an identifier."
        source_excerpt = "Protocol messages must include an identifier."
    document: dict[str, Any] = {
        "title": "Pump control requirements",
        "language_profile": profile,
        "lifecycle_profile": "general",
        "objective": "Define observable pump controller behavior.",
        "system_boundary": "The controller and its pump interface are in scope.",
        "intended_readers": ["implementers", "verification engineers"],
        "lifecycle_scope": {
            "product_layer": "component",
            "lifecycle_phase": "design",
            "included_processes": ["technical_requirements_definition"],
            "excluded_processes": [],
        },
        "source_authorities": [
            {
                "id": "SRC-001",
                "title": "Approved control brief",
                "revision": "1",
                "location": "approved-control-brief:3.1",
                "precedence": 1,
                "digest_unavailable_reason": (
                    "The authority is a controlled record without accessible source bytes."
                ),
            }
        ],
        "controlled_terms": [
            {
                "term": "controller",
                "definition": "The pump control component.",
                "source": "SRC-001",
                "approved": True,
            }
        ],
        "protected_values": ["2 seconds"],
        "approval_authority": [
            {
                "approver_id": "owner-1",
                "role": "baseline_approver",
                "authority_source": "Project charter section 3",
            }
        ],
        "requirements": [
            {
                "id": "REQ-001",
                "type": "performance" if profile == "shall" else "functional",
                "level": "component",
                "owner": "controller-owner",
                "text": text,
                "source": ["SRC-001"],
                "source_excerpt": source_excerpt,
                "rationale": "Provide deterministic controller behavior.",
                "assumptions": [],
                "parents": [],
                "derived": False,
                "allocated_to": ["controller"],
                "verification": {
                    "method": "test",
                    "success_criteria": "The observed result matches the requirement.",
                    "evidence": ["planned-test:TEST-001"],
                },
            }
        ],
        "unresolved": [],
        "reviews": [],
        "approvals": [],
    }
    if profile == "bcp14":
        document["normative_language_notice"] = (
            "The uppercase normative keywords use BCP 14 as defined by "
            "RFC 2119 and clarified by RFC 8174."
        )
    return document


def nasa_document(npr: bool = False) -> dict[str, Any]:
    document = valid_document()
    document["lifecycle_profile"] = (
        "nasa-npr-7123.1d" if npr else "nasa-se-handbook-rev2"
    )
    requirement = document["requirements"][0]
    requirement.update(
        {
            "source_document": "Approved control brief",
            "source_paragraph": "3.1",
        }
    )
    requirement["verification"].update(
        {
            "verification_level": "component",
            "verification_lead": "verification-lead",
            "facility": "Control laboratory",
            "phase": "qualification",
            "acceptance_requirement": True,
            "preflight_acceptance": False,
            "performing_organization": "Verification team",
            "results_state": "PLANNED",
            "discrepancies": [],
            "configuration": "controller-v1",
        }
    )
    document.update(
        {
            "external_parent_requirements": [],
            "stakeholder_context": {
                "stakeholders": ["operator"],
                "decision_authority": "requirements-board",
                "needs": ["Stop the pump predictably."],
                "goals": ["Protect the pump."],
                "objectives": ["Stop within 2 seconds."],
                "conops_references": ["CONOPS-001"],
                "measures_of_effectiveness": ["MOE-STOP-001"],
                "constraints": ["Use the installed pump interface."],
                "assumptions": ["Power is available."],
                "operational_environments": ["laboratory"],
                "commitments": ["approved-control-brief"],
                "expectation_baseline": "STK-BL-001",
            },
            "decomposition": {
                "functions": ["stop pump"],
                "inputs": ["stop request"],
                "outputs": ["pump stopped"],
                "sequences": ["request then stop"],
                "failure_modes": ["stop failure"],
                "consequences": ["pump continues"],
                "allocations": ["controller"],
                "derived_requirement_decisions": ["none identified"],
            },
            "completeness_assessment": [
                {
                    "category": category,
                    "result": "PASS",
                    "evidence": f"Reviewed {category} against SRC-001.",
                }
                for category in sorted(CHECKER.COMPLETENESS_CATEGORIES)
            ],
            "validation_plan": [
                {
                    "product_id": "controller",
                    "activity": "Operational stop scenario",
                    "objective": "Confirm that the product satisfies operator expectations.",
                    "method": "demonstration",
                    "facility": "Control laboratory",
                    "phase": "validation",
                    "performing_organization": "Validation team",
                    "results_state": "PLANNED",
                    "evidence": "planned-validation:VAL-001",
                    "stakeholder_expectations": ["STK-BL-001"],
                    "conops_references": ["CONOPS-001"],
                    "moe_references": ["MOE-STOP-001"],
                    "intended_environment": "laboratory",
                    "representative_users": ["operator-representative"],
                }
            ],
            "interfaces": [
                {
                    "id": "IF-001",
                    "kind": "internal",
                    "owners": ["controller-owner", "pump-owner"],
                    "controlling_source": "ICD-001",
                    "units": "seconds",
                    "tolerances": "2 seconds maximum",
                    "compatibility_evidence": "planned-test:IF-001",
                    "change_authority": "interface-board",
                }
            ],
            "baselines": [
                {
                    "id": "STK-BL-001",
                    "kind": "stakeholder_expectations",
                    "version": "1",
                    "date": "2026-07-28",
                    "authority": "requirements-board",
                    "content_digest": "sha256:stakeholder-baseline",
                },
                {
                    "id": "REQ-BL-001",
                    "kind": "technical_requirements",
                    "version": "1",
                    "date": "2026-07-28",
                    "authority": "requirements-board",
                    "content_digest": "sha256:requirements-baseline",
                },
            ],
            "change_records": [],
            "data_management": {
                "repository": "requirements-repository",
                "version_convention": "semantic-baseline-ids",
                "decision_records": "decisions/",
                "evidence_records": "evidence/",
            },
        }
    )
    if npr:
        manifest = (
            ROOT
            / "write-verifiable-requirements"
            / "references"
            / "reference-manifest.json"
        )
        document["npr_process_evidence"] = {
            "current_authority_record": {
                "reference_id": "NPR-7123.1D-C2",
                "directive_identifier": "NPR 7123.1D Updated with Change 2",
                "result": "PASS",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "authority_url": (
                    "https://nodis3.gsfc.nasa.gov/displayDir.cfm?"
                    "Internal_ID=N_PR_7123_001D_"
                ),
                "observed_markers": sorted(CHECKER.NPR_AUTHORITY_MARKERS),
                "missing_markers": [],
                "expired": False,
                "response_sha256": "1" * 64,
                "manifest_sha256": hashlib.sha256(
                    manifest.read_bytes()
                ).hexdigest(),
            },
            "applicability": "Applicable NASA project per ETA decision ETA-001.",
            "complete_compliance_matrix": "NPR-CM-001",
            "compliance_matrix_digest": "sha256:complete-matrix",
            "semp_or_equivalent": "SEMP-001",
            "semp_approval": "SEMP-APPROVAL-001",
            "tailoring_records": [],
            "customization_records": [],
            "eta_authority": "ETA-001",
            "eta_decisions": ["ETA-DECISION-001"],
        }
    return document


def add_passing_reviews(document: dict[str, Any]) -> None:
    digest = CHECKER.content_digest(document)
    document["reviews"] = [
        {
            "dimension": dimension,
            "reviewer_id": f"reviewer-{index}",
            "role": "requirements_reviewer",
            "date": "2026-07-28",
            "result": "PASS",
            "evidence": f"Reviewed {dimension} against SRC-001.",
            "content_digest": digest,
        }
        for index, dimension in enumerate(
            sorted(
                CHECKER.REVIEW_DIMENSIONS
                if document.get("lifecycle_profile")
                in CHECKER.NASA_LIFECYCLE_PROFILES
                else CHECKER.CORE_REVIEW_DIMENSIONS
            ),
            start=1,
        )
    ]


def add_approval(document: dict[str, Any]) -> None:
    document["approvals"] = [
        {
            "approver_id": "owner-1",
            "role": "baseline_approver",
            "date": "2026-07-28",
            "result": "APPROVED",
            "evidence": "Approved requirements baseline BR-001.",
            "content_digest": CHECKER.content_digest(document),
        }
    ]


class RequirementsCheckerTests(unittest.TestCase):
    def assert_has(
        self, report: dict[str, Any], check: str, result: str
    ) -> None:
        self.assertTrue(
            any(
                issue["check"] == check and issue["result"] == result
                for issue in report["issues"]
            ),
            f"missing {check}={result}",
        )

    def test_complete_content_without_reviews_is_draft(self) -> None:
        report = CHECKER.evaluate(valid_document())
        self.assertEqual(report["status"], CHECKER.STATUS_DRAFT)
        self.assertEqual(report["state_code"], "DRAFT")
        self.assertTrue(report["operation_succeeded"])
        self.assertFalse(report["release_permitted"])
        self.assert_has(report, "REVIEW-001", "REVIEW_REQUIRED")

    def test_passing_reviews_make_content_ready(self) -> None:
        document = valid_document()
        add_passing_reviews(document)
        report = CHECKER.evaluate(document)
        self.assertEqual(report["status"], CHECKER.STATUS_READY)
        self.assertFalse(report["release_gates"]["clean_output_permitted"])

    def test_current_approval_baselines_content(self) -> None:
        document = valid_document()
        add_passing_reviews(document)
        add_approval(document)
        report = CHECKER.evaluate(document)
        self.assertEqual(report["status"], CHECKER.STATUS_BASELINED)
        self.assertEqual(report["state_code"], "BASELINED")
        self.assertTrue(report["operation_succeeded"])
        self.assertTrue(report["release_permitted"])
        self.assertTrue(report["release_gates"]["clean_output_permitted"])

    def test_bcp14_profile_can_pass(self) -> None:
        document = valid_document("bcp14")
        add_passing_reviews(document)
        report = CHECKER.evaluate(document)
        self.assertEqual(report["status"], CHECKER.STATUS_READY)

    def test_bcp14_requires_notice(self) -> None:
        document = valid_document("bcp14")
        document.pop("normative_language_notice")
        report = CHECKER.evaluate(document)
        self.assert_has(report, "LANG-BCP14-002", "FAIL")

    def test_bcp14_rejects_lowercase_keyword_candidate(self) -> None:
        document = valid_document("bcp14")
        document["requirements"][0]["text"] = (
            "Each protocol message MUST include an identifier and may include a label."
        )
        document["requirements"][0]["atomicity_rationale"] = (
            "The optional label is part of the same message encoding."
        )
        report = CHECKER.evaluate(document)
        self.assert_has(report, "LANG-BCP14-001", "FAIL")

    def test_mixed_profile_keywords_fail(self) -> None:
        document = valid_document()
        document["requirements"][0]["text"] = (
            "The controller shall stop and MUST report the result."
        )
        report = CHECKER.evaluate(document)
        self.assert_has(report, "PROFILE-002", "FAIL")

    def test_multiple_obligation_keywords_fail(self) -> None:
        document = valid_document()
        document["requirements"][0]["text"] = (
            "The controller shall stop, and the monitor shall report."
        )
        report = CHECKER.evaluate(document)
        self.assert_has(report, "LANG-SHALL-001", "FAIL")

    def test_ambiguous_pronoun_subject_fails(self) -> None:
        document = valid_document()
        document["requirements"][0]["text"] = (
            "It shall stop the pump within 2 seconds."
        )
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-AMB-001", "FAIL")

    def test_open_ended_phrase_fails(self) -> None:
        document = valid_document()
        document["requirements"][0]["text"] = (
            "The controller shall stop the pump as appropriate within 2 seconds."
        )
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-AMB-001", "FAIL")

    def test_subjective_term_fails(self) -> None:
        document = valid_document()
        document["requirements"][0]["text"] = (
            "The controller shall stop the pump quickly within 2 seconds."
        )
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-VRF-001", "FAIL")

    def test_controlled_term_can_use_matched_word(self) -> None:
        document = valid_document()
        document["controlled_terms"].append(
            {
                "term": "safe",
                "definition": "The SAF-001 defined state.",
                "source": "SRC-001",
                "approved": True,
            }
        )
        document["requirements"][0]["text"] = (
            "The controller shall enter the safe state within 2 seconds."
        )
        report = CHECKER.evaluate(document)
        self.assertFalse(
            any(
                issue["check"] == "REQ-VRF-001"
                and issue["result"] == "FAIL"
                and issue["evidence"].lower() == "safe"
                for issue in report["issues"]
            )
        )

    def test_changed_value_fails(self) -> None:
        document = valid_document()
        document["requirements"][0]["text"] = (
            "The controller shall stop the pump within 3 seconds."
        )
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-FID-001", "FAIL")

    def test_missing_unit_fails(self) -> None:
        document = valid_document()
        document["requirements"][0]["text"] = (
            "The controller shall stop the pump within 2."
        )
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-FID-001", "FAIL")

    def test_changed_prohibition_fails(self) -> None:
        document = valid_document()
        document["requirements"][0]["source_excerpt"] = (
            "The controller must not start the pump within 2 seconds."
        )
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-FID-001", "FAIL")

    def test_unknown_source_fails(self) -> None:
        document = valid_document()
        document["requirements"][0]["source"] = ["MISSING"]
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-SRC-001", "FAIL")

    def test_source_authority_requires_revision_location_and_digest_binding(
        self,
    ) -> None:
        document = valid_document()
        authority = document["source_authorities"][0]
        authority.pop("revision")
        authority["digest"] = "NOT-A-SHA256"
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-SRC-001", "FAIL")
        authority["revision"] = "2"
        authority["digest"] = "a" * 64
        authority.pop("digest_unavailable_reason")
        report = CHECKER.evaluate(document)
        self.assertFalse(
            any(
                issue["location"] == "source_authorities[0]"
                and issue["check"] == "REQ-SRC-001"
                and issue["result"] == "FAIL"
                for issue in report["issues"]
            )
        )

    def test_source_authority_rejects_placeholder_revision(self) -> None:
        document = valid_document()
        document["source_authorities"][0]["revision"] = "not provided"
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-SRC-001", "FAIL")
        self.assertFalse(
            any(
                issue["location"] == "source_authorities[0]"
                and issue["result"] == "PASS"
                and "revision-bound" in issue["message"]
                for issue in report["issues"]
            )
        )

    def test_each_absent_decision_authority_requires_complete_wording(
        self,
    ) -> None:
        document = valid_document()
        document["ambiguities"] = [
            {
                "id": "AMB-001",
                "decision_authority": "not provided",
            },
            {
                "id": "AMB-002",
                "decision_authority": (
                    "The decision authority is not currently authorized; "
                    "none was added."
                ),
            },
        ]
        report = CHECKER.evaluate(document)
        matching = [
            issue
            for issue in report["issues"]
            if issue["check"] == "REQ-SRC-001"
            and issue["message"]
            == "An absent decision authority must use the complete bounded statement."
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(
            matching[0]["location"],
            "document.ambiguities[0].decision_authority",
        )

    def test_duplicate_requirement_id_fails(self) -> None:
        document = valid_document()
        document["requirements"].append(copy.deepcopy(document["requirements"][0]))
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-SRC-001", "FAIL")

    def test_missing_verification_criteria_fails(self) -> None:
        document = valid_document()
        document["requirements"][0]["verification"]["success_criteria"] = ""
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-VRF-002", "FAIL")

    def test_missing_verification_evidence_requires_review(self) -> None:
        document = valid_document()
        document["requirements"][0]["verification"]["evidence"] = []
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-VRF-002", "REVIEW_REQUIRED")

    def test_conjunction_requires_atomicity_rationale(self) -> None:
        document = valid_document()
        document["requirements"][0]["text"] = (
            "The controller shall stop the pump and record the event within 2 seconds."
        )
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-ATM-001", "REVIEW_REQUIRED")

    def test_atomicity_rationale_clears_conjunction_heuristic(self) -> None:
        document = valid_document()
        requirement = document["requirements"][0]
        requirement["text"] = (
            "The controller shall stop the pump and record the event within 2 seconds."
        )
        requirement["source_excerpt"] = requirement["text"]
        requirement["atomicity_rationale"] = (
            "The record is the required evidence of the single stop operation."
        )
        report = CHECKER.evaluate(document)
        self.assertFalse(
            any(
                issue["check"] == "REQ-ATM-001"
                and issue["result"] == "REVIEW_REQUIRED"
                for issue in report["issues"]
            )
        )

    def test_placeholder_blocks_release(self) -> None:
        document = valid_document()
        document["requirements"][0]["text"] = (
            "The controller shall stop the pump within TBD seconds."
        )
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-TBD-001", "REVIEW_REQUIRED")

    def test_open_decision_blocks_release(self) -> None:
        document = valid_document()
        document["unresolved"] = [
            {
                "id": "DEC-001",
                "statement": "The timeout is unknown.",
                "decision_needed": "Approve the timeout.",
                "owner": "control-owner",
                "due_date": "2026-08-01",
                "status": "OPEN",
            }
        ]
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-TBD-001", "REVIEW_REQUIRED")

    def test_closed_decision_requires_resolution(self) -> None:
        document = valid_document()
        document["unresolved"] = [
            {
                "id": "DEC-001",
                "statement": "The timeout was unknown.",
                "decision_needed": "Approve the timeout.",
                "status": "CLOSED",
            }
        ]
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-TBD-001", "REVIEW_REQUIRED")

    def test_stale_review_fails(self) -> None:
        document = valid_document()
        add_passing_reviews(document)
        document["requirements"][0]["rationale"] = "Changed after review."
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REVIEW-001", "FAIL")

    def test_failed_human_review_fails(self) -> None:
        document = valid_document()
        add_passing_reviews(document)
        document["reviews"][0]["result"] = "FAIL"
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REVIEW-001", "FAIL")

    def test_rejected_approval_fails(self) -> None:
        document = valid_document()
        add_passing_reviews(document)
        add_approval(document)
        document["approvals"][0]["result"] = "REJECTED"
        report = CHECKER.evaluate(document)
        self.assert_has(report, "APPROVAL-001", "FAIL")

    def test_wrong_approval_role_fails(self) -> None:
        document = valid_document()
        add_passing_reviews(document)
        add_approval(document)
        document["approvals"][0]["role"] = "author"
        report = CHECKER.evaluate(document)
        self.assert_has(report, "APPROVAL-001", "FAIL")

    def test_undeclared_approver_fails(self) -> None:
        document = valid_document()
        add_passing_reviews(document)
        add_approval(document)
        document["approvals"][0]["approver_id"] = "unknown-owner"
        report = CHECKER.evaluate(document)
        self.assert_has(report, "APPROVAL-001", "FAIL")

    def test_missing_approval_authority_blocks_readiness(self) -> None:
        document = valid_document()
        document.pop("approval_authority")
        add_passing_reviews(document)
        report = CHECKER.evaluate(document)
        self.assertEqual(report["status"], CHECKER.STATUS_DRAFT)
        self.assert_has(report, "APPROVAL-001", "REVIEW_REQUIRED")

    def test_traceability_matrix_contains_requirement(self) -> None:
        report = CHECKER.evaluate(valid_document())
        self.assertEqual(report["traceability_matrix"][0]["requirement_id"], "REQ-001")
        self.assertEqual(report["traceability_matrix"][0]["sources"], ["SRC-001"])

    def test_markdown_report_has_evidence_tables(self) -> None:
        report = CHECKER.evaluate(valid_document())
        markdown = CHECKER.render_markdown(report)
        self.assertIn("## Findings", markdown)
        self.assertIn("## Traceability and verification matrix", markdown)
        self.assertIn("## Limitations", markdown)

    def test_clean_output_fails_before_baseline(self) -> None:
        document = valid_document()
        add_passing_reviews(document)
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            input_path = temp_path / "requirements.yaml"
            clean_path = temp_path / "clean.txt"
            input_path.write_text(
                yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
            )
            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(input_path),
                    "--format",
                    "json",
                    "--clean-output",
                    str(clean_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertFalse(clean_path.exists())

    def test_clean_output_succeeds_after_baseline(self) -> None:
        document = valid_document()
        add_passing_reviews(document)
        add_approval(document)
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            input_path = temp_path / "requirements.yaml"
            clean_path = temp_path / "clean.txt"
            input_path.write_text(
                yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
            )
            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(input_path),
                    "--format",
                    "json",
                    "--clean-output",
                    str(clean_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("REQ-001 The controller shall", clean_path.read_text())

    def test_both_format_writes_machine_and_human_reports(self) -> None:
        document = valid_document()
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            input_path = temp_path / "requirements.yaml"
            report_dir = temp_path / "report"
            input_path.write_text(
                yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
            )
            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(input_path),
                    "--format",
                    "both",
                    "--output-dir",
                    str(report_dir),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            digest_prefix = CHECKER.content_digest(document).split(":", 1)[1][:12]
            json_report = report_dir / f"requirements-report-{digest_prefix}.json"
            markdown_report = report_dir / f"requirements-report-{digest_prefix}.md"
            self.assertTrue(json_report.exists())
            self.assertTrue(markdown_report.exists())
            parsed = json.loads(
                json_report.read_text()
            )
            self.assertEqual(parsed["status"], CHECKER.STATUS_DRAFT)
            self.assertFalse(parsed["release_permitted"])
            second = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(input_path),
                    "--format",
                    "both",
                    "--output-dir",
                    str(report_dir),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(second.returncode, 2)
            self.assertIn("Use --overwrite", second.stderr)
            overwritten = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(input_path),
                    "--format",
                    "both",
                    "--output-dir",
                    str(report_dir),
                    "--overwrite",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(overwritten.returncode, 1)

    def test_template_generation_supports_each_profile(self) -> None:
        for profile in ("shall", "bcp14"):
            generated = CHECKER.template(profile)
            self.assertEqual(generated["language_profile"], profile)
            self.assertEqual(generated["lifecycle_profile"], "general")
            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--emit-template",
                    profile,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            parsed = yaml.safe_load(result.stdout)
            self.assertEqual(parsed["language_profile"], profile)
        self.assertIn("normative_language_notice", CHECKER.template("bcp14"))
        generated = CHECKER.template("shall", "nasa-npr-7123.1d")
        self.assertIn(
            "current_authority_record", generated["npr_process_evidence"]
        )

    def test_realistic_safety_requirement_preserves_prohibition_and_threshold(
        self,
    ) -> None:
        document = valid_document()
        document["title"] = "Pressure chamber interlock requirements"
        document["objective"] = "Prevent unsafe chamber-door operation."
        document["controlled_terms"] = [
            {
                "term": "chamber door",
                "definition": "The pressure chamber access door.",
                "source": "SRC-001",
                "approved": True,
            }
        ]
        document["protected_values"] = ["5 psi"]
        requirement = document["requirements"][0]
        requirement.update(
            {
                "type": "safety",
                "text": (
                    "The chamber door shall not unlock when the chamber pressure "
                    "is 5 psi or more."
                ),
                "source_excerpt": (
                    "The chamber door must not unlock at or above 5 psi."
                ),
                "rationale": "Prevent personnel exposure to chamber pressure.",
            }
        )
        requirement["verification"] = {
            "method": "test",
            "success_criteria": (
                "The lock remains engaged at each tested pressure of 5 psi or more."
            ),
            "evidence": ["planned-test:SAF-INTERLOCK-001"],
        }
        add_passing_reviews(document)
        add_approval(document)
        report = CHECKER.evaluate(document)
        self.assertEqual(report["status"], CHECKER.STATUS_BASELINED)
        self.assertIn("shall not", requirement["text"])
        self.assertIn("5 psi", requirement["text"])

    def test_realistic_bcp14_retry_requirement_is_traceable(self) -> None:
        document = valid_document("bcp14")
        document["title"] = "Client retry protocol"
        document["objective"] = "Bound duplicate retry traffic."
        document["protected_values"] = ["3"]
        requirement = document["requirements"][0]
        requirement.update(
            {
                "type": "functional",
                "text": (
                    "A client MUST send no more than 3 retry requests for one "
                    "operation."
                ),
                "source_excerpt": (
                    "A client must send no more than 3 retry requests for one "
                    "operation."
                ),
                "rationale": "Limit duplicate traffic for one operation.",
            }
        )
        requirement["verification"] = {
            "method": "test",
            "success_criteria": (
                "The client sends 0 through 3 retry requests and never sends a "
                "fourth retry request for one operation."
            ),
            "evidence": ["planned-test:RETRY-001"],
        }
        add_passing_reviews(document)
        report = CHECKER.evaluate(document)
        self.assertEqual(report["status"], CHECKER.STATUS_READY)
        self.assertEqual(
            report["traceability_matrix"][0]["requirement_id"], "REQ-001"
        )

    def test_realistic_ambiguous_recovery_target_remains_unresolved(self) -> None:
        document = valid_document()
        document["title"] = "Service recovery requirements"
        document["objective"] = "Define service recovery behavior."
        document["requirements"] = []
        document["unresolved"] = [
            {
                "id": "DEC-RECOVERY-001",
                "statement": "The service must recover quickly after a failure.",
                "decision_needed": (
                    "Approve a recovery event, maximum duration, load condition, "
                    "and success measurement."
                ),
                "owner": "service-owner",
                "due_date": "2026-08-15",
                "status": "OPEN",
            }
        ]
        report = CHECKER.evaluate(document)
        self.assertEqual(report["status"], CHECKER.STATUS_DRAFT)
        self.assertFalse(report["release_gates"]["clean_output_permitted"])

    def test_realistic_source_conflict_blocks_baseline(self) -> None:
        document = valid_document()
        document["source_authorities"].append(
            {
                "id": "SRC-002",
                "title": "Approved interface brief",
                "revision": "1",
                "location": "approved-interface-brief:4.2",
                "precedence": 1,
                "digest_unavailable_reason": (
                    "The authority is a controlled record without accessible source bytes."
                ),
            }
        )
        document["unresolved"] = [
            {
                "id": "DEC-SOURCE-001",
                "statement": (
                    "SRC-001 requires a 2-second stop and SRC-002 requires a "
                    "3-second stop."
                ),
                "decision_needed": "Select the controlling stop-time requirement.",
                "owner": "requirements-owner",
                "due_date": "2026-08-15",
                "status": "OPEN",
            }
        ]
        report = CHECKER.evaluate(document)
        self.assertEqual(report["status"], CHECKER.STATUS_DRAFT)
        self.assert_has(report, "REQ-CTX-001", "REVIEW_REQUIRED")

    def test_complete_nasa_handbook_artifact_can_be_baselined(self) -> None:
        document = nasa_document()
        add_passing_reviews(document)
        add_approval(document)
        report = CHECKER.evaluate(document)
        self.assertEqual(report["status"], CHECKER.STATUS_BASELINED)
        self.assertTrue(report["release_gates"]["lifecycle_evidence"])
        self.assertTrue(report["release_gates"]["clean_output_permitted"])

    def test_nasa_profile_requires_stakeholder_expectations(self) -> None:
        document = nasa_document()
        del document["stakeholder_context"]
        report = CHECKER.evaluate(document)
        self.assertEqual(report["status"], CHECKER.STATUS_FAILED)
        self.assert_has(report, "STK-001", "FAIL")

    def test_nasa_profile_requires_every_completeness_category(self) -> None:
        document = nasa_document()
        document["completeness_assessment"].pop()
        report = CHECKER.evaluate(document)
        self.assertEqual(report["status"], CHECKER.STATUS_FAILED)
        self.assert_has(report, "REQ-COMPLETE-001", "FAIL")

    def test_verification_and_validation_matrices_are_distinct(self) -> None:
        report = CHECKER.evaluate(nasa_document())
        verification = report["traceability_matrix"][0]
        validation = report["validation_matrix"][0]
        expected_verification = {
            "requirement_id",
            "requirement",
            "sources",
            "source_document",
            "source_paragraph",
            "verification_method",
            "success_criteria",
            "verification_level",
            "verification_lead",
            "facility",
            "phase",
            "acceptance_requirement",
            "preflight_acceptance",
            "performing_organization",
            "results_state",
            "evidence",
            "configuration",
            "discrepancies",
        }
        expected_validation = {
            "product_id",
            "activity",
            "objective",
            "method",
            "facility",
            "phase",
            "performing_organization",
            "results_state",
            "evidence",
            "stakeholder_expectations",
            "conops_references",
            "moe_references",
            "intended_environment",
            "representative_users",
        }
        self.assertEqual(set(verification), expected_verification)
        self.assertEqual(set(validation), expected_validation)
        self.assertNotEqual(verification["requirement_id"], validation["product_id"])

    def test_nasa_profile_rejects_incomplete_verification_plan(self) -> None:
        document = nasa_document()
        del document["requirements"][0]["verification"]["verification_lead"]
        report = CHECKER.evaluate(document)
        self.assert_has(report, "VRF-PLAN-002", "FAIL")

    def test_trace_rejects_unknown_parent(self) -> None:
        document = nasa_document()
        document["requirements"][0]["parents"] = ["REQ-UNKNOWN"]
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-TRACE-001", "FAIL")

    def test_derived_requirement_requires_basis(self) -> None:
        document = nasa_document()
        document["requirements"][0]["derived"] = True
        report = CHECKER.evaluate(document)
        self.assert_has(report, "REQ-DERIVED-001", "FAIL")

    def test_npr_profile_fails_without_process_authority_evidence(self) -> None:
        document = nasa_document()
        document["lifecycle_profile"] = "nasa-npr-7123.1d"
        report = CHECKER.evaluate(document)
        self.assertEqual(report["status"], CHECKER.STATUS_FAILED)
        self.assert_has(report, "NPR-AUTH-001", "FAIL")

    def test_npr_profile_can_baseline_artifact_but_not_claim_compliance(
        self,
    ) -> None:
        document = nasa_document(npr=True)
        add_passing_reviews(document)
        add_approval(document)
        report = CHECKER.evaluate(document)
        self.assertEqual(report["status"], CHECKER.STATUS_BASELINED)
        self.assertTrue(report["release_gates"]["npr_authority_evidence"])
        self.assertIn("not NASA certification", report["claim_boundary"])
        self.assertNotIn("NASA compliant", report["status"])

    def test_npr_profile_rejects_stale_or_unbound_authority_record(self) -> None:
        document = nasa_document(npr=True)
        authority = document["npr_process_evidence"]["current_authority_record"]
        authority["checked_at"] = "2000-01-01T00:00:00+00:00"
        authority["manifest_sha256"] = "not-a-digest"
        report = CHECKER.evaluate(document)
        self.assertEqual(report["status"], CHECKER.STATUS_FAILED)
        self.assert_has(report, "NPR-AUTH-002", "FAIL")
        authority["checked_at"] = "2999-01-01T00:00:00+00:00"
        authority["manifest_sha256"] = hashlib.sha256(
            (
                ROOT
                / "write-verifiable-requirements"
                / "references"
                / "reference-manifest.json"
            ).read_bytes()
        ).hexdigest()
        report = CHECKER.evaluate(document)
        self.assert_has(report, "NPR-AUTH-002", "FAIL")

    def test_legacy_combined_profile_fails_closed(self) -> None:
        document = valid_document()
        document["profile"] = "nasa-shall"
        report = CHECKER.evaluate(document)
        self.assert_has(report, "PROFILE-001", "FAIL")

    def test_reference_files_match_recorded_hashes_and_section_inventory(
        self,
    ) -> None:
        references = ROOT / "write-verifiable-requirements" / "references"
        coverage = yaml.safe_load(
            (references / "nasa-reference-coverage.yaml").read_text()
        )
        self.assertEqual(len(coverage["handbook_sections"]), 64)
        for authority in coverage["authorities"]:
            bundled = references / authority["bundled_file"]
            digest = hashlib.sha256(bundled.read_bytes()).hexdigest()
            self.assertEqual(digest, authority["sha256"])
        governing = {
            row["id"]
            for row in coverage["handbook_sections"]
            if row["classification"] == "governing"
        }
        self.assertEqual(
            governing,
            {
                "1.1",
                "1.2",
                "2.4",
                "2.6",
                "3.11",
                "4.0",
                "4.1",
                "4.2",
                "4.3",
                "5.3",
                "5.4",
                "6.2",
                "6.3",
                "6.5",
                "6.6",
                "Appendix C",
                "Appendix D",
                "Appendix E",
                "Appendix I",
                "Appendix L",
                "Appendix N",
                "Appendix S",
            },
        )
        rules = yaml.safe_load(
            (references / "requirements-rules.yaml").read_text()
        )
        rule_ids = {rule["id"] for rule in rules["rules"]}
        for row in coverage["handbook_sections"]:
            if row["classification"] == "governing":
                self.assertTrue(row.get("controls"), row["id"])
                self.assertFalse(set(row["controls"]) - rule_ids, row["id"])

    def test_every_verified_rule_has_a_source_basis_and_enforcement(
        self,
    ) -> None:
        path = (
            ROOT
            / "write-verifiable-requirements"
            / "references"
            / "requirements-rules.yaml"
        )
        rules = yaml.safe_load(path.read_text())
        self.assertGreaterEqual(len(rules["rules"]), 36)
        for rule in rules["rules"]:
            self.assertTrue(rule["id"])
            self.assertTrue(rule["requirement"])
            self.assertTrue(rule["basis"])
            self.assertTrue(rule["enforcement"])
            self.assertNotEqual(rule["basis"], "model memory")
            self.assertNotRegex(rule["basis"], r"\bitems? \d")

    def test_every_emitted_check_has_a_verified_rule(self) -> None:
        rules_path = (
            ROOT
            / "write-verifiable-requirements"
            / "references"
            / "requirements-rules.yaml"
        )
        rules = yaml.safe_load(rules_path.read_text())["rules"]
        rule_ids = {rule["id"] for rule in rules}
        tree = ast.parse(SCRIPT.read_text())
        emitted = {
            call.args[2].value
            for call in ast.walk(tree)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "add"
            and len(call.args) > 2
            and isinstance(call.args[2], ast.Constant)
            and isinstance(call.args[2].value, str)
        }
        self.assertFalse(emitted - rule_ids)
        automated = {
            rule["id"]
            for rule in rules
            if rule["enforcement"] in {"automated", "automated_gate"}
        }
        self.assertFalse(automated - emitted)

    def test_appendix_c_validation_topics_are_complete(self) -> None:
        expected = {
            "clarity_unambiguous",
            "clarity_concise_simple",
            "clarity_one_thought",
            "clarity_one_subject_predicate",
            "incomplete_requirements_tracked",
            "functional_requirements",
            "performance_requirements",
            "interface_requirements",
            "environment_requirements",
            "facility_requirements",
            "transportation_requirements",
            "training_requirements",
            "personnel_requirements",
            "operability_requirements",
            "safety_requirements",
            "security_requirements",
            "appearance_physical_requirements",
            "design_requirements",
            "assumptions_explicit",
            "correct_product_level",
            "free_of_implementation_specifics",
            "free_of_operations_descriptions",
            "free_of_personnel_task_assignments",
            "requirements_consistent",
            "stakeholder_glossary_alignment",
            "terminology_consistent",
            "requirements_necessary",
            "bidirectional_traceability",
            "unique_references",
            "technical_correctness",
            "assumptions_confirmed",
            "technical_feasibility",
            "function_necessity_sufficiency",
            "performance_specifications_margins",
            "tolerance_realism",
            "external_interfaces",
            "internal_interfaces",
            "interface_necessity_sufficiency_consistency",
            "maintainability_measurable",
            "change_coupling_minimized",
            "reliability_measurable",
            "error_detection_reporting_handling_recovery",
            "undesired_event_responses",
            "function_sequence_assumptions",
            "fault_survivability",
            "verifiable_at_requirement_level",
            "verification_success_criteria_precision",
            "unverifiable_terms_absent",
            "dont_care_conditions_explicit",
            "human_system_integration",
            "logistics",
            "disposal",
            "quality_factors",
        }
        self.assertEqual(CHECKER.COMPLETENESS_CATEGORIES, expected)


if __name__ == "__main__":
    unittest.main()
