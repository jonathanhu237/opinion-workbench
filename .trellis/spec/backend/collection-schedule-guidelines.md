# Historical Fixed-Interval Collection

This document is retained only to explain the v13 storage/source that may still
exist in development checkouts. The old `/api/v1/collection-schedules` router,
timer lifecycle and frontend schedule pages are no longer registered.

Do not use this aggregate for new automatic behavior and do not restore its
completion callbacks. New work must follow
[Unified Opinion Automation](./automation-workflow-guidelines.md), whose central
owner executes the fixed collection, initial-analysis and topic-report chain.

The v15 additive migration intentionally leaves old schedule rows untouched.
The application was not deployed with this feature, so no conversion or legacy
UI is required; historical tables may be removed only in a separately reviewed
schema cleanup.
