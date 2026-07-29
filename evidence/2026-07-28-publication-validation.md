# Publication validation — 2026-07-28

This record contains dated evidence for the public repository. Normative behavior
remains in the skill, scripts, tests, and documentation.

## Public workflow

- Repository: `GhostlyGawd/write-verifiable-requirements`
- Implementation pull request:
  [#1](https://github.com/GhostlyGawd/write-verifiable-requirements/pull/1)
- Validated merge commit:
  `37eb725eefc418d427f1e6d5034f52d30c82480a`
- Pull-request workflow:
  [run 30420535081](https://github.com/GhostlyGawd/write-verifiable-requirements/actions/runs/30420535081)
- Main-branch workflow:
  [run 30420560181](https://github.com/GhostlyGawd/write-verifiable-requirements/actions/runs/30420560181)
- Required `validate` job result: `PASS`
- Automated tests: 75 passed
- Bundled-reference verification: `PASS`
- Fresh agent installation: `PASS`

The first manual workflow run failed because `setup-python` interpreted
`cache: false` as a package-manager cache provider. Pull request #1 removed that
unsupported input and added a regression test. Both subsequent public workflow
runs passed.

## Reference integrity

- NASA Systems Engineering Handbook Revision 2:
  `8eeb4887a4dc57a23049da7dd2ed556833cf98e214b240468d987873164ff688`
- NPR 7123.1D Change 2:
  `686b0d55d492bffe7e750a15523f339c5de41cb253499828b4fe9f2924810e40`
- Reference manifest:
  `b88287e9b90c99468e933e5080c67381e41fea684c5932328d96b33e1ba4dfeb`

Local verification matched both PDF files to the manifest. A secure repair from
the approved NASA URLs produced the same hashes. The NODIS authority check
identified NPR 7123.1D Change 2 as the current record on the validation date.
All 435 PDF pages rendered successfully and received a page-level visual
inspection.

## Publication and security checks

- Clean dependency installation with hash verification: `PASS`
- Fresh-clone tests and installation: `PASS`
- Git object integrity check: `PASS`
- Secret scan of reachable history and raw object content: zero findings
- Forbidden local-path and identity metadata scan: zero findings before the
  platform-generated merge commit
- Intersection with the private source commit set: zero commits
- Public repository references before the evidence change: one branch and zero
  tags
- Public CI permissions: read-only repository contents
- Public CI runner: standard GitHub-hosted `ubuntu-24.04`
- Workflow actions: pinned to full commit hashes

GitHub generated the merge commit with the account profile name as author and
the GitHub service identity as committer. The source commits use
`GhostlyGawd <141867403+GhostlyGawd@users.noreply.github.com>`.

## Operational checks

- Transactional install: `PASS`
- Repeated no-op install: `PASS`
- Corrupt-reference rejection: `PASS`
- Approved-reference repair: `PASS`
- Offline local verification: `PASS`
- Global installed copy matched the verified repository source on the
  validation date.

## Boundaries

- The repository has no code license. Public visibility does not grant a code
  license.
- The unchanged NASA publications retain their source notices and identifiers.
- The repository does not claim NASA endorsement.
- Automated checks do not replace requirements-authority review, technical
  review, or human approval.
