# fixtures/ — interlocking-coverage

**Placeholder (afokapu/atdd-extensions#24 scaffold).** Holds the detector's
golden inputs. The owning build slice populates:

- `clean/` — a consumer tree the detector passes (no violations).
- `dirty/` — a consumer tree the detector flags (>=1 RAW violation).

Mirror the python-pytest fleet layout (see
`official/atdd.workspace.python-pytest/implementations/*/fixtures/{clean,dirty}/`).
