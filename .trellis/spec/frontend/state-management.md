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
- Mutations invalidate or update the relevant query cache instead of copying server data into component/global state.
- URL-addressable filters remain in React Router even when they also participate in a query key.
- Network policy, API base URL, and response validation belong in `lib/api/`, not in generic providers.

---

## Common Mistakes

- Creating a new `QueryClient` during render and losing cache on every update.
- Copying the same server resource into TanStack Query and a client store.
- Keeping filters or pagination only in component state, making views impossible to restore.
- Copying React Hook Form values into parallel component state.
- Creating a global context for unrelated ephemeral UI state.
