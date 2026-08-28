# Manual Summary Integration Verification — 2026-08-28

## Scope and safety

This round implements the existing full-run manual summary task. Local source is authoritative;
execution used the isolated Centaurus checkout `/tmp/longtian-media-validation.DeYMEC`. No user
database, credentials, browser profile, runtime directory, or private cost-probe cache was copied.
No real provider requests or platform-browser acquisition occurred. No commit, push or archive.

The task-only `verification/preview_app.py` creates its own `mkdtemp` SQLite/runtime, seeds four
synthetic results, and injects fake model and media workers into the real product application,
repository, enrichment service and summary pipeline. Its platform process launcher rejects live
browser startup. Input media is a tiny synthetic PNG; the model's JSON and token counts are fake.
This proves application integration, not actual model quality, media understanding or billing.

## Automated gates

- First transport checkpoint: **160 passed**, scoped Ruff and formatting clean; local/remote
  hashes matched. The 21/100 historical-query cases failed before the 20→100 compatibility fix.
  See `transport-check.md`.
- First full backend gate: **593 passed, 1 failed**. The failure was a test-only Pydantic injection
  that did not run; it was replaced by a real SQLite trigger aborting the second item insert to
  verify rollback of both the parent and first child.
- First frontend gate: **274 passed / 14 files**, formatting/lint/typecheck/build passed. The
  subsequent independent review added matched-term/Unicode/error-copy regressions.
- Final independent gate after source-hash reconciliation: backend **596 passed in 11.94s**,
  Ruff/check-format **68 files** clean. Frontend independent frozen install **447 packages**,
  **281 passed / 14 files**, formatting, lint (0 errors/warnings), typecheck and production build
  all passed. Thirty key source/test/package/lock hashes matched local and remote. See
  `integration-check.md` for narrow review fixes and red/green evidence.

## Browser acceptance

The local browser visited a forwarded isolated frontend at `127.0.0.1:15184`, proxying only the
fake API on `127.0.0.1:18080`. Existing services on 5173/8000/15173/15174 were not used or stopped.

1. Initial result page and read-only summary history: zero model and media calls. Original results
   remained visible without AI. Choosing “再次命中 0” hid result rows but confirmation still stated
   the entire four-result run, not zero or the current page.
2. Confirmation displayed the saved endpoint/model and explicit media/quota boundary. Escape
   dismissed it; counters stayed at zero. No key was displayed or submitted through the UI.
3. Summary #1 showed pending/progress/cancel, then completed with **1 relevant, 1 irrelevant,
   1 uncertain, 1 input-incomplete, 0 failed**. The incomplete source said no model was called.
   Three item calls plus one text-composition call yielded **60 synthetic tokens / 4 calls**.
4. The report cited only the relevant source, resolving to the stored original result URL.
   Expanding “内容分析” showed distinct decisions/reasons and the explicit incomplete-input message.
   No fake source link was followed to a live platform.
5. Summary #2 reused all three completed analyses, retried only the unresolved acquisition, and
   made just one new text-composition call: **15 synthetic tokens / 1 call**, “复用分析 3”.
   Totals after two complete versions were 5 fake model responses and 5 media acquisitions.
6. Reload restored #2 without new calls. Force-refresh #3 followed by cancellation retained one
   completed analysis and cancelled the other three. It showed two attempted requests but only
   one accounted response: **15 synthetic tokens, accounting incomplete**.
7. Selecting #1 after cancellation restored its original report/coverage/60-token accounting;
   old versions were not overwritten. The observed 1265px viewport had equal scroll/client width
   (no horizontal overflow); screenshot review matched the existing theme. No responsive override
   or visual redesign was performed. Browser warning/error logs were empty.
8. Owned staging directories were empty after each terminal operation. The first owned preview
   tab and Vite process were closed before the independent dependency-install gate. Only exact
   task-owned processes were stopped; shared dependency targets and other servers were untouched.

Follow-up after the independent text/decoder fixes: reopened the same isolated source and restored
cancelled summary #3. Its retention notice appeared only once, completed-analysis access and partial
token accounting remained, warning/error logs were still empty, counters did not increase, and
staging was empty. This final view reused the original fake backend; final route-header changes
were covered by the freshly synchronized backend API tests, not claimed as a live-provider run.
The final preview tab, task-owned API/Vite processes and SSH port forward were then closed; no
regular application service or shared dependency target was stopped or removed.

## Remaining live acceptance

The task remains `in_progress`. A separately authorized real source must still pass the complete
worker → acquired actual media → configured model → saved analysis → text summary chain. Confirm
content fidelity, cited claims, usage and reuse on that source. The earlier private video cost probe
and this synthetic acceptance are not that gate. The media child remains open, including incomplete
WB/KS inventory, XHS acquisition and abnormal-worker cleanup limitations already documented there.
Do not claim five-platform complete-media readiness, automatically run a paid acceptance, or treat
an AI source claim as a verified incident.
