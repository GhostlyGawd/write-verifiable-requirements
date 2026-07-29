#!/usr/bin/env python3
"""Validate structured requirements and derive a fail-closed release status.

This checker validates declared structure and selected language patterns. It
does not prove semantic correctness, completeness, feasibility, safety, or
conflict freedom.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml


STATUS_DRAFT = "DRAFT — SOURCE OR DECISIONS INCOMPLETE"
STATUS_FAILED = "NOT READY — REQUIREMENT QUALITY CHECK FAILED"
STATUS_READY = "READY FOR BASELINE REVIEW"
STATUS_BASELINED = "BASELINED — AUTHORIZED APPROVAL RECORDED"

RESULTS = {"PASS", "FAIL", "REVIEW_REQUIRED", "NOT_APPLICABLE"}
LANGUAGE_PROFILES = {"shall", "bcp14"}
LIFECYCLE_PROFILES = {
    "general",
    "nasa-se-handbook-rev2",
    "nasa-npr-7123.1d",
}
NASA_LIFECYCLE_PROFILES = {
    "nasa-se-handbook-rev2",
    "nasa-npr-7123.1d",
}
REQUIREMENT_TYPES = {
    "functional",
    "performance",
    "interface",
    "constraint",
    "safety",
    "security",
    "quality",
    "operational",
}
VERIFICATION_METHODS = {"inspection", "analysis", "demonstration", "test"}
VERIFICATION_STATES = {"PLANNED", "PASS", "FAIL", "NOT_RUN"}
CORE_REVIEW_DIMENSIONS = {
    "source_fidelity",
    "coverage",
    "conflicts",
    "feasibility",
    "verification_adequacy",
}
NASA_REVIEW_DIMENSIONS = {
    "validation_adequacy",
    "traceability",
    "interfaces",
    "lifecycle_completeness",
}
REVIEW_DIMENSIONS = CORE_REVIEW_DIMENSIONS | NASA_REVIEW_DIMENSIONS
COMPLETENESS_CATEGORIES = {
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
VAGUE_PATTERNS = {
    "REQ-AMB-001": [
        r"\bas appropriate\b",
        r"\band/or\b",
        r"\betc\.",
        r"\bbut not limited to\b",
    ],
    "REQ-VRF-001": [
        r"\badequate(?:ly)?\b",
        r"\beasy\b",
        r"\befficient(?:ly)?\b",
        r"\bfast\b",
        r"\bflexible\b",
        r"\bmaximize\b",
        r"\bminimize\b",
        r"\bquickly\b",
        r"\brobust\b",
        r"\bsafe\b",
        r"\bsufficient(?:ly)?\b",
        r"\buser-friendly\b",
    ],
}
PLACEHOLDER_RE = re.compile(r"\b(?:TBD|TBR|TBC)\b")
MISSING_SOURCE_IDENTITY_VALUES = {
    "n/a",
    "na",
    "none",
    "not provided",
    "not specified",
    "unknown",
    "unavailable",
}
AUTHORITY_ABSENCE_CLAUSES = ("not currently authorized", "none was added")
NUMBER_UNIT_RE = re.compile(
    r"(?<![\w.])[-+]?\d+(?:[.,]\d+)?"
    r"(?:\s*(?:%|°[CF]|[A-Za-zµ]+(?:/[A-Za-z]+)?))?"
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
NPR_AUTHORITY_MARKERS = {
    "NPR 7123.1D",
    "Effective Date: July 05, 2023",
    "Expiration Date: July 05, 2028",
    "Updated w/Change 2",
}
NPR_AUTHORITY_URL = (
    "https://nodis3.gsfc.nasa.gov/displayDir.cfm?"
    "Internal_ID=N_PR_7123_001D_"
)


@dataclass(frozen=True)
class Issue:
    location: str
    check: str
    result: str
    basis: str
    message: str
    evidence: str = ""


def add(
    issues: list[Issue],
    location: str,
    check: str,
    result: str,
    basis: str,
    message: str,
    evidence: str = "",
) -> None:
    if result not in RESULTS:
        raise ValueError(f"Unsupported result: {result}")
    issues.append(Issue(location, check, result, basis, message, evidence))


def load_document(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc
    try:
        data = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("The input root must be a mapping.")
    return data


def canonical_content(document: dict[str, Any]) -> dict[str, Any]:
    excluded = {"reviews", "approvals", "status"}
    return {key: value for key, value in document.items() if key not in excluded}


def content_digest(document: dict[str, Any]) -> str:
    payload = json.dumps(
        canonical_content(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def text_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def check_required_context(document: dict[str, Any], issues: list[Issue]) -> None:
    for field in ("title", "objective", "system_boundary"):
        if text_value(document.get(field)):
            add(
                issues,
                f"document.{field}",
                "REQ-CTX-001",
                "PASS",
                "NASA-SEH-REV2 Appendix C",
                f"{field} is present.",
            )
        else:
            add(
                issues,
                f"document.{field}",
                "REQ-CTX-001",
                "REVIEW_REQUIRED",
                "NASA-SEH-REV2 Appendix C",
                f"{field} is required.",
            )

    if string_list(document.get("intended_readers")):
        add(
            issues,
            "document.intended_readers",
            "REQ-CTX-001",
            "PASS",
            "NASA-SEH-REV2 Appendix C",
            "Intended readers are identified.",
        )
    else:
        add(
            issues,
            "document.intended_readers",
            "REQ-CTX-001",
            "REVIEW_REQUIRED",
            "NASA-SEH-REV2 Appendix C",
            "At least one intended reader is required.",
        )

    lifecycle_scope = document.get("lifecycle_scope")
    required_scope_fields = (
        "product_layer",
        "lifecycle_phase",
        "included_processes",
        "excluded_processes",
    )
    if not isinstance(lifecycle_scope, dict):
        add(
            issues,
            "document.lifecycle_scope",
            "REQ-CTX-001",
            "REVIEW_REQUIRED",
            "NASA-SEH-REV2 sections 1.2 and 3",
            "Lifecycle scope is required.",
        )
    else:
        missing = [
            field
            for field in required_scope_fields
            if (
                not isinstance(lifecycle_scope.get(field), list)
                if field.endswith("processes")
                else not text_value(lifecycle_scope.get(field))
            )
        ]
        add(
            issues,
            "document.lifecycle_scope",
            "REQ-CTX-001",
            "REVIEW_REQUIRED" if missing else "PASS",
            "NASA-SEH-REV2 sections 1.2 and 3",
            (
                "Lifecycle scope is incomplete."
                if missing
                else "Product layer, lifecycle phase, and process scope are declared."
            ),
            ", ".join(missing),
        )


def check_sources(
    document: dict[str, Any], issues: list[Issue]
) -> tuple[set[str], dict[str, int]]:
    authorities = document.get("source_authorities")
    if not isinstance(authorities, list) or not authorities:
        add(
            issues,
            "document.source_authorities",
            "REQ-SRC-001",
            "REVIEW_REQUIRED",
            "NASA-SEH-REV2 Appendix C",
            "At least one ordered source authority is required.",
        )
        return set(), {}

    source_ids: set[str] = set()
    precedences: dict[str, int] = {}
    for index, authority in enumerate(authorities):
        location = f"source_authorities[{index}]"
        if not isinstance(authority, dict):
            add(
                issues,
                location,
                "REQ-SRC-001",
                "FAIL",
                "NASA-SEH-REV2 Appendix C",
                "Source authority must be a mapping.",
            )
            continue
        source_id = text_value(authority.get("id"))
        title = text_value(authority.get("title"))
        revision = text_value(authority.get("revision"))
        source_location = text_value(authority.get("location"))
        revision_normalized = revision.casefold()
        location_normalized = source_location.casefold()
        revision_is_missing = (
            revision_normalized in MISSING_SOURCE_IDENTITY_VALUES
            or any(
                clause in revision_normalized
                for clause in AUTHORITY_ABSENCE_CLAUSES
            )
        )
        location_is_missing = (
            location_normalized in MISSING_SOURCE_IDENTITY_VALUES
            or any(
                clause in location_normalized
                for clause in AUTHORITY_ABSENCE_CLAUSES
            )
        )
        source_digest = text_value(authority.get("digest"))
        digest_unavailable_reason = text_value(
            authority.get("digest_unavailable_reason")
        )
        precedence = authority.get("precedence")
        digest_valid = bool(SHA256_RE.fullmatch(source_digest))
        digest_binding_valid = (
            digest_valid and not digest_unavailable_reason
        ) or (
            not source_digest and bool(digest_unavailable_reason)
        )
        if (
            not source_id
            or not title
            or not revision
            or revision_is_missing
            or not source_location
            or location_is_missing
            or not isinstance(precedence, int)
            or precedence < 1
            or not digest_binding_valid
        ):
            add(
                issues,
                location,
                "REQ-SRC-001",
                "FAIL",
                "NASA-SEH-REV2 Appendix C",
                "Source authority requires id, title, revision, location, positive integer precedence, and exactly one valid digest binding.",
                (
                    "Use a 64-character lowercase SHA-256 digest when source "
                    "bytes are available. Otherwise, give "
                    "digest_unavailable_reason."
                ),
            )
            continue
        if source_id in source_ids:
            add(
                issues,
                location,
                "REQ-SRC-001",
                "FAIL",
                "NASA-SEH-REV2 Appendix C",
                f"Duplicate source authority id: {source_id}.",
            )
            continue
        source_ids.add(source_id)
        precedences[source_id] = precedence
        add(
            issues,
            location,
            "REQ-SRC-001",
            "PASS",
            "NASA-SEH-REV2 Appendix C",
            f"Source authority {source_id} is defined and revision-bound.",
            (
                f"revision={revision}; location={source_location}; "
                + (
                    f"digest={source_digest}"
                    if source_digest
                    else f"digest unavailable: {digest_unavailable_reason}"
                )
            ),
        )

    duplicate_precedence = {
        rank for rank in precedences.values() if list(precedences.values()).count(rank) > 1
    }
    if duplicate_precedence:
        add(
            issues,
            "document.source_authorities",
            "REQ-CTX-001",
            "REVIEW_REQUIRED",
            "NASA-SEH-REV2 Appendix C",
            "Source precedence is not decisive.",
            f"Repeated precedence values: {sorted(duplicate_precedence)}",
        )
    return source_ids, precedences


def check_authority_gap_wording(
    document: dict[str, Any], issues: list[Issue]
) -> None:
    stack: list[tuple[str, Any]] = [("document", document)]
    missing_values = MISSING_SOURCE_IDENTITY_VALUES | {
        "not identified",
        "not authorized",
    }
    while stack:
        location, value = stack.pop()
        if isinstance(value, dict):
            for field, child in value.items():
                child_location = f"{location}.{field}"
                if field == "decision_authority":
                    wording = text_value(child).casefold()
                    authority_is_absent = (
                        wording in missing_values
                        or "not currently authorized" in wording
                        or "none was added" in wording
                    )
                    has_complete_statement = all(
                        clause in wording for clause in AUTHORITY_ABSENCE_CLAUSES
                    )
                    if authority_is_absent and not has_complete_statement:
                        add(
                            issues,
                            child_location,
                            "REQ-SRC-001",
                            "FAIL",
                            "Skill source-authority policy",
                            (
                                "An absent decision authority must use the "
                                "complete bounded statement."
                            ),
                            (
                                "The decision authority is not currently "
                                "authorized; none was added."
                            ),
                        )
                stack.append((child_location, child))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                stack.append((f"{location}[{index}]", child))


def check_profile(
    document: dict[str, Any], issues: list[Issue]
) -> tuple[str, str]:
    legacy_profile = text_value(document.get("profile"))
    language_profile = text_value(document.get("language_profile"))
    lifecycle_profile = text_value(document.get("lifecycle_profile"))
    if legacy_profile:
        add(
            issues,
            "document.profile",
            "PROFILE-001",
            "FAIL",
            "requirements-schema.md",
            "The legacy profile field combines language and lifecycle concerns. Use language_profile and lifecycle_profile.",
            legacy_profile,
        )
    if language_profile not in LANGUAGE_PROFILES:
        add(
            issues,
            "document.language_profile",
            "PROFILE-001",
            "FAIL",
            "requirements-rules.yaml",
            "Language profile must be shall or bcp14.",
        )
    else:
        add(
            issues,
            "document.language_profile",
            "PROFILE-001",
            "PASS",
            "requirements-rules.yaml",
            f"Selected language profile: {language_profile}.",
        )
    if lifecycle_profile not in LIFECYCLE_PROFILES:
        add(
            issues,
            "document.lifecycle_profile",
            "PROFILE-001",
            "FAIL",
            "requirements-rules.yaml",
            "Lifecycle profile must be general, nasa-se-handbook-rev2, or nasa-npr-7123.1d.",
        )
    else:
        add(
            issues,
            "document.lifecycle_profile",
            "PROFILE-001",
            "PASS",
            "requirements-rules.yaml",
            f"Selected lifecycle profile: {lifecycle_profile}.",
        )

    notice = text_value(document.get("normative_language_notice"))
    if language_profile == "bcp14":
        lowered = notice.lower()
        required_fragments = ("bcp 14", "rfc 2119", "rfc 8174", "uppercase")
        if all(fragment in lowered for fragment in required_fragments):
            add(
                issues,
                "document.normative_language_notice",
                "LANG-BCP14-002",
                "PASS",
                "RFC-8174",
                "The BCP 14 notice identifies both RFCs and uppercase use.",
            )
        else:
            add(
                issues,
                "document.normative_language_notice",
                "LANG-BCP14-002",
                "FAIL",
                "RFC-8174",
                "The BCP 14 notice must identify BCP 14, RFC 2119, RFC 8174, and uppercase use.",
            )
    elif language_profile == "shall" and notice:
        add(
            issues,
            "document.normative_language_notice",
            "LANG-SHALL-001",
            "REVIEW_REQUIRED",
            "requirements-rules.yaml",
            "A BCP 14 notice is present in a shall-profile document. Remove it or select bcp14.",
        )
    return language_profile, lifecycle_profile


def controlled_terms(document: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    entries = document.get("controlled_terms")
    if not isinstance(entries, list):
        return result
    for entry in entries:
        if isinstance(entry, dict):
            term = text_value(entry.get("term"))
            definition = text_value(entry.get("definition"))
            if term and definition and entry.get("approved") is True:
                result.add(term.casefold())
    return result


def normative_matches(text: str, profile: str) -> list[str]:
    if profile == "shall":
        return re.findall(r"\bshall(?: not)?\b", text)
    if profile == "bcp14":
        return re.findall(r"\b(?:MUST NOT|SHOULD NOT|MUST|SHOULD|MAY|OPTIONAL)\b", text)
    return []


def check_normative_form(
    requirement: dict[str, Any],
    location: str,
    profile: str,
    issues: list[Issue],
) -> None:
    text = text_value(requirement.get("text"))
    matches = normative_matches(text, profile)
    basis = (
        "NASA-SEH-REV2 Appendix C"
        if profile == "shall"
        else "RFC-2119; RFC-8174"
    )
    check = "LANG-SHALL-001" if profile == "shall" else "LANG-BCP14-001"
    if len(matches) != 1:
        add(
            issues,
            location,
            check,
            "FAIL",
            basis,
            "A requirement must contain exactly one profile keyword.",
            f"Detected keywords: {matches}",
        )
    else:
        add(
            issues,
            location,
            check,
            "PASS",
            basis,
            f"One profile keyword is present: {matches[0]}.",
        )

    if profile == "shall":
        mixed = re.findall(
            r"\b(?:MUST NOT|SHOULD NOT|MUST|SHOULD|MAY|OPTIONAL)\b", text
        )
    else:
        mixed = re.findall(r"\bshall(?: not)?\b", text, flags=re.IGNORECASE)
    if mixed:
        add(
            issues,
            location,
            "PROFILE-002",
            "FAIL",
            "requirements-rules.yaml",
            "The requirement mixes normative-language profiles.",
            f"Foreign keywords: {mixed}",
        )
    if profile == "bcp14":
        lowercase_candidates = re.findall(
            r"\b(?:must|should|may|optional)\b", text
        )
        if lowercase_candidates:
            add(
                issues,
                location,
                "LANG-BCP14-001",
                "FAIL",
                "RFC-8174",
                "A lowercase BCP 14 candidate is not an uppercase normative keyword.",
                f"Lowercase candidates: {lowercase_candidates}",
            )

    keyword_pattern = (
        r"\bshall(?: not)?\b"
        if profile == "shall"
        else r"\b(?:MUST NOT|SHOULD NOT|MUST|SHOULD|MAY|OPTIONAL)\b"
    )
    split = re.split(keyword_pattern, text, maxsplit=1)
    subject = split[0].strip() if len(split) > 1 else ""
    if not subject:
        add(
            issues,
            location,
            "REQ-CLR-001",
            "FAIL",
            "NASA-SEH-REV2 Appendix C",
            "The requirement needs an explicit subject before its normative keyword.",
        )
    elif re.match(
        r"^(?:it|this|that|these|those|they|he|she|which)\b",
        subject,
        flags=re.IGNORECASE,
    ):
        add(
            issues,
            location,
            "REQ-AMB-001",
            "FAIL",
            "NASA-SEH-REV2 Appendix C",
            "The requirement subject starts with a potentially ambiguous pronoun.",
            subject,
        )


def check_language_patterns(
    requirement: dict[str, Any],
    location: str,
    terms: set[str],
    issues: list[Issue],
) -> None:
    text = text_value(requirement.get("text"))
    sentences = [
        item for item in re.split(r"(?<=[.!?])\s+", text.strip()) if item.strip()
    ]
    if len(sentences) > 1:
        add(
            issues,
            location,
            "REQ-ATM-001",
            "FAIL",
            "NASA-SEH-REV2 Appendix C",
            "A requirement must contain one normative statement.",
            f"Detected sentence count: {len(sentences)}",
        )
    if text and text[-1] not in ".!?":
        add(
            issues,
            location,
            "REQ-CLR-001",
            "FAIL",
            "NASA-SEH-REV2 Appendix C",
            "The requirement must be a complete sentence with terminal punctuation.",
        )

    lowered = text.casefold()
    for check, patterns in VAGUE_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match and match.group(0).casefold() not in terms:
                add(
                    issues,
                    location,
                    check,
                    "FAIL",
                    "NASA-SEH-REV2 Appendix C",
                    "The requirement contains an open-ended or unverifiable term.",
                    match.group(0),
                )

    if PLACEHOLDER_RE.search(text):
        add(
            issues,
            location,
            "REQ-TBD-001",
            "REVIEW_REQUIRED",
            "NASA-SEH-REV2 Appendix C",
            "The requirement contains an unresolved placeholder.",
            ", ".join(sorted(set(PLACEHOLDER_RE.findall(text)))),
        )

    if re.search(r"\b(?:shall(?: not)?|MUST NOT|SHOULD NOT|MUST|SHOULD|MAY|OPTIONAL)\b.*\band\b", text):
        rationale = text_value(requirement.get("atomicity_rationale"))
        if not rationale:
            add(
                issues,
                location,
                "REQ-ATM-001",
                "REVIEW_REQUIRED",
                "NASA-SEH-REV2 Appendix C",
                "A conjunction follows the obligation. Split the requirement or explain why it has one outcome.",
            )


def normalize_literal(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def check_source_fidelity(
    requirement: dict[str, Any],
    location: str,
    protected_values: list[str],
    profile: str,
    issues: list[Issue],
) -> None:
    source_excerpt = text_value(requirement.get("source_excerpt"))
    text = text_value(requirement.get("text"))
    if not source_excerpt:
        add(
            issues,
            location,
            "REQ-FID-001",
            "REVIEW_REQUIRED",
            "NASA-SEH-REV2 Appendix C",
            "A source excerpt is required for a fidelity comparison.",
        )
        return

    missing_values: list[str] = []
    source_normalized = normalize_literal(source_excerpt)
    target_normalized = normalize_literal(text)
    literals = {match.group(0).strip() for match in NUMBER_UNIT_RE.finditer(source_excerpt)}
    literals.update(
        value
        for value in protected_values
        if normalize_literal(value) in source_normalized
    )
    for value in sorted(literals):
        if normalize_literal(value) not in target_normalized:
            missing_values.append(value)
    if missing_values:
        add(
            issues,
            location,
            "REQ-FID-001",
            "FAIL",
            "NASA-SEH-REV2 Appendix C",
            "A source value or unit is not preserved in the requirement.",
            ", ".join(missing_values),
        )

    negative_source = bool(
        re.search(
            r"\b(?:shall not|must not|may not|prohibited|forbidden|do not|does not)\b",
            source_excerpt,
            flags=re.IGNORECASE,
        )
    )
    negative_target = (
        bool(re.search(r"\bshall not\b", text))
        if profile == "shall"
        else bool(re.search(r"\bMUST NOT\b", text))
    )
    if negative_source and not negative_target:
        add(
            issues,
            location,
            "REQ-FID-001",
            "FAIL",
            "NASA-SEH-REV2 Appendix C",
            "A source prohibition became a non-prohibitive requirement.",
        )


def check_requirement_fields(
    requirement: dict[str, Any],
    location: str,
    source_ids: set[str],
    lifecycle_profile: str,
    issues: list[Issue],
) -> None:
    requirement_type = text_value(requirement.get("type"))
    if requirement_type not in REQUIREMENT_TYPES:
        add(
            issues,
            location,
            "REQ-STRUCT-001",
            "FAIL",
            "requirements-schema.md",
            f"Unsupported requirement type: {requirement_type or '(missing)'}.",
        )
    if not text_value(requirement.get("level")):
        add(
            issues,
            location,
            "REQ-STRUCT-001",
            "REVIEW_REQUIRED",
            "NASA-SEH-REV2 Appendix C",
            "Requirement level is required.",
        )
    if not text_value(requirement.get("owner")):
        add(
            issues,
            location,
            "REQ-META-001",
            "REVIEW_REQUIRED",
            "NASA-SEH-REV2 section 4.2.4",
            "Requirement owner is required.",
        )
    if not text_value(requirement.get("rationale")):
        add(
            issues,
            location,
            "REQ-RAT-001",
            "REVIEW_REQUIRED",
            "NASA-SEH-REV2 Appendix C",
            "Rationale is required.",
        )
    if not isinstance(requirement.get("assumptions"), list):
        add(
            issues,
            location,
            "REQ-RAT-001",
            "REVIEW_REQUIRED",
            "NASA-SEH-REV2 Appendix C",
            "Assumptions must be an explicit list, including an empty list when none apply.",
        )
    if not isinstance(requirement.get("parents"), list):
        add(
            issues,
            location,
            "REQ-TRACE-001",
            "FAIL",
            "NASA-SEH-REV2 sections 4.3 and 6.2",
            "Parents must be an explicit list, including an empty list for a root requirement.",
        )
    if not isinstance(requirement.get("allocated_to"), list):
        add(
            issues,
            location,
            "REQ-META-001",
            "REVIEW_REQUIRED",
            "NASA-SEH-REV2 sections 4.2.4 and 4.3",
            "Allocation must be an explicit list.",
        )
    if requirement.get("derived") not in {True, False}:
        add(
            issues,
            location,
            "REQ-DERIVED-001",
            "FAIL",
            "NASA-SEH-REV2 section 4.3.2.2",
            "Derived must be an explicit Boolean.",
        )
    elif requirement.get("derived") and not text_value(
        requirement.get("derived_basis")
    ):
        add(
            issues,
            location,
            "REQ-DERIVED-001",
            "FAIL",
            "NASA-SEH-REV2 section 4.3.2.2",
            "A derived requirement needs its derivation basis.",
        )

    sources = string_list(requirement.get("source"))
    if not sources:
        add(
            issues,
            location,
            "REQ-SRC-001",
            "FAIL",
            "NASA-SEH-REV2 Appendix C",
            "Requirement source is required.",
        )
    unknown = sorted(set(sources) - source_ids)
    if unknown:
        add(
            issues,
            location,
            "REQ-SRC-001",
            "FAIL",
            "NASA-SEH-REV2 Appendix C",
            "Requirement references undefined sources.",
            ", ".join(unknown),
        )
    if lifecycle_profile in NASA_LIFECYCLE_PROFILES:
        missing_source_fields = [
            field
            for field in ("source_document", "source_paragraph")
            if not text_value(requirement.get(field))
        ]
        if missing_source_fields:
            add(
                issues,
                location,
                "REQ-META-001",
                "FAIL",
                "NASA-SEH-REV2 section 4.2.4; Appendix D",
                "NASA lifecycle trace metadata is incomplete.",
                ", ".join(missing_source_fields),
            )

    verification = requirement.get("verification")
    if not isinstance(verification, dict):
        add(
            issues,
            location,
            "VRF-PLAN-001",
            "FAIL",
            "NASA-SEH-REV2 sections 5.3 and 6.1; Appendix D",
            "Each binding product requirement needs a verification plan.",
        )
        add(
            issues,
            location,
            "REQ-VRF-002",
            "FAIL",
            "NASA-SEH-REV2 Appendix C",
            "Verification must define method, success criteria, and evidence.",
        )
        return
    add(
        issues,
        location,
        "VRF-PLAN-001",
        "PASS",
        "NASA-SEH-REV2 sections 5.3 and 6.1; Appendix D",
        "The requirement has a separate verification plan.",
    )
    method = text_value(verification.get("method"))
    criteria = text_value(verification.get("success_criteria"))
    evidence = verification.get("evidence")
    if method not in VERIFICATION_METHODS:
        add(
            issues,
            location,
            "REQ-VRF-002",
            "FAIL",
            "NASA-SEH-REV2 Appendix C",
            f"Verification method must be one of {sorted(VERIFICATION_METHODS)}.",
        )
    if not criteria:
        add(
            issues,
            location,
            "REQ-VRF-002",
            "FAIL",
            "NASA-SEH-REV2 Appendix C",
            "Objective verification success criteria are required.",
        )
    if not (
        text_value(evidence)
        or (isinstance(evidence, list) and any(text_value(item) for item in evidence))
    ):
        add(
            issues,
            location,
            "REQ-VRF-002",
            "REVIEW_REQUIRED",
            "NASA-SEH-REV2 Appendix C",
            "Planned or actual verification evidence is required.",
        )
    if lifecycle_profile in NASA_LIFECYCLE_PROFILES:
        required_text_fields = (
            "verification_level",
            "verification_lead",
            "facility",
            "phase",
            "performing_organization",
            "results_state",
            "configuration",
        )
        missing = [
            field
            for field in required_text_fields
            if not text_value(verification.get(field))
        ]
        boolean_fields = ("acceptance_requirement", "preflight_acceptance")
        missing.extend(
            field
            for field in boolean_fields
            if verification.get(field) not in {True, False}
        )
        if not isinstance(verification.get("discrepancies"), list):
            missing.append("discrepancies")
        if missing:
            add(
                issues,
                location,
                "VRF-PLAN-002",
                "FAIL",
                "NASA-SEH-REV2 section 5.3; Appendix D",
                "NASA verification-plan fields are incomplete.",
                ", ".join(missing),
            )
        if (
            text_value(verification.get("results_state"))
            and text_value(verification.get("results_state"))
            not in VERIFICATION_STATES
        ):
            add(
                issues,
                location,
                "VRF-RESULT-001",
                "FAIL",
                "NASA-SEH-REV2 section 5.3",
                f"Unsupported verification results state: {verification.get('results_state')}.",
            )

    if requirement_type == "performance" and not NUMBER_UNIT_RE.search(
        text_value(requirement.get("text"))
    ):
        add(
            issues,
            location,
            "REQ-VRF-001",
            "REVIEW_REQUIRED",
            "NASA-SEH-REV2 Appendix C",
            "A performance requirement needs a measurable value and applicable unit.",
        )


def check_requirements(
    document: dict[str, Any],
    profile: str,
    lifecycle_profile: str,
    source_ids: set[str],
    issues: list[Issue],
) -> list[dict[str, Any]]:
    requirements = document.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        add(
            issues,
            "document.requirements",
            "REQ-STRUCT-001",
            "REVIEW_REQUIRED",
            "requirements-schema.md",
            "At least one requirement is required.",
        )
        return []

    seen_ids: set[str] = set()
    terms = controlled_terms(document)
    protected = string_list(document.get("protected_values"))
    valid: list[dict[str, Any]] = []
    for index, requirement in enumerate(requirements):
        list_location = f"requirements[{index}]"
        if not isinstance(requirement, dict):
            add(
                issues,
                list_location,
                "REQ-STRUCT-001",
                "FAIL",
                "requirements-schema.md",
                "Requirement must be a mapping.",
            )
            continue
        requirement_id = text_value(requirement.get("id"))
        location = requirement_id or list_location
        if not requirement_id:
            add(
                issues,
                list_location,
                "REQ-SRC-001",
                "FAIL",
                "NASA-SEH-REV2 Appendix C",
                "Requirement identifier is required.",
            )
        elif requirement_id in seen_ids:
            add(
                issues,
                location,
                "REQ-SRC-001",
                "FAIL",
                "NASA-SEH-REV2 Appendix C",
                f"Duplicate requirement identifier: {requirement_id}.",
            )
        else:
            seen_ids.add(requirement_id)

        if not text_value(requirement.get("text")):
            add(
                issues,
                location,
                "REQ-CLR-001",
                "FAIL",
                "NASA-SEH-REV2 Appendix C",
                "Requirement text is required.",
            )
            continue
        check_requirement_fields(
            requirement, location, source_ids, lifecycle_profile, issues
        )
        check_normative_form(requirement, location, profile, issues)
        check_language_patterns(requirement, location, terms, issues)
        check_source_fidelity(requirement, location, protected, profile, issues)
        valid.append(requirement)

    external_parent_ids = {
        text_value(item.get("id"))
        for item in document.get("external_parent_requirements", [])
        if isinstance(item, dict) and text_value(item.get("id"))
    }
    known_parent_ids = seen_ids | external_parent_ids
    for requirement in valid:
        location = text_value(requirement.get("id")) or "requirements"
        parents = string_list(requirement.get("parents"))
        unknown_parents = sorted(set(parents) - known_parent_ids)
        if unknown_parents:
            add(
                issues,
                location,
                "REQ-TRACE-001",
                "FAIL",
                "NASA-SEH-REV2 sections 4.3 and 6.2",
                "Requirement references an undefined parent.",
                ", ".join(unknown_parents),
            )
        if text_value(requirement.get("id")) in parents:
            add(
                issues,
                location,
                "REQ-TRACE-001",
                "FAIL",
                "NASA-SEH-REV2 sections 4.3 and 6.2",
                "A requirement cannot be its own parent.",
            )
    return valid


def check_unresolved(document: dict[str, Any], issues: list[Issue]) -> None:
    records = document.get("unresolved", [])
    if records is None:
        records = []
    if not isinstance(records, list):
        add(
            issues,
            "document.unresolved",
            "REQ-TBD-001",
            "FAIL",
            "requirements-schema.md",
            "Unresolved records must be a list.",
        )
        return
    for index, record in enumerate(records):
        location = f"unresolved[{index}]"
        if not isinstance(record, dict):
            add(
                issues,
                location,
                "REQ-TBD-001",
                "FAIL",
                "requirements-schema.md",
                "Unresolved record must be a mapping.",
            )
            continue
        status = text_value(record.get("status"))
        common = ("id", "statement", "decision_needed")
        missing = [field for field in common if not text_value(record.get(field))]
        if status not in {"OPEN", "CLOSED"} or missing:
            add(
                issues,
                location,
                "REQ-TBD-001",
                "FAIL",
                "requirements-schema.md",
                "Unresolved record needs id, statement, decision_needed, and OPEN or CLOSED status.",
            )
        elif status == "OPEN":
            tracking = ("owner", "due_date")
            tracking_missing = [
                field for field in tracking if not text_value(record.get(field))
            ]
            add(
                issues,
                location,
                "REQ-TBD-001",
                "REVIEW_REQUIRED",
                "NASA-SEH-REV2 Appendix C",
                "An open decision blocks baseline release.",
                (
                    f"Missing tracking fields: {', '.join(tracking_missing)}"
                    if tracking_missing
                    else text_value(record.get("decision_needed"))
                ),
            )
        elif not text_value(record.get("resolution")):
            add(
                issues,
                location,
                "REQ-TBD-001",
                "REVIEW_REQUIRED",
                "requirements-schema.md",
                "A closed decision needs a recorded resolution.",
            )


def check_record_collection(
    document: dict[str, Any],
    field: str,
    required_fields: tuple[str, ...],
    check: str,
    basis: str,
    issues: list[Issue],
    *,
    allow_empty: bool = False,
) -> bool:
    records = document.get(field)
    if not isinstance(records, list) or (not records and not allow_empty):
        add(
            issues,
            f"document.{field}",
            check,
            "FAIL",
            basis,
            f"{field} must be a {'possibly empty ' if allow_empty else 'non-empty '}list.",
        )
        return False
    valid = True
    for index, record in enumerate(records):
        location = f"{field}[{index}]"
        if not isinstance(record, dict):
            add(
                issues,
                location,
                check,
                "FAIL",
                basis,
                f"Each {field} record must be a mapping.",
            )
            valid = False
            continue
        missing = [
            name
            for name in required_fields
            if not (
                text_value(record.get(name))
                or (
                    isinstance(record.get(name), list)
                    and bool(record.get(name))
                )
            )
        ]
        if missing:
            add(
                issues,
                location,
                check,
                "FAIL",
                basis,
                f"{field} record is incomplete.",
                ", ".join(missing),
            )
            valid = False
        else:
            add(
                issues,
                location,
                check,
                "PASS",
                basis,
                f"{field} record contains its required evidence fields.",
            )
    return valid


def check_lifecycle_context(
    document: dict[str, Any], lifecycle_profile: str, issues: list[Issue]
) -> bool:
    terms = document.get("controlled_terms", [])
    if not isinstance(terms, list):
        add(
            issues,
            "document.controlled_terms",
            "REQ-FORM-003",
            "FAIL",
            "NASA-SEH-REV2 Appendix C, C.2 Editorial Checklist, Product Requirement",
            "Controlled terms must be a list.",
        )
    else:
        for index, term in enumerate(terms):
            if not isinstance(term, dict):
                add(
                    issues,
                    f"controlled_terms[{index}]",
                    "REQ-FORM-003",
                    "FAIL",
                    "NASA-SEH-REV2 Appendix C, C.2 Editorial Checklist, Product Requirement",
                    "Controlled term must be a mapping.",
                )
                continue
            missing = [
                field
                for field in ("term", "definition", "source")
                if not text_value(term.get(field))
            ]
            if term.get("approved") is not True:
                missing.append("approved=true")
            if missing:
                add(
                    issues,
                    f"controlled_terms[{index}]",
                    "REQ-FORM-003",
                    "REVIEW_REQUIRED",
                    "NASA-SEH-REV2 Appendix C, C.2 Editorial Checklist, Product Requirement",
                    "A controlled term is not fully approved and sourced.",
                    ", ".join(missing),
                )

    if lifecycle_profile not in NASA_LIFECYCLE_PROFILES:
        return True

    valid = True
    stakeholder = document.get("stakeholder_context")
    stakeholder_fields = (
        "stakeholders",
        "decision_authority",
        "needs",
        "goals",
        "objectives",
        "conops_references",
        "measures_of_effectiveness",
        "constraints",
        "assumptions",
        "operational_environments",
        "commitments",
        "expectation_baseline",
    )
    if not isinstance(stakeholder, dict):
        add(
            issues,
            "document.stakeholder_context",
            "STK-001",
            "FAIL",
            "NASA-SEH-REV2 section 4.1; Appendix S",
            "NASA lifecycle profiles require stakeholder context.",
        )
        valid = False
    else:
        missing = [
            field
            for field in stakeholder_fields
            if field not in stakeholder
            or (
                not text_value(stakeholder.get(field))
                and not isinstance(stakeholder.get(field), list)
            )
        ]
        if missing:
            add(
                issues,
                "document.stakeholder_context",
                "STK-001",
                "FAIL",
                "NASA-SEH-REV2 section 4.1; Appendix S",
                "Stakeholder context is incomplete.",
                ", ".join(missing),
            )
            valid = False
        else:
            add(
                issues,
                "document.stakeholder_context",
                "STK-001",
                "PASS",
                "NASA-SEH-REV2 section 4.1; Appendix S",
                "Stakeholder context fields are present.",
            )

    decomposition = document.get("decomposition")
    decomposition_fields = (
        "functions",
        "inputs",
        "outputs",
        "sequences",
        "failure_modes",
        "consequences",
        "allocations",
        "derived_requirement_decisions",
    )
    if not isinstance(decomposition, dict) or any(
        field not in decomposition for field in decomposition_fields
    ):
        add(
            issues,
            "document.decomposition",
            "DECOMP-001",
            "FAIL",
            "NASA-SEH-REV2 section 4.3; Appendix F",
            "Logical decomposition must explicitly assess every required field.",
        )
        valid = False

    assessments = document.get("completeness_assessment")
    assessed: set[str] = set()
    if not isinstance(assessments, list):
        add(
            issues,
            "document.completeness_assessment",
            "REQ-COMPLETE-001",
            "FAIL",
            "NASA-SEH-REV2 Appendix C, completeness",
            "Completeness assessment must be a list.",
        )
        valid = False
    else:
        for index, assessment in enumerate(assessments):
            location = f"completeness_assessment[{index}]"
            if not isinstance(assessment, dict):
                add(
                    issues,
                    location,
                    "REQ-COMPLETE-001",
                    "FAIL",
                    "NASA-SEH-REV2 Appendix C, completeness",
                    "Completeness assessment must be a mapping.",
                )
                valid = False
                continue
            category = text_value(assessment.get("category"))
            result = text_value(assessment.get("result"))
            evidence = text_value(assessment.get("evidence"))
            if (
                category not in COMPLETENESS_CATEGORIES
                or category in assessed
                or result not in RESULTS
                or not evidence
            ):
                add(
                    issues,
                    location,
                    "REQ-COMPLETE-001",
                    "FAIL",
                    "NASA-SEH-REV2 Appendix C, completeness",
                    "Completeness assessment has an invalid category, result, duplicate, or missing evidence.",
                )
                valid = False
                continue
            assessed.add(category)
            add(
                issues,
                location,
                "REQ-COMPLETE-001",
                result,
                "NASA-SEH-REV2 Appendix C, completeness",
                f"Completeness category assessed: {category}.",
                evidence,
            )
        missing_categories = sorted(COMPLETENESS_CATEGORIES - assessed)
        if missing_categories:
            add(
                issues,
                "document.completeness_assessment",
                "REQ-COMPLETE-001",
                "FAIL",
                "NASA-SEH-REV2 Appendix C, completeness",
                "Completeness categories are missing.",
                ", ".join(missing_categories),
            )
            valid = False

    valid &= check_record_collection(
        document,
        "validation_plan",
        (
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
        ),
        "VAL-PLAN-002",
        "NASA-SEH-REV2 section 5.4; Appendix E",
        issues,
    )
    validation_records = document.get("validation_plan", [])
    add(
        issues,
        "document.validation_plan",
        "VAL-PLAN-001",
        (
            "PASS"
            if isinstance(validation_records, list) and validation_records
            else "FAIL"
        ),
        "NASA-SEH-REV2 sections 2.4 and 5.4; Appendix E",
        (
            "Product validation is recorded separately from requirement verification."
            if isinstance(validation_records, list) and validation_records
            else "A separate product validation plan is required."
        ),
    )
    if isinstance(validation_records, list):
        for index, record in enumerate(validation_records):
            if not isinstance(record, dict):
                continue
            method = text_value(record.get("method"))
            state = text_value(record.get("results_state"))
            if method not in VERIFICATION_METHODS or state not in VERIFICATION_STATES:
                add(
                    issues,
                    f"validation_plan[{index}]",
                    "VAL-PLAN-002",
                    "FAIL",
                    "NASA-SEH-REV2 section 5.4; Appendix E",
                    "Validation method or results state is invalid.",
                    f"method={method or '(missing)'} state={state or '(missing)'}",
                )
                valid = False
    valid &= check_record_collection(
        document,
        "interfaces",
        (
            "id",
            "kind",
            "owners",
            "controlling_source",
            "units",
            "tolerances",
            "compatibility_evidence",
            "change_authority",
        ),
        "IFACE-001",
        "NASA-SEH-REV2 section 6.3; Appendix L",
        issues,
        allow_empty=True,
    )
    interfaces = document.get("interfaces", [])
    if isinstance(interfaces, list):
        for index, record in enumerate(interfaces):
            if (
                isinstance(record, dict)
                and text_value(record.get("kind")) not in {"internal", "external"}
            ):
                add(
                    issues,
                    f"interfaces[{index}]",
                    "IFACE-001",
                    "FAIL",
                    "NASA-SEH-REV2 section 6.3; Appendix L",
                    "Interface kind must be internal or external.",
                )
                valid = False
    valid &= check_record_collection(
        document,
        "baselines",
        ("id", "kind", "version", "date", "authority", "content_digest"),
        "BASELINE-001",
        "NASA-SEH-REV2 sections 4.1, 4.2, 6.2, and 6.5",
        issues,
    )
    baselines = document.get("baselines", [])
    if isinstance(baselines, list):
        baseline_kinds = {
            text_value(record.get("kind"))
            for record in baselines
            if isinstance(record, dict)
        }
        required_baseline_kinds = {
            "stakeholder_expectations",
            "technical_requirements",
        }
        if not required_baseline_kinds <= baseline_kinds:
            add(
                issues,
                "document.baselines",
                "BASELINE-001",
                "FAIL",
                "NASA-SEH-REV2 sections 4.1, 4.2, and 6.5",
                "NASA lifecycle release requires stakeholder-expectations and technical-requirements baselines.",
                ", ".join(sorted(required_baseline_kinds - baseline_kinds)),
            )
            valid = False
    valid &= check_record_collection(
        document,
        "change_records",
        ("id", "status", "authority", "reason", "impacts"),
        "CHANGE-001",
        "NASA-SEH-REV2 section 6.2.2.2",
        issues,
        allow_empty=True,
    )
    change_impact_fields = {
        "cost",
        "schedule",
        "architecture",
        "design",
        "interfaces",
        "conops",
        "parent_requirements",
        "child_requirements",
        "safety",
        "risk",
    }
    changes = document.get("change_records", [])
    if isinstance(changes, list):
        for index, record in enumerate(changes):
            if not isinstance(record, dict):
                continue
            impacts = record.get("impacts")
            if not isinstance(impacts, dict) or not change_impact_fields <= set(
                impacts
            ):
                add(
                    issues,
                    f"change_records[{index}]",
                    "CHANGE-001",
                    "FAIL",
                    "NASA-SEH-REV2 section 6.2.2.2",
                    "Requirement change impact analysis is incomplete.",
                    ", ".join(
                        sorted(
                            change_impact_fields
                            - (set(impacts) if isinstance(impacts, dict) else set())
                        )
                    ),
                )
                valid = False

    data_management = document.get("data_management")
    data_fields = (
        "repository",
        "version_convention",
        "decision_records",
        "evidence_records",
    )
    if not isinstance(data_management, dict) or any(
        not text_value(data_management.get(field)) for field in data_fields
    ):
        add(
            issues,
            "document.data_management",
            "DATA-001",
            "FAIL",
            "NASA-SEH-REV2 section 6.6",
            "Technical data management evidence is incomplete.",
        )
        valid = False
    return bool(valid)


def check_npr_authority(
    document: dict[str, Any], lifecycle_profile: str, issues: list[Issue]
) -> bool:
    if lifecycle_profile != "nasa-npr-7123.1d":
        return True
    evidence = document.get("npr_process_evidence")
    if not isinstance(evidence, dict):
        add(
            issues,
            "document.npr_process_evidence",
            "NPR-AUTH-001",
            "FAIL",
            "NPR-7123.1D-C2 sections 1 and 2; Appendix D",
            "The NPR lifecycle profile requires NASA process evidence.",
        )
        return False
    required_text = (
        "applicability",
        "complete_compliance_matrix",
        "compliance_matrix_digest",
        "semp_or_equivalent",
        "semp_approval",
        "eta_authority",
    )
    missing = [
        field for field in required_text if not text_value(evidence.get(field))
    ]
    for field in ("tailoring_records", "customization_records", "eta_decisions"):
        if not isinstance(evidence.get(field), list):
            missing.append(field)

    authority = evidence.get("current_authority_record")
    if not isinstance(authority, dict):
        missing.append("current_authority_record")
        authority = {}
    if text_value(authority.get("reference_id")) != "NPR-7123.1D-C2":
        missing.append("canonical reference_id")
    if text_value(authority.get("directive_identifier")) != (
        "NPR 7123.1D Updated with Change 2"
    ):
        missing.append("canonical directive_identifier")
    if authority.get("result") != "PASS":
        missing.append("passing authority result")
    authority_url = text_value(authority.get("authority_url"))
    if authority_url != NPR_AUTHORITY_URL:
        missing.append("canonical authority_url")
    observed_markers = set(string_list(authority.get("observed_markers")))
    if observed_markers != NPR_AUTHORITY_MARKERS:
        missing.append("complete observed authority markers")
    if authority.get("missing_markers") != []:
        missing.append("empty missing_markers")
    if authority.get("expired") is not False:
        missing.append("unexpired authority record")
    if not SHA256_RE.fullmatch(
        text_value(authority.get("response_sha256"))
    ):
        missing.append("response_sha256")
    manifest_digest = text_value(authority.get("manifest_sha256"))
    local_manifest = (
        Path(__file__).resolve().parents[1]
        / "references"
        / "reference-manifest.json"
    )
    try:
        expected_manifest_digest = hashlib.sha256(
            local_manifest.read_bytes()
        ).hexdigest()
    except OSError:
        expected_manifest_digest = ""
    if manifest_digest != expected_manifest_digest:
        missing.append("current local manifest_sha256")
    try:
        checked_at = datetime.fromisoformat(
            text_value(authority.get("checked_at")).replace("Z", "+00:00")
        )
        if checked_at.tzinfo is None:
            raise ValueError
        now = datetime.now(timezone.utc)
        checked_date = checked_at.astimezone(timezone.utc).date()
        if checked_date != now.date():
            missing.append("fresh checked_at")
        if checked_at.astimezone(timezone.utc) > now:
            missing.append("non-future checked_at")
    except ValueError:
        missing.append("valid timezone-aware checked_at")
    if missing:
        add(
            issues,
            "document.npr_process_evidence",
            "NPR-AUTH-002",
            "FAIL",
            "NPR-7123.1D-C2 sections 1.3, 2.1, 2.2, and Appendix D",
            "NPR process evidence is incomplete or does not identify the current directive.",
            ", ".join(missing),
        )
        return False
    add(
        issues,
        "document.npr_process_evidence",
        "NPR-AUTH-002",
        "PASS",
        "NPR-7123.1D-C2 sections 1.3, 2.1, 2.2, and Appendix D",
        "The canonical, current NODIS authority record and declared NPR process-evidence fields are present. Authorized reviewers remain responsible for applicability and sufficiency.",
        (
            f"response_sha256={authority['response_sha256']}; "
            f"manifest_sha256={authority['manifest_sha256']}"
        ),
    )
    return True


def check_reviews(
    document: dict[str, Any],
    digest: str,
    lifecycle_profile: str,
    issues: list[Issue],
) -> bool:
    reviews = document.get("reviews", [])
    if reviews is None:
        reviews = []
    if not isinstance(reviews, list):
        add(
            issues,
            "document.reviews",
            "REVIEW-001",
            "FAIL",
            "requirements-schema.md",
            "Reviews must be a list.",
        )
        return False

    valid_dimensions: set[str] = set()
    for index, review in enumerate(reviews):
        location = f"reviews[{index}]"
        if not isinstance(review, dict):
            add(
                issues,
                location,
                "REVIEW-001",
                "FAIL",
                "requirements-schema.md",
                "Review must be a mapping.",
            )
            continue
        dimension = text_value(review.get("dimension"))
        result = text_value(review.get("result"))
        reviewer = text_value(review.get("reviewer_id"))
        role = text_value(review.get("role"))
        review_date = text_value(review.get("date"))
        evidence = text_value(review.get("evidence"))
        review_digest = text_value(review.get("content_digest"))
        if dimension not in REVIEW_DIMENSIONS:
            add(
                issues,
                location,
                "REVIEW-001",
                "FAIL",
                "requirements-schema.md",
                f"Unsupported review dimension: {dimension or '(missing)'}.",
            )
            continue
        if not reviewer or not role or not review_date or not evidence:
            add(
                issues,
                location,
                "REVIEW-001",
                "FAIL",
                "requirements-schema.md",
                "Review needs reviewer_id, role, date, and evidence.",
            )
            continue
        try:
            date.fromisoformat(review_date)
        except ValueError:
            add(
                issues,
                location,
                "REVIEW-001",
                "FAIL",
                "requirements-schema.md",
                "Review date must use ISO YYYY-MM-DD format.",
            )
            continue
        if review_digest != digest:
            add(
                issues,
                location,
                "REVIEW-001",
                "FAIL",
                "requirements-schema.md",
                "Review does not match the current content digest.",
                f"review={review_digest or '(missing)'} current={digest}",
            )
            continue
        if result == "FAIL":
            add(
                issues,
                location,
                "REVIEW-001",
                "FAIL",
                "requirements-schema.md",
                f"Human review failed for {dimension}.",
                evidence,
            )
        elif result == "REVIEW_REQUIRED":
            add(
                issues,
                location,
                "REVIEW-001",
                "REVIEW_REQUIRED",
                "requirements-schema.md",
                f"Human review remains open for {dimension}.",
                evidence,
            )
        elif result == "PASS":
            if dimension in valid_dimensions:
                add(
                    issues,
                    location,
                    "REVIEW-001",
                    "FAIL",
                    "requirements-schema.md",
                    f"Duplicate passing review dimension: {dimension}.",
                )
            else:
                valid_dimensions.add(dimension)
                add(
                    issues,
                    location,
                    "REVIEW-001",
                    "PASS",
                    "requirements-schema.md",
                    f"Human review passed for {dimension}.",
                    evidence,
                )
        else:
            add(
                issues,
                location,
                "REVIEW-001",
                "FAIL",
                "requirements-schema.md",
                "Review result must be PASS, FAIL, or REVIEW_REQUIRED.",
            )

    required_dimensions = set(CORE_REVIEW_DIMENSIONS)
    if lifecycle_profile in NASA_LIFECYCLE_PROFILES:
        required_dimensions |= NASA_REVIEW_DIMENSIONS
    missing = sorted(required_dimensions - valid_dimensions)
    if missing:
        add(
            issues,
            "document.reviews",
            "REVIEW-001",
            "REVIEW_REQUIRED",
            "requirements-schema.md",
            "Required human semantic reviews are incomplete.",
            ", ".join(missing),
        )
        return False
    return True


def check_approval(
    document: dict[str, Any], digest: str, issues: list[Issue]
) -> bool:
    declared_authority = document.get("approval_authority")
    authorized: set[tuple[str, str]] = set()
    if not isinstance(declared_authority, list) or not declared_authority:
        add(
            issues,
            "document.approval_authority",
            "APPROVAL-001",
            "REVIEW_REQUIRED",
            "requirements-schema.md",
            "A declared approval authority is required.",
        )
    else:
        for index, authority in enumerate(declared_authority):
            location = f"approval_authority[{index}]"
            if not isinstance(authority, dict):
                add(
                    issues,
                    location,
                    "APPROVAL-001",
                    "FAIL",
                    "requirements-schema.md",
                    "Approval authority must be a mapping.",
                )
                continue
            approver_id = text_value(authority.get("approver_id"))
            role = text_value(authority.get("role"))
            authority_source = text_value(authority.get("authority_source"))
            if not approver_id or not role or not authority_source:
                add(
                    issues,
                    location,
                    "APPROVAL-001",
                    "FAIL",
                    "requirements-schema.md",
                    "Approval authority needs approver_id, role, and authority_source.",
                )
                continue
            authorized.add((approver_id, role))

    approvals = document.get("approvals", [])
    if approvals is None:
        approvals = []
    if not isinstance(approvals, list):
        add(
            issues,
            "document.approvals",
            "APPROVAL-001",
            "FAIL",
            "requirements-schema.md",
            "Approvals must be a list.",
        )
        return False
    approved = False
    for index, approval in enumerate(approvals):
        location = f"approvals[{index}]"
        if not isinstance(approval, dict):
            add(
                issues,
                location,
                "APPROVAL-001",
                "FAIL",
                "requirements-schema.md",
                "Approval must be a mapping.",
            )
            continue
        fields = ("approver_id", "role", "date", "result", "evidence", "content_digest")
        missing = [field for field in fields if not text_value(approval.get(field))]
        if missing:
            add(
                issues,
                location,
                "APPROVAL-001",
                "FAIL",
                "requirements-schema.md",
                "Approval record is incomplete.",
                ", ".join(missing),
            )
            continue
        try:
            date.fromisoformat(text_value(approval.get("date")))
        except ValueError:
            add(
                issues,
                location,
                "APPROVAL-001",
                "FAIL",
                "requirements-schema.md",
                "Approval date must use ISO YYYY-MM-DD format.",
            )
            continue
        if text_value(approval.get("content_digest")) != digest:
            add(
                issues,
                location,
                "APPROVAL-001",
                "FAIL",
                "requirements-schema.md",
                "Approval does not match the current content digest.",
            )
            continue
        result = text_value(approval.get("result"))
        if result == "REJECTED":
            add(
                issues,
                location,
                "APPROVAL-001",
                "FAIL",
                "requirements-schema.md",
                "The baseline approver rejected the artifact.",
                text_value(approval.get("evidence")),
            )
        elif result == "PENDING":
            add(
                issues,
                location,
                "APPROVAL-001",
                "NOT_APPLICABLE",
                "requirements-schema.md",
                "Baseline approval is pending.",
            )
        elif result == "APPROVED":
            identity = (
                text_value(approval.get("approver_id")),
                text_value(approval.get("role")),
            )
            if identity not in authorized:
                add(
                    issues,
                    location,
                    "APPROVAL-001",
                    "FAIL",
                    "requirements-schema.md",
                    "The approver and role are not in the declared approval authority.",
                )
            elif text_value(approval.get("role")) != "baseline_approver":
                add(
                    issues,
                    location,
                    "APPROVAL-001",
                    "FAIL",
                    "requirements-schema.md",
                    "An approved baseline record requires the baseline_approver role.",
                )
            elif approved:
                add(
                    issues,
                    location,
                    "APPROVAL-001",
                    "FAIL",
                    "requirements-schema.md",
                    "Multiple current baseline approvals are ambiguous.",
                )
            else:
                approved = True
                add(
                    issues,
                    location,
                    "APPROVAL-001",
                    "PASS",
                    "requirements-schema.md",
                    "Authorized baseline approval matches the current content digest.",
                )
        else:
            add(
                issues,
                location,
                "APPROVAL-001",
                "FAIL",
                "requirements-schema.md",
                "Approval result must be APPROVED, REJECTED, or PENDING.",
            )
    return approved


def derive_status(issues: list[Issue], approval_valid: bool) -> str:
    if any(issue.result == "FAIL" for issue in issues):
        return STATUS_FAILED
    if any(issue.result == "REVIEW_REQUIRED" for issue in issues):
        return STATUS_DRAFT
    if approval_valid:
        return STATUS_BASELINED
    return STATUS_READY


def make_matrix(
    requirements: list[dict[str, Any]], profile: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for requirement in requirements:
        text = text_value(requirement.get("text"))
        keywords = normative_matches(text, profile)
        if profile == "shall" and not keywords:
            continue
        verification = requirement.get("verification")
        verification = verification if isinstance(verification, dict) else {}
        rows.append(
            {
                "requirement_id": text_value(requirement.get("id")),
                "requirement": text,
                "sources": string_list(requirement.get("source")),
                "source_document": text_value(
                    requirement.get("source_document")
                ),
                "source_paragraph": text_value(
                    requirement.get("source_paragraph")
                ),
                "verification_method": text_value(verification.get("method")),
                "success_criteria": text_value(
                    verification.get("success_criteria")
                ),
                "verification_level": text_value(
                    verification.get("verification_level")
                ),
                "verification_lead": text_value(
                    verification.get("verification_lead")
                ),
                "facility": text_value(verification.get("facility")),
                "phase": text_value(verification.get("phase")),
                "acceptance_requirement": verification.get(
                    "acceptance_requirement", ""
                ),
                "preflight_acceptance": verification.get(
                    "preflight_acceptance", ""
                ),
                "performing_organization": text_value(
                    verification.get("performing_organization")
                ),
                "results_state": text_value(
                    verification.get("results_state")
                ),
                "evidence": verification.get("evidence", ""),
                "configuration": text_value(
                    verification.get("configuration")
                ),
                "discrepancies": verification.get("discrepancies", []),
            }
        )
    return rows


def make_validation_matrix(document: dict[str, Any]) -> list[dict[str, Any]]:
    records = document.get("validation_plan")
    if not isinstance(records, list):
        return []
    fields = (
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
    )
    return [
        {field: record.get(field, "") for field in fields}
        for record in records
        if isinstance(record, dict)
    ]


def evaluate(document: dict[str, Any]) -> dict[str, Any]:
    issues: list[Issue] = []
    digest = content_digest(document)
    check_required_context(document, issues)
    source_ids, _ = check_sources(document, issues)
    check_authority_gap_wording(document, issues)
    language_profile, lifecycle_profile = check_profile(document, issues)
    requirements = check_requirements(
        document, language_profile, lifecycle_profile, source_ids, issues
    )
    check_unresolved(document, issues)
    lifecycle_valid = check_lifecycle_context(
        document, lifecycle_profile, issues
    )
    npr_authority_valid = check_npr_authority(
        document, lifecycle_profile, issues
    )
    check_reviews(document, digest, lifecycle_profile, issues)
    approval_valid = check_approval(document, digest, issues)
    status = derive_status(issues, approval_valid)
    release_permitted = status == STATUS_BASELINED
    state_codes = {
        STATUS_DRAFT: "DRAFT",
        STATUS_FAILED: "CHECK_FAILED",
        STATUS_READY: "BASELINE_REVIEW",
        STATUS_BASELINED: "BASELINED",
    }
    return {
        "status": status,
        "state_code": state_codes[status],
        "operation_succeeded": True,
        "release_permitted": release_permitted,
        "content_digest": digest,
        "summary": {
            result: sum(1 for issue in issues if issue.result == result)
            for result in ("PASS", "FAIL", "REVIEW_REQUIRED", "NOT_APPLICABLE")
        },
        "release_gates": {
            "deterministic_checks": not any(
                issue.result == "FAIL" for issue in issues
            ),
            "human_semantic_reviews": not any(
                issue.check == "REVIEW-001"
                and issue.result in {"FAIL", "REVIEW_REQUIRED"}
                for issue in issues
            ),
            "lifecycle_evidence": lifecycle_valid,
            "npr_authority_evidence": npr_authority_valid,
            "authorized_baseline_approval": approval_valid,
            "clean_output_permitted": release_permitted,
        },
        "issues": [asdict(issue) for issue in issues],
        "traceability_matrix": make_matrix(requirements, language_profile),
        "validation_matrix": make_validation_matrix(document),
        "claim_boundary": (
            "Artifact readiness only. This report is not NASA certification or organizational process compliance."
        ),
        "limitations": [
            "Pattern checks do not prove semantic correctness, completeness, feasibility, safety, or conflict freedom.",
            "Human reviewers must compare the requirements with authoritative sources.",
            "NASA process compliance requires authorized applicability, tailoring, SEMP, ETA, and complete compliance-matrix decisions outside this checker.",
        ],
    }


def markdown_escape(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Requirements artifact report",
        "",
        f"Status: `{report['status']}`",
        "",
        f"State code: `{report['state_code']}`",
        "",
        f"Operation succeeded: `{str(report['operation_succeeded']).lower()}`",
        "",
        f"Release permitted: `{str(report['release_permitted']).lower()}`",
        "",
        f"Content digest: `{report['content_digest']}`",
        "",
        f"Claim boundary: {report['claim_boundary']}",
        "",
        "## Release gates",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    for gate, result in report["release_gates"].items():
        lines.append(f"| {gate} | {'PASS' if result else 'OPEN'} |")
    lines.extend(
        [
            "",
            "## Findings",
            "",
            "| Location | Check | Result | Basis | Message | Evidence |",
            "|---|---|---|---|---|---|",
        ]
    )
    for issue in report["issues"]:
        lines.append(
            "| "
            + " | ".join(
                markdown_escape(issue[key])
                for key in (
                    "location",
                    "check",
                    "result",
                    "basis",
                    "message",
                    "evidence",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Traceability and verification matrix",
            "",
            "| Requirement | Source document | Paragraph | Method | Criteria | Level | Lead | Facility | Phase | Acceptance | Preflight | Organization | State | Evidence |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for row in report["traceability_matrix"]:
        lines.append(
            "| "
            + " | ".join(
                markdown_escape(row[key])
                for key in (
                    "requirement_id",
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
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Product validation matrix",
            "",
            "| Product | Activity | Objective | Method | Facility | Phase | Organization | State | Stakeholder trace | ConOps trace | MOE trace | Environment | Users | Evidence |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for row in report["validation_matrix"]:
        lines.append(
            "| "
            + " | ".join(
                markdown_escape(row[key])
                for key in (
                    "product_id",
                    "activity",
                    "objective",
                    "method",
                    "facility",
                    "phase",
                    "performing_organization",
                    "results_state",
                    "stakeholder_expectations",
                    "conops_references",
                    "moe_references",
                    "intended_environment",
                    "representative_users",
                    "evidence",
                )
            )
            + " |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines) + "\n"


def template(
    language_profile: str, lifecycle_profile: str = "general"
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "title": "Requirements title",
        "language_profile": language_profile,
        "lifecycle_profile": lifecycle_profile,
        "objective": "",
        "system_boundary": "",
        "intended_readers": [],
        "lifecycle_scope": {
            "product_layer": "",
            "lifecycle_phase": "",
            "included_processes": [],
            "excluded_processes": [],
        },
        "source_authorities": [
            {
                "id": "SRC-001",
                "title": "Authoritative source",
                "revision": "",
                "location": "",
                "precedence": 1,
                "digest_unavailable_reason": "",
            }
        ],
        "controlled_terms": [],
        "protected_values": [],
        "approval_authority": [
            {
                "approver_id": "owner-1",
                "role": "baseline_approver",
                "authority_source": "Project governance record",
            }
        ],
        "requirements": [],
        "unresolved": [],
        "reviews": [],
        "approvals": [],
    }
    if language_profile == "bcp14":
        document["normative_language_notice"] = (
            "The uppercase normative keywords use BCP 14 as defined by "
            "RFC 2119 and clarified by RFC 8174."
        )
    if lifecycle_profile in NASA_LIFECYCLE_PROFILES:
        document.update(
            {
                "external_parent_requirements": [],
                "stakeholder_context": {
                    "stakeholders": [],
                    "decision_authority": "",
                    "needs": [],
                    "goals": [],
                    "objectives": [],
                    "conops_references": [],
                    "measures_of_effectiveness": [],
                    "constraints": [],
                    "assumptions": [],
                    "operational_environments": [],
                    "commitments": [],
                    "expectation_baseline": "",
                },
                "decomposition": {
                    "functions": [],
                    "inputs": [],
                    "outputs": [],
                    "sequences": [],
                    "failure_modes": [],
                    "consequences": [],
                    "allocations": [],
                    "derived_requirement_decisions": [],
                },
                "completeness_assessment": [
                    {"category": category, "result": "REVIEW_REQUIRED", "evidence": ""}
                    for category in sorted(COMPLETENESS_CATEGORIES)
                ],
                "validation_plan": [],
                "interfaces": [],
                "baselines": [],
                "change_records": [],
                "data_management": {
                    "repository": "",
                    "version_convention": "",
                    "decision_records": "",
                    "evidence_records": "",
                },
            }
        )
    if lifecycle_profile == "nasa-npr-7123.1d":
        document["npr_process_evidence"] = {
            "current_authority_record": {
                "reference_id": "NPR-7123.1D-C2",
                "directive_identifier": "NPR 7123.1D Updated with Change 2",
                "result": "",
                "checked_at": "",
                "authority_url": "",
                "observed_markers": [],
                "missing_markers": [],
                "expired": "",
                "response_sha256": "",
                "manifest_sha256": "",
            },
            "applicability": "",
            "complete_compliance_matrix": "",
            "compliance_matrix_digest": "",
            "semp_or_equivalent": "",
            "semp_approval": "",
            "tailoring_records": [],
            "customization_records": [],
            "eta_authority": "",
            "eta_decisions": [],
        }
    return document


def write_clean_output(
    document: dict[str, Any], path: Path, overwrite: bool
) -> None:
    requirements = document.get("requirements", [])
    lines = [
        f"{text_value(item.get('id'))} {text_value(item.get('text'))}"
        for item in requirements
        if isinstance(item, dict)
    ]
    write_output(path, "\n".join(lines) + "\n", overwrite)


def write_output(path: Path, text: str, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise ValueError(
            f"Output already exists: {path}. Use --overwrite to replace it."
        )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
            temporary_path = Path(stream.name)
        if overwrite:
            os.replace(temporary_path, path)
        else:
            try:
                os.link(temporary_path, path)
            except FileExistsError as exc:
                raise ValueError(
                    f"Output already exists: {path}. Use --overwrite to replace it."
                ) from exc
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError(f"Cannot write output {path}: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check structured requirements and derive their release status."
    )
    parser.add_argument("input", nargs="?", type=Path, help="YAML or JSON input")
    parser.add_argument(
        "--format", choices=("json", "markdown", "both"), default="both"
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output file. By default, outputs are immutable.",
    )
    parser.add_argument(
        "--emit-template", choices=("shall", "bcp14"), metavar="LANGUAGE_PROFILE"
    )
    parser.add_argument(
        "--lifecycle-profile",
        choices=tuple(sorted(LIFECYCLE_PROFILES)),
        default="general",
        help="Lifecycle profile for a generated template.",
    )
    parser.add_argument("--clean-output", type=Path)
    parser.add_argument(
        "--require-baseline",
        action="store_true",
        help="Return failure unless authorized baseline approval is current.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.emit_template:
        rendered = yaml.safe_dump(
            template(args.emit_template, args.lifecycle_profile),
            sort_keys=False,
            allow_unicode=True,
        )
        if args.output:
            try:
                write_output(args.output, rendered, args.overwrite)
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
        else:
            sys.stdout.write(rendered)
        return 0
    if not args.input:
        print("error: input is required unless --emit-template is used", file=sys.stderr)
        return 2
    if args.format == "both" and not args.output_dir:
        print("error: --output-dir is required with --format both", file=sys.stderr)
        return 2
    if args.format != "both" and args.output_dir and args.output:
        print("error: use --output or --output-dir, not both", file=sys.stderr)
        return 2

    try:
        document = load_document(args.input)
        report = evaluate(document)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    json_text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    markdown_text = render_markdown(report)
    digest_prefix = report["content_digest"].removeprefix("sha256:")[:12]
    try:
        if args.format == "both":
            json_path = args.output_dir / f"requirements-report-{digest_prefix}.json"
            markdown_path = args.output_dir / f"requirements-report-{digest_prefix}.md"
            existing = [
                path for path in (json_path, markdown_path)
                if path.exists() and not args.overwrite
            ]
            if existing:
                raise ValueError(
                    "Output already exists: "
                    + ", ".join(str(path) for path in existing)
                    + ". Use --overwrite to replace it."
                )
            created: list[Path] = []
            try:
                write_output(json_path, json_text, args.overwrite)
                if not args.overwrite:
                    created.append(json_path)
                write_output(markdown_path, markdown_text, args.overwrite)
                if not args.overwrite:
                    created.append(markdown_path)
            except ValueError:
                for path in created:
                    path.unlink(missing_ok=True)
                raise
            print(report["status"])
            print(report["content_digest"])
        else:
            rendered = json_text if args.format == "json" else markdown_text
            if args.output:
                write_output(args.output, rendered, args.overwrite)
            else:
                sys.stdout.write(rendered)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.clean_output:
        if report["status"] != STATUS_BASELINED:
            print(
                "error: clean output requires current authorized baseline approval",
                file=sys.stderr,
            )
            return 1
        try:
            write_clean_output(document, args.clean_output, args.overwrite)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if report["status"] in {STATUS_DRAFT, STATUS_FAILED}:
        return 1
    if args.require_baseline and report["status"] != STATUS_BASELINED:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
