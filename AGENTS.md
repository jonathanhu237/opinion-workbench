## Local-First Application Runtime

- This project is a local-first desktop application. By default, run the
  frontend, backend API, SQLite runtime database, MediaCrawler processes, and
  browser/CDP integration on the user's local machine.
- Use the local machine for development previews, debugging, and application
  validation. Browser-dependent collection and platform-login flows must run on
  the same local machine as the user's browser.
- Do not rsync this project to Centaurus, start application services there, or
  use Centaurus for validation unless the user explicitly requests Centaurus in
  the current task. Do not infer permission from workload size or tool
  availability.
- This local-first policy overrides older Trellis specs, task artifacts, or
  verification notes that prescribe Centaurus; treat those references as
  historical unless the user explicitly opts into Centaurus again.
- If the user explicitly requests Centaurus for a specific task, keep the local
  repository as the source of truth and apply the Centaurus workflow only to
  that task.
