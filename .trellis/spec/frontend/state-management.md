# State Management

> How state is managed in this project.

---

## Overview

State is owned by the narrowest layer that represents it correctly. TanStack Query is the foundation for reusable backend resource state, React Router owns URL-addressable state, React Hook Form with Zod owns forms, and React owns ephemeral interaction state.

---

## State Categories

| State kind | Owner | Examples |
| --- | --- | --- |
| Server resources | TanStack Query | Future platform status, collected items, task mutations |
| URL state | React Router | Route selection, filters, pagination, selected item IDs |
| Form state | React Hook Form + Zod | Platform settings, keyword rules, validation errors |
| Local UI state | Component state or narrow context | Disclosure, focus, retry sequence, transient interaction |

The current health screen intentionally retains its narrow `fetchHealth(signal)` plus reducer flow. Do not migrate it merely to demonstrate TanStack Query; establish query keys and retry policy with the first reusable server-resource feature.

---

## When to Use Global State

Zustand is not installed. Introduce a client store only when a concrete value is client-only, shared across unrelated route branches, not accurately represented in the URL/form/server cache, and long-lived enough that lifting state is demonstrably harmful.

Valid future candidates might include a cross-route upload queue or an unsaved multi-route draft. The introducing task must specify ownership, lifecycle, and persistence behavior.

---

## Server State

- `QueryClient` is created once at module scope in `src/app/providers.tsx`; never construct it during render.
- Query keys identify backend resources plus all parameters that affect their result.
- When multiple routes consume the same resource, expose one shared query hook and retain TanStack
  Query's normal cache lifetime. Do not set `gcTime: 0` merely to force fresh route renders; use
  mutation invalidation, active-state polling, or explicit refetch based on the resource contract.
- Mutations invalidate or update the relevant query cache instead of copying server data into component/global state.
- URL-addressable filters remain in React Router even when they also participate in a query key.
- Network policy, API base URL, and response validation belong in `lib/api/`, not in generic providers.

### Secret-bearing forms

The AI configuration form is a deliberate exception to using TanStack mutations for every write.
Submit the typed API key via a direct API function so it never becomes retained mutation variables.
RHF owns only the transient input; clear it after a submitted attempt, including failures. Do not
persist credentials in browser storage, cached errors or form drafts. Cache only the validated
non-secret settings projection. See [AI Configuration](../backend/ai-configuration-guidelines.md)
for the API, saved-revision testing and endpoint-change contracts.

### Monitoring-rule composition

RHF owns the two editable textarea groups (`monitoring_objects`, optional `issue_keywords`). Derive
the ordered query preview locally from watched form values; do not keep a second mutable preview
state or request a preview endpoint. Edit and every full PUT (including enable/disable) retain the
original groups. The server's read-only `terms` projection is for collectors and effective counts,
not for reconstructing input groups. Update or invalidate the shared rule query after mutations. See
[Monitoring Rules](../backend/monitoring-rules-guidelines.md) for query limits and strict payloads.

Do not disable error-target inputs during RHF's local validation merely because `isSubmitting` is
true: resolver completion can try to focus a still-disabled input. In this editor, inputs and dialog
mutation locking use `saveMutation.isPending`; the submit button additionally uses `isSubmitting`
to block repeated submissions. Test both first-invalid-field focus and disabled controls during an
actual pending save. Verify focus with ordinary mouse/keyboard events, not only a synthetic
automation click that may refocus its own target after the application's handler finishes.

### Sequencing exclusive browser operations

Platform authentication uses one browser operation at a time. A page-level batch action must keep
only its queue and progress as ephemeral React state, invoke the existing per-platform TanStack
Query mutation in catalog order, and let the shared platform query remain authoritative for each
attempt's progress and result.

- Do not start the next platform when the POST is merely pending or by inspecting a terminal value
  left over from an earlier check. First accept the new attempt, then wait until the polled platform
  projection leaves `checking` / `action_required` and reaches a terminal state.
- Keep competing row actions disabled while the batch exists; never overlap browser attempts.
- If an attempt request cannot start, end the local batch and preserve the technical API error. Do
  not reinterpret service, protocol, or conflict errors as an account-login failure.
- Test catalog order, non-overlap, the `checking -> action_required -> terminal` path, request-start
  failure recovery, unavailable catalog entries, and unchanged single-platform behavior.

---

## Common Mistakes

- Creating a new `QueryClient` during render and losing cache on every update.
- Giving a shared cross-route query `gcTime: 0`, causing avoidable request churn every time the last
  observer unmounts during navigation.
- Copying the same server resource into TanStack Query and a client store.
- Keeping filters or pagination only in component state, making views impossible to restore.
- Copying React Hook Form values into parallel component state.
- Creating a global context for unrelated ephemeral UI state.
