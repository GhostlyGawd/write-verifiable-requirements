from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "write-verifiable-requirements"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MANAGER = load_module(
    "test_manage_references",
    SKILL / "scripts" / "manage_references.py",
)
INSTALLER = load_module(
    "test_install_skill",
    ROOT / "scripts" / "install_skill.py",
)


class FakeHeaders:
    def __init__(self, content_type: str, content_length: int | None) -> None:
        self.content_type = content_type
        self.content_length = content_length

    def get_content_type(self) -> str:
        return self.content_type

    def get(self, name: str, default=None):
        if name == "Content-Length" and self.content_length is not None:
            return str(self.content_length)
        return default


class FakeResponse:
    def __init__(
        self,
        payload: bytes,
        url: str,
        content_type: str = "application/pdf",
        content_length: int | None = None,
    ) -> None:
        self.stream = io.BytesIO(payload)
        self.url = url
        self.headers = FakeHeaders(
            content_type,
            len(payload) if content_length is None else content_length,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)

    def geturl(self) -> str:
        return self.url


class ReferenceManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest_path = SKILL / "references" / "reference-manifest.json"
        self.manifest = MANAGER.load_manifest(self.manifest_path)

    def test_bundled_references_pass(self) -> None:
        results = MANAGER.verify_all(self.manifest, SKILL / "references")
        self.assertTrue(results)
        self.assertTrue(all(result.result == "PASS" for result in results))

    def test_manifest_and_coverage_hashes_agree(self) -> None:
        coverage = (
            SKILL / "references" / "nasa-reference-coverage.yaml"
        ).read_text(encoding="utf-8")
        rules = (SKILL / "references" / "requirements-rules.yaml").read_text(
            encoding="utf-8"
        )
        for document in self.manifest["documents"]:
            self.assertIn(document["id"], coverage)
            self.assertIn(document["sha256"], coverage)
            self.assertIn(document["id"], rules)

    def test_missing_reference_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = MANAGER.verify_reference(
                self.manifest["documents"][0], Path(directory)
            )
        self.assertEqual(result.result, "FAIL")
        self.assertIn("missing", result.message)

    def test_corrupt_reference_fails(self) -> None:
        reference = self.manifest["documents"][0]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / reference["local_path"]
            target.write_bytes(b"%PDF-" + b"x" * (reference["size_bytes"] - 5))
            result = MANAGER.verify_reference(reference, Path(directory))
        self.assertEqual(result.result, "FAIL")
        self.assertIn("SHA-256", result.message)

    def test_symlink_reference_fails(self) -> None:
        reference = self.manifest["documents"][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = SKILL / "references" / reference["local_path"]
            target = root / reference["local_path"]
            try:
                target.symlink_to(source)
            except OSError:
                self.skipTest("Symlink creation is unavailable.")
            result = MANAGER.verify_reference(reference, root)
        self.assertEqual(result.result, "FAIL")
        self.assertIn("Symlink", result.message)

    def test_repair_uses_verified_cache_without_network(self) -> None:
        reference = self.manifest["documents"][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            references_dir = root / "references"
            cache_dir = root / "cache"
            references_dir.mkdir()
            cache_dir.mkdir()
            for document in self.manifest["documents"]:
                shutil.copy2(
                    SKILL / "references" / document["local_path"],
                    references_dir / document["local_path"],
                )
            (references_dir / reference["local_path"]).write_bytes(b"corrupt")
            cache_path = cache_dir / f"{reference['sha256']}.pdf"
            shutil.copy2(
                SKILL / "references" / reference["local_path"],
                cache_path,
            )
            with mock.patch.object(
                MANAGER,
                "download_approved_reference",
                side_effect=AssertionError("network must not be used"),
            ):
                results = MANAGER.repair_references(
                    self.manifest,
                    references_dir,
                    cache_dir,
                    {reference["id"]},
                    1.0,
                )
        self.assertTrue(all(result.result == "PASS" for result in results))

    def test_download_accepts_only_approved_bytes(self) -> None:
        reference = self.manifest["documents"][0]
        payload = (
            SKILL / "references" / reference["local_path"]
        ).read_bytes()
        response = FakeResponse(payload, reference["canonical_download_url"])
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "approved.pdf"
            with mock.patch.object(
                MANAGER, "open_approved_url", return_value=response
            ):
                MANAGER.download_approved_reference(
                    reference, destination, 1.0
                )
            self.assertEqual(
                hashlib.sha256(destination.read_bytes()).hexdigest(),
                reference["sha256"],
            )

    def test_download_rejects_truncated_content_and_cleans_partial(self) -> None:
        reference = self.manifest["documents"][0]
        payload = (
            SKILL / "references" / reference["local_path"]
        ).read_bytes()[:-1]
        response = FakeResponse(
            payload,
            reference["canonical_download_url"],
            content_length=reference["size_bytes"],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "truncated.pdf"
            with mock.patch.object(
                MANAGER, "open_approved_url", return_value=response
            ):
                with self.assertRaises(MANAGER.ReferenceError):
                    MANAGER.download_approved_reference(
                        reference, destination, 1.0
                    )
            self.assertFalse(destination.exists())
            self.assertEqual(
                [path for path in root.iterdir() if path.suffix == ".partial"],
                [],
            )

    def test_download_rejects_wrong_content_type(self) -> None:
        reference = self.manifest["documents"][0]
        payload = b"<html>not a PDF</html>"
        response = FakeResponse(
            payload,
            reference["canonical_download_url"],
            content_type="text/html",
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "wrong.pdf"
            with mock.patch.object(
                MANAGER, "open_approved_url", return_value=response
            ):
                with self.assertRaises(MANAGER.ReferenceError):
                    MANAGER.download_approved_reference(
                        reference, destination, 1.0
                    )
            self.assertFalse(destination.exists())

    def test_unapproved_redirect_host_is_rejected(self) -> None:
        handler = MANAGER.RestrictedRedirectHandler({"www.nasa.gov"})
        request = MANAGER.Request("https://www.nasa.gov/reference.pdf")
        with self.assertRaises(MANAGER.ReferenceError):
            handler.redirect_request(
                request,
                io.BytesIO(),
                302,
                "Found",
                {},
                "https://example.com/reference.pdf",
            )

    def test_current_authority_requires_every_marker(self) -> None:
        reference = self.manifest["documents"][1]
        payload = "\n".join(reference["expected_status_markers"]).encode()
        passing = FakeResponse(
            payload,
            reference["official_landing_page"],
            content_type="text/html",
        )
        with mock.patch.object(
            MANAGER, "open_approved_url", return_value=passing
        ):
            result = MANAGER.check_current_authority(reference, 1.0)
        self.assertEqual(result["result"], "PASS")

        failing = FakeResponse(
            b"NPR 7123.1D",
            reference["official_landing_page"],
            content_type="text/html",
        )
        with mock.patch.object(
            MANAGER, "open_approved_url", return_value=failing
        ):
            result = MANAGER.check_current_authority(reference, 1.0)
        self.assertEqual(result["result"], "FAIL")
        self.assertTrue(result["missing_markers"])


class InstallerTests(unittest.TestCase):
    def test_missing_yaml_dependency_blocks_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(
                INSTALLER,
                "package_version",
                side_effect=INSTALLER.PackageNotFoundError,
            ):
                with self.assertRaises(INSTALLER.InstallError):
                    INSTALLER.install_skill(SKILL, Path(directory) / "codex")

    def test_fresh_install_and_idempotent_reinstall(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            codex_home = Path(directory) / "codex"
            first = INSTALLER.install_skill(SKILL, codex_home)
            second = INSTALLER.install_skill(SKILL, codex_home)
            installed = codex_home / "skills" / INSTALLER.SKILL_NAME
            self.assertEqual(first.action, "installed")
            self.assertEqual(second.action, "no-op")
            self.assertEqual(
                INSTALLER.tree_digest(installed),
                INSTALLER.tree_digest(SKILL),
            )

    def test_dry_run_does_not_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            codex_home = Path(directory) / "codex"
            result = INSTALLER.install_skill(SKILL, codex_home, dry_run=True)
            self.assertEqual(result.action, "dry-run")
            self.assertFalse(
                (codex_home / "skills" / INSTALLER.SKILL_NAME).exists()
            )

    def test_corrupt_source_blocks_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            shutil.copytree(SKILL, source)
            manifest = json.loads(
                (source / "references" / "reference-manifest.json").read_text()
            )
            target = source / "references" / manifest["documents"][0]["local_path"]
            target.write_bytes(b"corrupt")
            with self.assertRaises(INSTALLER.InstallError):
                INSTALLER.install_skill(source, root / "codex")

    def test_existing_lock_blocks_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            codex_home = Path(directory) / "codex"
            skills = codex_home / "skills"
            skills.mkdir(parents=True)
            lock = skills / f".{INSTALLER.SKILL_NAME}.install.lock"
            lock.write_text("pid=1\n", encoding="ascii")
            with self.assertRaises(INSTALLER.InstallError):
                INSTALLER.install_skill(SKILL, codex_home)
            self.assertTrue(lock.exists())

    def test_failed_replacement_restores_last_valid_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex_home = root / "codex"
            INSTALLER.install_skill(SKILL, codex_home)
            destination = codex_home / "skills" / INSTALLER.SKILL_NAME
            original_digest = INSTALLER.tree_digest(destination)

            source = root / "updated-source"
            shutil.copytree(SKILL, source)
            (source / "PUBLICATION_TEST_MARKER").write_text(
                "new source\n", encoding="utf-8"
            )
            original_validate = INSTALLER.validate_skill_source

            def fail_only_for_final(path: Path):
                if path == destination:
                    raise INSTALLER.InstallError("simulated final validation failure")
                return original_validate(path)

            with mock.patch.object(
                INSTALLER,
                "validate_skill_source",
                side_effect=fail_only_for_final,
            ):
                with self.assertRaises(INSTALLER.InstallError):
                    INSTALLER.install_skill(source, codex_home)
            self.assertTrue(destination.exists())
            self.assertEqual(
                INSTALLER.tree_digest(destination),
                original_digest,
            )


if __name__ == "__main__":
    unittest.main()
