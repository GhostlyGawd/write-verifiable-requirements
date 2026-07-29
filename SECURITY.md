# Security

## Trust boundary

The skill reads technical source data supplied for the current task. It does
not require credentials, production access, or a persistent service.

Normal execution uses local files and does not access the network.

Two explicit operations can access NASA hosts:

- `manage_references.py check-current` reads the NODIS authority record.
- `manage_references.py repair` restores only bytes already approved in the
  reference manifest.

The repair operation requires HTTPS, restricts hosts and redirects, bounds
response size and time, checks the PDF signature, verifies exact size and
SHA-256, uses temporary files, and installs atomically. Downloaded files are
never executed.

## Failure behavior

The skill fails closed for an affected NASA profile when:

- a reference is absent, corrupt, or symlinked;
- a download changes host, size, type, or digest;
- NODIS current authority cannot be confirmed;
- a source conflict, ambiguity, required review, or approval gate remains open.

The general lifecycle profile remains usable when NASA references or live
authority are unavailable.

## Supply-chain controls

- GitHub Actions use read-only permissions and commit-pinned actions.
- Public pull requests do not receive secrets or write tokens.
- CI does not use `pull_request_target`, self-hosted runners, caches, or
  artifacts.
- The Python dependency is version-pinned and hash-pinned.
- NASA reference identity is recorded in
  `references/reference-manifest.json`.

## Reporting a vulnerability

Do not open a public issue for a suspected secret or exploitable vulnerability.
Use GitHub's private vulnerability-reporting or Security Advisory interface for
this repository. Include affected versions, a minimal reproduction, and impact.
Do not include real credentials or private technical source data.
