#!/usr/bin/env python3
"""Verify and repair the pinned NASA references used by this skill.

Local verification is the normal path. Network access occurs only for an
explicit repair or current-authority check. A new digest is never accepted
automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import ssl
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
)


EXIT_OK = 0
EXIT_INPUT_ERROR = 1
EXIT_BLOCKED = 2
MAX_REDIRECTS = 3
MAX_STATUS_BYTES = 2 * 1024 * 1024
DOWNLOAD_SLACK_BYTES = 1


class ReferenceError(ValueError):
    """An invalid manifest, path, download, or authority response."""


@dataclass(frozen=True)
class ReferenceResult:
    reference_id: str
    path: str
    result: str
    message: str
    size_bytes: int | None = None
    sha256: str | None = None


class RestrictedRedirectHandler(HTTPRedirectHandler):
    """Permit a bounded number of HTTPS redirects to approved hosts."""

    def __init__(self, allowed_hosts: set[str]) -> None:
        super().__init__()
        self.allowed_hosts = allowed_hosts
        self.redirect_count = 0

    def redirect_request(
        self,
        req: Request,
        fp: BinaryIO,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        self.redirect_count += 1
        if self.redirect_count > MAX_REDIRECTS:
            raise ReferenceError(f"Redirect limit exceeded ({MAX_REDIRECTS}).")
        validate_https_url(newurl, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def manifest_path() -> Path:
    return skill_root() / "references" / "reference-manifest.json"


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReferenceError(f"Cannot load reference manifest {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ReferenceError("The reference manifest root must be an object.")
    if data.get("schema_version") != "1.0.0":
        raise ReferenceError("Unsupported reference manifest schema version.")
    if data.get("skill_name") != "write-verifiable-requirements":
        raise ReferenceError("The reference manifest has the wrong skill name.")
    documents = data.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ReferenceError("The reference manifest must contain documents.")

    required = {
        "id",
        "title",
        "identifier",
        "authority_type",
        "local_path",
        "size_bytes",
        "sha256",
        "pdf_signature",
        "official_landing_page",
        "canonical_download_url",
        "allowed_hosts",
        "distribution_basis",
    }
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            raise ReferenceError(f"documents[{index}] must be an object.")
        missing = sorted(required - document.keys())
        if missing:
            raise ReferenceError(
                f"documents[{index}] is missing fields: {', '.join(missing)}"
            )
        reference_id = document["id"]
        local_path = document["local_path"]
        if not isinstance(reference_id, str) or not reference_id:
            raise ReferenceError(f"documents[{index}].id must be a nonempty string.")
        if reference_id in seen_ids:
            raise ReferenceError(f"Duplicate reference id: {reference_id}")
        seen_ids.add(reference_id)
        if (
            not isinstance(local_path, str)
            or not local_path
            or Path(local_path).name != local_path
        ):
            raise ReferenceError(
                f"documents[{index}].local_path must be one filename."
            )
        if local_path in seen_paths:
            raise ReferenceError(f"Duplicate reference path: {local_path}")
        seen_paths.add(local_path)
        if not isinstance(document["size_bytes"], int) or document["size_bytes"] <= 0:
            raise ReferenceError(
                f"documents[{index}].size_bytes must be a positive integer."
            )
        digest = document["sha256"]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ReferenceError(
                f"documents[{index}].sha256 must be lowercase SHA-256."
            )
        allowed_hosts = document["allowed_hosts"]
        if (
            not isinstance(allowed_hosts, list)
            or not allowed_hosts
            or not all(
                isinstance(host, str) and host and host == host.lower()
                for host in allowed_hosts
            )
        ):
            raise ReferenceError(
                f"documents[{index}].allowed_hosts must contain lowercase hosts."
            )
        validate_https_url(document["official_landing_page"], set(allowed_hosts))
        validate_https_url(document["canonical_download_url"], set(allowed_hosts))
    return data


def validate_https_url(url: Any, allowed_hosts: set[str]) -> None:
    if not isinstance(url, str) or not url:
        raise ReferenceError("Reference URL must be a nonempty string.")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ReferenceError(f"Only HTTPS URLs are permitted: {url}")
    if parsed.username or parsed.password or parsed.port:
        raise ReferenceError(f"Credentials and explicit ports are prohibited: {url}")
    host = (parsed.hostname or "").lower()
    if host not in allowed_hosts:
        raise ReferenceError(f"URL host is not approved: {host or '(missing)'}")


def ensure_no_symlink(path: Path, boundary: Path) -> None:
    boundary = boundary.absolute()
    candidate = path.absolute()
    try:
        relative = candidate.relative_to(boundary)
    except ValueError as exc:
        raise ReferenceError(f"Path is outside the approved directory: {candidate}") from exc
    for component in reversed((boundary, *boundary.parents)):
        if component.is_symlink():
            raise ReferenceError(f"Symlink path is prohibited: {component}")
    current = boundary
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ReferenceError(f"Symlink path is prohibited: {current}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_reference(
    reference: dict[str, Any], references_dir: Path
) -> ReferenceResult:
    target = references_dir / reference["local_path"]
    try:
        ensure_no_symlink(target, references_dir)
        if not target.exists():
            return ReferenceResult(
                reference["id"],
                str(target),
                "FAIL",
                "Reference file is missing.",
            )
        if not target.is_file():
            return ReferenceResult(
                reference["id"],
                str(target),
                "FAIL",
                "Reference path is not a regular file.",
            )
        size = target.stat().st_size
        if size != reference["size_bytes"]:
            return ReferenceResult(
                reference["id"],
                str(target),
                "FAIL",
                f"Expected {reference['size_bytes']} bytes; found {size}.",
                size_bytes=size,
            )
        with target.open("rb") as stream:
            signature = stream.read(len(reference["pdf_signature"])).decode(
                "ascii", errors="replace"
            )
        if signature != reference["pdf_signature"]:
            return ReferenceResult(
                reference["id"],
                str(target),
                "FAIL",
                "File does not have the expected PDF signature.",
                size_bytes=size,
            )
        digest = sha256_file(target)
        if digest != reference["sha256"]:
            return ReferenceResult(
                reference["id"],
                str(target),
                "FAIL",
                "SHA-256 does not match the reviewed reference.",
                size_bytes=size,
                sha256=digest,
            )
        return ReferenceResult(
            reference["id"],
            str(target),
            "PASS",
            "Reference identity and integrity are verified.",
            size_bytes=size,
            sha256=digest,
        )
    except (OSError, ReferenceError) as exc:
        return ReferenceResult(
            reference["id"],
            str(target),
            "FAIL",
            str(exc),
        )


def verify_all(
    manifest: dict[str, Any], references_dir: Path
) -> list[ReferenceResult]:
    return [
        verify_reference(reference, references_dir)
        for reference in manifest["documents"]
    ]


def opener_for(allowed_hosts: set[str]) -> Any:
    context = ssl.create_default_context()
    redirect_handler = RestrictedRedirectHandler(allowed_hosts)
    return build_opener(HTTPSHandler(context=context), redirect_handler)


def open_approved_url(
    url: str, allowed_hosts: set[str], timeout_seconds: float
) -> Any:
    validate_https_url(url, allowed_hosts)
    request = Request(
        url,
        headers={
            "User-Agent": "write-verifiable-requirements-reference-manager/1.0",
            "Accept": "application/pdf,text/html;q=0.9",
        },
    )
    try:
        response = opener_for(allowed_hosts).open(request, timeout=timeout_seconds)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ReferenceError(f"Reference request failed: {exc}") from exc
    validate_https_url(response.geturl(), allowed_hosts)
    return response


def download_approved_reference(
    reference: dict[str, Any],
    destination: Path,
    timeout_seconds: float,
) -> None:
    allowed_hosts = set(reference["allowed_hosts"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    ensure_no_symlink(destination, destination.parent)
    if destination.exists():
        raise ReferenceError(f"Refusing to overwrite download target: {destination}")

    temporary_path: Path | None = None
    try:
        with open_approved_url(
            reference["canonical_download_url"],
            allowed_hosts,
            timeout_seconds,
        ) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"application/pdf", "application/octet-stream"}:
                raise ReferenceError(
                    f"Expected PDF content type; received {content_type}."
                )
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared_size = int(content_length)
                except ValueError as exc:
                    raise ReferenceError("Invalid Content-Length header.") from exc
                if declared_size != reference["size_bytes"]:
                    raise ReferenceError(
                        "Download size header does not match the approved manifest."
                    )

            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{reference['id']}.",
                suffix=".partial",
                dir=destination.parent,
            )
            temporary_path = Path(temporary_name)
            digest = hashlib.sha256()
            byte_count = 0
            with os.fdopen(descriptor, "wb") as stream:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    byte_count += len(chunk)
                    if byte_count > reference["size_bytes"] + DOWNLOAD_SLACK_BYTES:
                        raise ReferenceError("Download exceeded the approved size.")
                    digest.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())

        if byte_count != reference["size_bytes"]:
            raise ReferenceError(
                f"Expected {reference['size_bytes']} bytes; downloaded {byte_count}."
            )
        with temporary_path.open("rb") as stream:
            signature = stream.read(len(reference["pdf_signature"])).decode(
                "ascii", errors="replace"
            )
        if signature != reference["pdf_signature"]:
            raise ReferenceError("Downloaded file does not have a PDF signature.")
        downloaded_digest = digest.hexdigest()
        if downloaded_digest != reference["sha256"]:
            raise ReferenceError(
                "Downloaded SHA-256 is not an approved manifest digest."
            )
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def materialize_reference(source: Path, destination: Path, references_dir: Path) -> None:
    ensure_no_symlink(destination, references_dir)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".stage",
        dir=references_dir,
    )
    temporary_path = Path(temporary_name)
    try:
        with source.open("rb") as input_stream, os.fdopen(
            descriptor, "wb"
        ) as output_stream:
            shutil.copyfileobj(input_stream, output_stream)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def default_cache_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    base = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return base / "cache" / "write-verifiable-requirements" / "references"


def repair_references(
    manifest: dict[str, Any],
    references_dir: Path,
    cache_dir: Path,
    selected_ids: set[str],
    timeout_seconds: float,
) -> list[ReferenceResult]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    if cache_dir.is_symlink():
        raise ReferenceError(f"Cache directory must not be a symlink: {cache_dir}")
    references_dir.mkdir(parents=True, exist_ok=True)
    if references_dir.is_symlink():
        raise ReferenceError(
            f"References directory must not be a symlink: {references_dir}"
        )

    known_ids = {document["id"] for document in manifest["documents"]}
    unknown = selected_ids - known_ids
    if unknown:
        raise ReferenceError(f"Unknown reference ids: {', '.join(sorted(unknown))}")

    for reference in manifest["documents"]:
        if reference["id"] not in selected_ids:
            continue
        current = verify_reference(reference, references_dir)
        if current.result == "PASS":
            continue
        cache_path = cache_dir / f"{reference['sha256']}.pdf"
        ensure_no_symlink(cache_path, cache_dir)
        cache_reference = dict(reference)
        cache_reference["local_path"] = cache_path.name
        cached = verify_reference(cache_reference, cache_dir)
        if cached.result != "PASS":
            cache_path.unlink(missing_ok=True)
            download_approved_reference(reference, cache_path, timeout_seconds)
            cached = verify_reference(cache_reference, cache_dir)
            if cached.result != "PASS":
                cache_path.unlink(missing_ok=True)
                raise ReferenceError(
                    f"Downloaded cache failed verification: {cached.message}"
                )
        materialize_reference(
            cache_path,
            references_dir / reference["local_path"],
            references_dir,
        )
    return verify_all(manifest, references_dir)


def check_current_authority(
    reference: dict[str, Any], timeout_seconds: float
) -> dict[str, Any]:
    markers = reference.get("expected_status_markers")
    if not isinstance(markers, list) or not markers:
        raise ReferenceError(
            f"{reference['id']} does not define a current-authority check."
        )
    allowed_hosts = set(reference["allowed_hosts"])
    with open_approved_url(
        reference["official_landing_page"], allowed_hosts, timeout_seconds
    ) as response:
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "text/plain"}:
            raise ReferenceError(
                f"Expected an HTML authority record; received {content_type}."
            )
        payload = response.read(MAX_STATUS_BYTES + 1)
    if len(payload) > MAX_STATUS_BYTES:
        raise ReferenceError("Authority response exceeded the size limit.")
    text = payload.decode("utf-8", errors="replace")
    missing = [marker for marker in markers if marker not in text]
    observed = [marker for marker in markers if marker in text]
    expiration = reference.get("expiration_date")
    expired = False
    if isinstance(expiration, str):
        try:
            expired = date.today() > date.fromisoformat(expiration)
        except ValueError as exc:
            raise ReferenceError("Manifest expiration_date is not ISO format.") from exc
    result = "PASS" if not missing and not expired else "FAIL"
    return {
        "reference_id": reference["id"],
        "directive_identifier": reference["identifier"],
        "result": result,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "authority_url": reference["official_landing_page"],
        "observed_markers": observed,
        "missing_markers": missing,
        "expired": expired,
        "response_sha256": hashlib.sha256(payload).hexdigest(),
        "message": (
            "Current NODIS identity, change level, and date markers are present."
            if result == "PASS"
            else "Current authority could not be confirmed."
        ),
    }


def report_payload(
    action: str,
    results: list[ReferenceResult],
    next_action: str | None = None,
) -> dict[str, Any]:
    passed = all(result.result == "PASS" for result in results)
    return {
        "skill": "write-verifiable-requirements",
        "action": action,
        "result": "PASS" if passed else "FAIL",
        "references": [asdict(result) for result in results],
        "next_action": None if passed else next_action,
    }


def render_human(payload: dict[str, Any]) -> str:
    lines = [
        f"Reference status: {payload['result']}",
        f"Action: {payload['action']}",
    ]
    for result in payload.get("references", []):
        lines.append(
            f"- {result['reference_id']}: {result['result']} — {result['message']}"
        )
    authority = payload.get("authority")
    if authority:
        lines.append(
            f"- {authority['reference_id']}: {authority['result']} — "
            f"{authority['message']}"
        )
    if payload.get("next_action"):
        lines.append(f"Next action: {payload['next_action']}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify and repair the skill's pinned NASA references."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=manifest_path(),
        help="Reference manifest path.",
    )
    parser.add_argument(
        "--references-dir",
        type=Path,
        default=skill_root() / "references",
        help="Directory that contains the pinned references.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Verify local reference identity.")
    subparsers.add_parser("verify", help="Alias for status.")

    repair = subparsers.add_parser(
        "repair", help="Restore approved reference bytes from cache or NASA."
    )
    repair.add_argument(
        "--id",
        action="append",
        dest="reference_ids",
        help="Reference id to repair. Repeat as needed. Default: all.",
    )
    repair.add_argument(
        "--cache-dir",
        type=Path,
        default=default_cache_dir(),
        help="Content-addressed verified cache directory.",
    )
    repair.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="Per-request timeout.",
    )

    current = subparsers.add_parser(
        "check-current",
        help="Confirm live authority markers for a directive.",
    )
    current.add_argument(
        "--id",
        default="NPR-7123.1D-C2",
        dest="reference_id",
        help="Directive reference id.",
    )
    current.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="Request timeout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        references_dir = args.references_dir.absolute()
        if args.command in {"status", "verify"}:
            results = verify_all(manifest, references_dir)
            payload = report_payload(
                args.command,
                results,
                (
                    f"Run: {sys.executable} "
                    f"{Path(__file__).resolve()} repair"
                ),
            )
        elif args.command == "repair":
            selected = set(args.reference_ids or [])
            if not selected:
                selected = {document["id"] for document in manifest["documents"]}
            results = repair_references(
                manifest,
                references_dir,
                args.cache_dir.absolute(),
                selected,
                args.timeout_seconds,
            )
            payload = report_payload(
                "repair",
                results,
                "Inspect the failure and rerun the explicit repair command.",
            )
        else:
            reference = next(
                (
                    document
                    for document in manifest["documents"]
                    if document["id"] == args.reference_id
                ),
                None,
            )
            if reference is None:
                raise ReferenceError(f"Unknown reference id: {args.reference_id}")
            results = verify_all(manifest, references_dir)
            authority = check_current_authority(
                reference, args.timeout_seconds
            )
            authority["manifest_sha256"] = hashlib.sha256(
                args.manifest.read_bytes()
            ).hexdigest()
            payload = report_payload(
                "check-current",
                results,
                "Repair local references before an authority check.",
            )
            payload["authority"] = authority
            if authority["result"] != "PASS":
                payload["result"] = "FAIL"
                payload["next_action"] = (
                    "Review the NODIS record. Do not make a current-NPR claim."
                )
        print(
            json.dumps(payload, indent=2, ensure_ascii=False)
            if args.json
            else render_human(payload)
        )
        return EXIT_OK if payload["result"] == "PASS" else EXIT_BLOCKED
    except ReferenceError as exc:
        error = {
            "skill": "write-verifiable-requirements",
            "action": getattr(args, "command", "unknown"),
            "result": "ERROR",
            "message": str(exc),
        }
        print(
            json.dumps(error, indent=2)
            if args.json
            else f"Reference error: {exc}",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
