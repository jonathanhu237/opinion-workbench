# Research: Backend and source-enrichment dirty changes

- Query: Review the uncommitted backend source, backend tests, and initial-analysis specification; determine intent, completeness, validation commands, risks, and missing coverage before separate commits/pushes.
- Scope: internal
- Date: 2026-09-01

## Findings

### Coherent intent

The product change is a narrowly scoped historical-compatibility fix for one stored Toutiao URL form: `http://www.toutiao.com/a<ID>/?channel=`. It preserves the stored URL in analysis snapshots while allowing enrichment to proceed, without broadening normal collection output or accepting arbitrary query strings.

- `backend/src/longtian_api/services/enrichment_models.py:262-297` keeps the existing strict source boundary and adds exactly the trailing-slash empty-`channel` legacy form. The full-string regular expression still rejects nonmatching host, path, port, credentials, fragments, extra query parameters, and ID mismatches.
- `backend/tests/test_content_analysis_repository.py:127-169` simulates an already-stored historical row, admits it via `all_never_started`, proves the URL is frozen unchanged, and proves admission performs no browser/model call.
- `backend/tests/test_enrichment_staging.py:229-277` checks the positive form, close adversarial variants, exact preservation through enrichment validation, and acceptance by `AnalysisSource`.
- `.trellis/spec/backend/initial-analysis-guidelines.md:14-17,59-63,95-101,189-190,203-218,239-249,274-283` documents the backend/worker cross-boundary contract, preservation rule, failure behavior, and required adversarial testing.
- The coupled MediaCrawler edit implements the same regex at `third_party/MediaCrawler/tools/enrichment_worker_protocol.py:120-143`, with protocol/model tests at `third_party/MediaCrawler/tests/test_product_media_protocol.py:86-138`.
- Actual Toutiao enrichment upgrades an accepted stored HTTP URL to HTTPS before browser navigation at `third_party/MediaCrawler/media_platform/toutiao/product_enrichment.py:241-260`, while the returned evidence retains the original stored source URL.

The code path is internally consistent and no functional defect was found in the new validator. The change is not safely publishable as only a parent-repository backend commit: the backend and worker validators must ship together or the backend will admit a source that the old worker rejects.

### Validation completed

- Backend Ruff on the three changed Python files: passed.
- Backend Ruff format check on the three changed Python files: passed.
- `uv run pytest tests/test_enrichment_staging.py tests/test_content_analysis_repository.py`: **61 passed**.
- MediaCrawler `tests/test_product_media_protocol.py`: **99 passed**.
- MediaCrawler targeted protocol/navigation checks using its own `.venv`: **28 passed, 121 deselected**, with one existing SQLAlchemy deprecation warning.
- `git diff --check` passed for the reviewed parent files and the two changed submodule files.

Recommended final gates before committing:

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest

cd ../third_party/MediaCrawler
.venv/bin/python -m pytest \
  tests/test_product_media_protocol.py \
  tests/test_product_media_toutiao.py
```

### Commit and push boundaries

1. Commit and push the MediaCrawler code/tests first on its own `main` branch and remote (`https://github.com/jonathanhu237/MediaCrawler.git`). The submodule currently points at `546b0d78fe51cfd7c86439baf6129d441a050414`; a parent commit cannot publish the dirty child working tree.
2. Then commit the parent backend implementation/tests plus the updated submodule pointer. This keeps the two runtime validators deployable as one parent revision.
3. Stage the URL-contract hunks in `initial-analysis-guidelines.md` with that functional commit, or use a separate docs commit immediately afterward.
4. The spec's change from Centaurus-only validation to local-first validation (`initial-analysis-guidelines.md:245-249`) is a distinct repository-policy concern. It should travel with the related root `AGENTS.md` policy change, not be silently mixed into the URL-compatibility commit.

## Files Found

- `backend/src/longtian_api/services/enrichment_models.py` — backend source-identity validation and enriched-content contract.
- `backend/tests/test_content_analysis_repository.py` — atomic analysis admission and frozen-source repository coverage.
- `backend/tests/test_enrichment_staging.py` — backend/worker contract fixtures and validation boundary tests.
- `.trellis/spec/backend/initial-analysis-guidelines.md` — executable initial-analysis and historical-source contract.
- `third_party/MediaCrawler/tools/enrichment_worker_protocol.py` — worker-side copy of the source-identity boundary.
- `third_party/MediaCrawler/tests/test_product_media_protocol.py` — worker protocol/model adversarial tests.
- `third_party/MediaCrawler/media_platform/toutiao/product_enrichment.py` — HTTPS upgrade and browser navigation path.
- `third_party/MediaCrawler/tests/test_product_media_toutiao.py` — adapter-level stored-URL navigation tests.
- `third_party/MediaCrawler/tests/fixtures/enrichment_contract_v1.json` — existing cross-repository golden source/evidence corpus.

## Code Patterns

- Validate stored identity at admission and again before browser acquisition; do not rewrite the database or frozen snapshot.
- Permit a legacy exception with a full-string regex and a matching numeric content ID, rather than general URL parsing/allowlisting.
- Upgrade the accepted historical HTTP form only at the platform navigation boundary; serialize the original source URL back into evidence.
- Keep backend and worker validation behavior in lockstep because they are separate process boundaries.

## External References

- No web sources were needed. Runtime/tool versions observed locally: Python 3.11, pytest 9.x, Ruff from the backend environment, Pydantic 2.x per both project manifests.
- MediaCrawler is a Git submodule with its own Git remote and commit history; it must be committed and pushed independently before updating the parent pointer.

## Related Specs

- `.trellis/spec/backend/initial-analysis-guidelines.md` — primary contract reviewed here.
- `.trellis/spec/backend/ai-summary-guidelines.md` — referenced shared transport/media/privacy/usage requirements.
- Root `AGENTS.md` — local-first runtime/validation policy; its uncommitted policy edit is related only to the spec's validation-location hunk.

## Caveats / Not Found

1. **Shared-matrix drift:** the spec requires a shared adversarial matrix (`initial-analysis-guidelines.md:239-244`), but the new `?channel=` cases are duplicated independently in the backend and submodule Python tests. The shared fixture `third_party/MediaCrawler/tests/fixtures/enrichment_contract_v1.json:18-39` was not extended. This is a maintainability/spec-compliance gap: the copies can diverge while each suite stays green.
2. **Missing adapter-level regression:** `third_party/MediaCrawler/tests/test_product_media_toutiao.py:168-179` proves HTTP-to-HTTPS navigation for the two older legacy forms, but its parameter list omits the newly accepted `...?channel=` form. The generic upgrade code makes the implementation likely correct, but one new parameter should prove the exact new URL is upgraded once, preserves the stored source value, and does not disturb user tabs.
3. **Environment note:** trying the adapter test with the backend environment failed at collection because Pillow is not a backend dependency. The same targeted test passed with MediaCrawler's own `.venv`; this is an environment-selection issue, not a product failure.
4. No live Toutiao/browser request was made. All findings are based on strict unit/repository tests and source inspection; they prove protocol behavior, not current platform availability.
