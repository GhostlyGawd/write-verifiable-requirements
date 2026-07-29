# Contributing

## Before a change

1. Identify the requirement, source authority, and affected profile.
2. Preserve technical meaning and release-gate behavior.
3. Do not add a rule or citation that the controlling source does not support.
4. Use a separate change for a reference-document revision.

## Checks

Run:

```shell
python -m pip install --require-hashes -r requirements.txt
python -m unittest discover -s tests -v
python write-verifiable-requirements/scripts/manage_references.py status
python scripts/install_skill.py --dry-run
```

The test suite must include passing and failing cases for new deterministic
behavior. A passing command proves only the invariant that command checks.

## Reference updates

Never update a reference digest only because an official URL returns different
bytes.

1. Download the new official file to a separate staging location.
2. Record the old and new title, revision, size, SHA-256, URL, and authority
   status.
3. Inspect metadata and every page for source identity and third-party notices.
4. Review every derived rule and coverage mapping against the new reference.
5. Update the manifest intentionally.
6. Run the complete unit, acceptance, forward, installation, and drift tests.
7. Obtain maintainer review before merging.

The update must not overwrite the last reviewed reference during evaluation.

## Pull requests

Describe the changed behavior, authority basis, test evidence, documentation
impact, and unresolved gates. Do not include credentials, private technical
data, local machine paths, or private audit evidence.
