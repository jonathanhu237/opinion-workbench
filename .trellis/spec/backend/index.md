# Backend Development Guidelines

> Best practices for backend development in this project.

---

## Overview

This directory contains guidelines for backend development. Fill in each file with your project's specific conventions.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Module organization and file layout | To fill |
| [Database Guidelines](./database-guidelines.md) | Local SQLite ownership, queries, transactions, migrations, and tests | Active |
| [Error Handling](./error-handling.md) | Stable product errors, validation, storage sanitization, and tests | Active |
| [Monitoring Rules](./monitoring-rules-guidelines.md) | Ordered object/issue groups, query composition, v9 migration, API and collector contracts | Active |
| [Quality Guidelines](./quality-guidelines.md) | Code standards, forbidden patterns | To fill |
| [Logging Guidelines](./logging-guidelines.md) | Structured logging, log levels | To fill |
| [Browser Authentication State](./auth-state-guidelines.md) | Local credential persistence, safe fallback, and secret-safe logging | Active |
| [Visible Browser Search Adapter](./browser-search-adapter-guidelines.md) | Search-only browser lifecycle, DOM/link contracts, storage, and live validation | Active |
| [Platform Connection](./platform-connection-guidelines.md) | Authentication-only subprocess protocol, product state, and borrowed-Chrome ownership | Active |
| [Product Search](./product-search-guidelines.md) | Borrowed-Chrome collection runs, product SQLite deduplication, API/worker contracts, and validation | Active |
| [Batch Search](./batch-search-guidelines.md) | Durable multi-platform batches, serial ownership, attempts, recovery, and UI/API contracts | Active |
| [AI Configuration](./ai-configuration-guidelines.md) | Single-model settings, protected credentials, exclusive operations, text testing, and secret-safe UI/API contracts | Active |

---

## How to Fill These Guidelines

For each guideline file:

1. Document your project's **actual conventions** (not ideals)
2. Include **code examples** from your codebase
3. List **forbidden patterns** and why
4. Add **common mistakes** your team has made

The goal is to help AI assistants and new team members understand how YOUR project works.

---

**Language**: All documentation should be written in **English**.
