#!/usr/bin/env python3
"""Transactionally install the bundled Codex skill after local verification."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Any


EXIT_OK = 0
EXIT_INPUT_ERROR = 1
EXIT_BLOCKED = 2
SKILL_NAME = "write-verifiable-requirements"


class InstallError(ValueError):
    """An invalid source, destination, or installation state."""


@dataclass(frozen=True)
class InstallResult:
    result: str
    action: str
    source: str
    destination: str
    source_digest: str | None
    installed_digest: str | None
    message: str
    next_action: str | None = None


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def source_skill_root() -> Path:
    return repository_root() / SKILL_NAME


def default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def load_reference_module(skill_dir: Path) -> ModuleType:
    module_path = skill_dir / "scripts" / "manage_references.py"
    spec = importlib.util.spec_from_file_location(
        "write_verifiable_requirements_manage_references", module_path
    )
    if spec is None or spec.loader is None:
        raise InstallError(f"Cannot load reference manager: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def reject_symlinks(root: Path) -> None:
    if root.is_symlink():
        raise InstallError(f"Skill root must not be a symlink: {root}")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise InstallError(f"Skill source contains a symlink: {path}")


def validate_skill_source(skill_dir: Path) -> dict[str, Any]:
    required = [
        "SKILL.md",
        "agents/openai.yaml",
        "references/reference-manifest.json",
        "scripts/check_requirements.py",
        "scripts/manage_references.py",
    ]
    if not skill_dir.is_dir():
        raise InstallError(f"Skill source is not a directory: {skill_dir}")
    reject_symlinks(skill_dir)
    for relative in required:
        if not (skill_dir / relative).is_file():
            raise InstallError(f"Required skill file is missing: {relative}")

    skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    if not skill_text.startswith("---\n"):
        raise InstallError("SKILL.md does not start with YAML frontmatter.")
    frontmatter_end = skill_text.find("\n---\n", 4)
    if frontmatter_end < 0:
        raise InstallError("SKILL.md frontmatter is not closed.")
    frontmatter = skill_text[4:frontmatter_end]
    if f"name: {SKILL_NAME}" not in frontmatter.splitlines():
        raise InstallError("SKILL.md has the wrong skill name.")

    manager = load_reference_module(skill_dir)
    manifest_file = skill_dir / "references" / "reference-manifest.json"
    manifest = manager.load_manifest(manifest_file)
    results = manager.verify_all(manifest, skill_dir / "references")
    failures = [result for result in results if result.result != "PASS"]
    if failures:
        messages = "; ".join(
            f"{failure.reference_id}: {failure.message}" for failure in failures
        )
        raise InstallError(f"Bundled references failed verification: {messages}")
    return manifest


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise InstallError(f"Cannot hash a symlinked tree: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        size = path.stat().st_size
        digest.update(size.to_bytes(8, "big"))
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def ensure_install_boundary(codex_home: Path) -> Path:
    codex_home = codex_home.absolute()
    for component in reversed((codex_home, *codex_home.parents)):
        if component.is_symlink():
            raise InstallError(f"Install path must not use a symlink: {component}")
    codex_home.mkdir(parents=True, exist_ok=True)
    skills_dir = codex_home / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    if skills_dir.is_symlink():
        raise InstallError(f"Skills directory must not be a symlink: {skills_dir}")
    return skills_dir


def acquire_lock(lock_path: Path) -> int:
    try:
        descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as exc:
        raise InstallError(
            f"Another installation may be active: {lock_path}. "
            "Remove this file only after you confirm that no installer is running."
        ) from exc
    os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
    os.fsync(descriptor)
    return descriptor


def install_skill(
    source: Path,
    codex_home: Path,
    dry_run: bool = False,
) -> InstallResult:
    validate_skill_source(source)
    source_digest = tree_digest(source)
    skills_dir = ensure_install_boundary(codex_home)
    destination = skills_dir / SKILL_NAME
    lock_path = skills_dir / f".{SKILL_NAME}.install.lock"
    if destination.is_symlink():
        raise InstallError(f"Installed skill path must not be a symlink: {destination}")

    installed_digest = tree_digest(destination) if destination.is_dir() else None
    if installed_digest == source_digest:
        return InstallResult(
            "PASS",
            "no-op",
            str(source),
            str(destination),
            source_digest,
            installed_digest,
            "The installed skill already matches the verified source.",
        )
    if dry_run:
        return InstallResult(
            "PASS",
            "dry-run",
            str(source),
            str(destination),
            source_digest,
            installed_digest,
            "The source is valid. Installation would replace the destination.",
        )

    lock_descriptor = acquire_lock(lock_path)
    token = uuid.uuid4().hex
    staging = skills_dir / f".{SKILL_NAME}.stage-{token}"
    backup = skills_dir / f".{SKILL_NAME}.backup-{token}"
    replaced_existing = False
    try:
        shutil.copytree(source, staging, copy_function=shutil.copy2)
        validate_skill_source(staging)
        staged_digest = tree_digest(staging)
        if staged_digest != source_digest:
            raise InstallError("The staged skill differs from the verified source.")

        if destination.exists():
            os.replace(destination, backup)
            replaced_existing = True
        try:
            os.replace(staging, destination)
            validate_skill_source(destination)
            final_digest = tree_digest(destination)
            if final_digest != source_digest:
                raise InstallError(
                    "The installed skill differs from the verified source."
                )
        except Exception:
            if destination.exists():
                shutil.rmtree(destination)
            if replaced_existing and backup.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        return InstallResult(
            "PASS",
            "installed",
            str(source),
            str(destination),
            source_digest,
            source_digest,
            "The skill was verified and installed transactionally.",
        )
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup.exists() and not destination.exists():
            os.replace(backup, destination)
        os.close(lock_descriptor)
        lock_path.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify and transactionally install write-verifiable-requirements."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=source_skill_root(),
        help="Skill source directory.",
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=default_codex_home(),
        help="Codex home directory. Default: CODEX_HOME or ~/.codex.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify without changing the installation.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = install_skill(
            args.source.absolute(),
            args.codex_home.absolute(),
            args.dry_run,
        )
        payload = asdict(result)
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"Installation status: {result.result}")
            print(f"Action: {result.action}")
            print(result.message)
            print(f"Destination: {result.destination}")
        return EXIT_OK
    except (InstallError, OSError, UnicodeError) as exc:
        payload = {
            "result": "FAIL",
            "action": "blocked",
            "source": str(args.source),
            "destination": str(args.codex_home / "skills" / SKILL_NAME),
            "message": str(exc),
            "next_action": (
                "Correct the reported source or destination problem, then rerun "
                "this command."
            ),
        }
        if args.json:
            print(json.dumps(payload, indent=2), file=sys.stderr)
        else:
            print(f"Installation blocked: {exc}", file=sys.stderr)
        return EXIT_BLOCKED


if __name__ == "__main__":
    raise SystemExit(main())
