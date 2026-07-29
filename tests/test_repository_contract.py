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

    def test_license_and_alignment_claims_are_truthful(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
        alignment = (ROOT / "docs" / "alignment.md").read_text(encoding="utf-8")
        self.assertFalse((ROOT / "LICENSE").exists())
        self.assertIn("currently grants no software license", readme)
        self.assertIn("not NASA-approved", " ".join(notice.split()))
        self.assertEqual(alignment.count("| Contract item |"), 1)


if __name__ == "__main__":
    unittest.main()
