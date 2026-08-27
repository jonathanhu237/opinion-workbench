# AI Configuration Execution

Depends on: none. The final parent review and starting this child were approved on 2026-08-27. Implement configuration only; later media, screening and summary children remain separate deliveries.

1. Read parent PRD/design and curated specs/research. Confirm dirty state and remote availability; no runtime reads or real keys.
2. Add settings schema/repository/migration and isolated credential-store tests (mode, symlink, atomic replacement, failure/reopen).
3. Implement injectable configuration lease/client and strict GET/PUT/test routes. Add status/code, redaction, origin/destination and fake SSE tests.
4. Add `AI 配置` route and shadcn form using the existing frontend stack; test validation, dirty state, pending state, direct secret submission/clearing and saved-key absence.
5. Sync code/tasks one-way to Centaurus excluding runtime and credentials. Run the complete backend/frontend commands in parent `implement.md`; forward services for visual/console checks.
6. Dispatch the required Trellis check role, resolve scoped findings, and document any learned contracts in specs. Report real-provider validation separately; no unsolicited call or live key setup.

Risky shared files: `database.py`, `main.py`, router/dependency ownership, frontend shell/router, backend manifest/lock. Keep existing routes, migration history and platform worker unchanged.

Acceptance proves settings independently. Do not start media/screening as a side effect of completing this child. No commit/push unless requested.
