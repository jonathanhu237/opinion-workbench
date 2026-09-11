# Windows delivery verification

Implementation baseline: cda5fa20bfe4a5e4da39b180c0be43b8e7359651. All changes are local and uncommitted.

## Verified on macOS

- Parent independent final focused suite: 34 passed, covering application paths, lifecycle/API entry, occupied port, startup timeout, worker contracts and existing native Chrome lifecycle.
- Implementer broader focused backend suite: 38 passed; frontend typecheck, lint and production build passed.
- Local PyInstaller build produced separate application and console worker; frozen worker JSON broker exchange passed. This is a macOS packaging smoke check, not a Windows executable validation.
- Actual local server smoke check: blank temporary database, static page and health endpoint available, last WebSocket closure exits launcher successfully.
- Parent baseline comparison reproduced all 31 backend failures encountered by the implementation suite on the unchanged baseline. The full backend run was interrupted after 319 passes and 31 failures; do not describe the full backend suite as passing.
- Frontend full suite: 567 passed and 3 failed. All three failures also reproduce on the unchanged baseline.

## Windows acceptance still required

On the maintainer's Windows x64 machine, extract the toolkit and double-click windows/build.cmd. Build output: dist/windows/Longtian-Setup.exe. Build logs: windows/build/logs/.

Use windows/README.md acceptance checklist: clean installation, launch, own Chrome login, AI configuration, actual collection/reporting, last-page shutdown, interrupted task state on reopening, manual retry, upgrade and retained data. Windows DPAPI, installer execution and actual browser collection have not been exercised on macOS. The installable EXE is not yet produced.

## Final review and artifact

- Three review rounds completed; final code review passed.
- Parent executed all nine delivery contract tests with mise-managed PowerShell available: 9 passed, including both bootstrap/no-winget scenarios; no installations performed by those scenarios.
- Toolkit ZIP integrity and exclusion checks passed: 310 entries, 961672 bytes.
- SHA256: 93f3346d250740d3aae4a456d87229878a316282bbeb43bfff43823e1d91cb96.
