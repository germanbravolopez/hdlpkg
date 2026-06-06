# Tests — HDL IP Packager

A scalable pytest suite. The layout, markers, fixtures, and reporting below are
designed so the suite stays fast and readable as the project grows from a handful
of modules to many.

## Layout

```
tests/
├── conftest.py                 shared fixtures + the local per-module summary hook
├── unit/                       fast, isolated tests (no I/O, no network)  - marker: unit
│   ├── test_version.py
│   ├── test_version_properties.py  Hypothesis property tests for version.py invariants
│   ├── test_vlnv.py
│   ├── test_manifest.py
│   ├── test_scaffold.py
│   ├── test_resolver.py            backtracking dependency resolution
│   ├── test_lockfile.py            ip.lock model: round-trip + verification
│   ├── test_cli.py
│   ├── test_precommit_config.py    .pre-commit-config.yaml parses + keeps CI hooks
│   └── test_docs_site.py       mkdocs.yml parses + every nav page exists
└── integration/                multi-module / filesystem tests            - marker: integration
    ├── test_manifest_cli_flow.py
    ├── test_resolve_cli.py         hdlpkg resolve end to end on examples/
    ├── test_cache.py               content-addressed cache (verify-on-read)
    ├── test_registry.py            local + HTTP registries, graph walk, install
    └── test_examples.py         validates the bundled examples/ cores
```

There are intentionally **no `__init__.py`** files: the suite runs under pytest's
`importlib` import mode (configured in `pyproject.toml`), so test modules are
imported by path and never collide.

## Running

```powershell
pytest                              # everything, with the per-module summary
pytest -m unit                      # only fast unit tests
pytest -m "not integration"        # skip filesystem/integration tests (fast loop)
pytest -m slow                      # only the slow ones (none yet)
pytest tests/unit/test_version.py   # a single file
pytest -k "constraint"             # tests matching a keyword

# Coverage (gate is set by fail_under in pyproject.toml):
pytest --cov=hdl_ip_packager --cov-report=term-missing

# Produce the JUnit XML + the rendered Markdown report (what CI publishes):
pytest --junitxml=test-results.xml
python scripts/render_test_summary.py --title "Test results"
```

`pytest-randomly` shuffles test order every run to surface hidden coupling between
tests; a failure prints the seed so you can reproduce with `-p randomly --randomly-seed=<n>`.

## Markers

Declared (and enforced via `--strict-markers`) in `pyproject.toml`:

| Marker | Use for |
|--------|---------|
| `unit` | fast, isolated, pure-logic tests |
| `integration` | tests crossing modules or touching the filesystem |
| `slow` | anything over ~1s; exclude from the fast loop with `-m "not slow"` |

Apply a marker to a whole module with `pytestmark = pytest.mark.<name>` at the top
(see any test file).

## Fixtures (in `conftest.py`)

| Fixture | Gives you |
|---------|-----------|
| `sample_manifest_toml` | A complete, valid `ip.toml` as a string |
| `write_manifest` | Factory: write a manifest to a temp file, return its `Path` |

Plus pytest built-ins you'll use a lot: `tmp_path`, `monkeypatch`, `capsys`.

## Reporting

- **Locally**: `conftest.py`'s `pytest_terminal_summary` prints a `summary by
  module` table (PASS/FAIL + counts per module) at the end of every run.
- **In CI**: `scripts/render_test_summary.py` reads the JUnit XML and writes a
  foldable, per-group Markdown report to the GitHub Actions run summary, with
  failure messages inline.

## How to add a test

1. Put it in `tests/unit/` (fast/pure) or `tests/integration/` (I/O/multi-module).
2. Name the file `test_<thing>.py` and set `pytestmark = pytest.mark.<unit|integration>`.
3. Prefer many small, parametrized cases (`@pytest.mark.parametrize`) over a few
   big ones — see `test_version.py` for the style.
4. **Cover the error paths**: every `raise` in the code under test should have a
   test asserting it (`pytest.raises(SomeError)`).
5. Keep unit tests pure — if you need files, use `tmp_path`/`write_manifest` and
   mark the test `integration`.
6. Run `pytest` and keep coverage at/above the gate.

## Property-based tests (Hypothesis)

`test_version_properties.py` uses [Hypothesis](https://hypothesis.readthedocs.io)
to assert *invariants* over generated inputs (round-trip `Version.parse(str(v)) ==
v`, total-order/`sorted` consistency, constraint containment, and grammar fuzzing)
rather than fixed examples. Hypothesis ships in the `dev` extra. Use a shared
`settings(max_examples=..., deadline=None)` decorator to keep the loop fast and to
avoid wall-clock-per-example flakiness on AV-throttled machines (see `CLAUDE.md`).
Reach for it when a module has algebraic invariants; keep example-based tests for
specific, named edge cases.

## Testability rule (from the AI instructions)

If something is hard to test, that is a design signal: extract the pure decision
into its own function and test *that*. The `manifest` module reads files but stays
testable because all of its validation logic is pure and exercised via
`Manifest.from_str`. New code should follow the same shape.
