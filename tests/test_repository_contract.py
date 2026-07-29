from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTests(unittest.TestCase):
    def test_required_public_surfaces_exist(self) -> None:
        required = {
            "README.md",
            "SECURITY.md",
            "NOTICE.md",
            "CONTRIBUTING.md",
            "AGENTS.md",
            "requirements.txt",
            "docs/agent-flow.svg",
            "docs/alignment.md",
            ".github/workflows/ci.yml",
        }
        self.assertEqual(
            [],
            sorted(path for path in required if not (ROOT / path).is_file()),
        )

    def test_readme_relative_links_resolve(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        links = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", readme)
        relative = [
            target.split("#", 1)[0]
            for target in links
            if target
            and not target.startswith(("http://", "https://", "mailto:"))
        ]
        self.assertTrue(relative)
        self.assertEqual(
            [],
            sorted(target for target in relative if not (ROOT / target).exists()),
        )

    def test_workflow_uses_restricted_public_ci(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        uses = re.findall(r"^\s*uses:\s*([^#\s]+)", workflow, flags=re.MULTILINE)
        self.assertTrue(uses)
        for action in uses:
            self.assertRegex(action, r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertIn("github.event.repository.private == false", workflow)
        self.assertIn("vars.PUBLIC_CI_ENABLED == 'true'", workflow)
        self.assertNotIn("pull_request_target", workflow)
        self.assertNotIn("self-hosted", workflow)
        self.assertNotIn("actions/cache", workflow)
        self.assertNotIn("upload-artifact", workflow)
        self.assertNotIn("cache: false", workflow)

    def test_license_and_alignment_claims_are_truthful(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
        alignment = (ROOT / "docs" / "alignment.md").read_text(encoding="utf-8")
        self.assertFalse((ROOT / "LICENSE").exists())
        self.assertIn("currently grants no software license", readme)
        self.assertIn("not NASA-approved", " ".join(notice.split()))
        self.assertEqual(alignment.count("| Contract item |"), 1)
        skill = (ROOT / "write-verifiable-requirements" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        rules = (
            ROOT
            / "write-verifiable-requirements"
            / "references"
            / "requirements-rules.yaml"
        ).read_text(encoding="utf-8")
        schema = (
            ROOT
            / "write-verifiable-requirements"
            / "references"
            / "requirements-schema.md"
        ).read_text(encoding="utf-8")
        self.assertIn("<SKILL_ROOT>/scripts/check_requirements.py", skill)
        self.assertIn("Do not silently combine source clauses.", skill)
        self.assertIn("source-transformation mapping", skill)
        self.assertIn("REQ-FID-002", rules)
        self.assertIn("REQ-CONFLICT-001", rules)
        self.assertIn("REQ-VRF-003", rules)
        self.assertIn("source_transformations", schema)
        self.assertIn("introduced_constraints", schema)
        self.assertIn("state_code", skill)
        self.assertIn("release_permitted", skill)
        self.assertIn("digest-qualified names", skill)
        self.assertIn("current_authority_record", schema)
        self.assertIn("digest_unavailable_reason", schema)
        agent_yaml = (
            ROOT
            / "write-verifiable-requirements"
            / "agents"
            / "openai.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: true", agent_yaml)


if __name__ == "__main__":
    unittest.main()
