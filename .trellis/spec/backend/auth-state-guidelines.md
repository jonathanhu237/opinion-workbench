# Browser Authentication State Guidelines

## Scenario: Local browser authentication persistence

### 1. Scope / Trigger

Use this contract when a crawler or browser integration must reuse an authenticated session after the browser process exits. Authentication Cookie values are bearer credentials: anyone who obtains a valid value may impersonate the account.

This project permits a local plaintext state file for the single-user MVP only when the user has accepted that risk, the file is excluded from Git, and POSIX access is restricted to the current operating-system user.

### 2. Signatures

The persistence boundary exposes browser-context operations rather than platform login logic:

```python
class BrowserAuthStateStore:
    async def restore(self, browser_context: BrowserContext) -> bool: ...
    async def save(self, browser_context: BrowserContext) -> bool: ...
```

Platform integration order:

```text
create browser context
→ restore allowed authentication state
→ create authenticated HTTP client
→ run the platform's authoritative login check
→ fall back to interactive login when invalid
→ save state only after authentication is confirmed
```

### 3. Contracts

- State files use a versioned, platform-scoped schema containing only the authentication material required by that platform.
- Cookie capture uses an explicit URL/domain allowlist. Do not serialize all cookies from a shared browser context.
- Restore merges validated cookies with `BrowserContext.add_cookies()`; it must not clear unrelated browser storage.
- The platform's live authentication check remains authoritative. A readable state file never proves that a session is valid.
- A missing or schema-invalid file, or a file with no usable Cookies, returns `False` without raising. The caller still performs the live authentication check and uses its existing interactive fallback when that check fails.
- Writes use a temporary file plus atomic replacement. On POSIX systems, both temporary and final files must have mode `0600`.
- Runtime authentication files must live under a Git-ignored path such as `browser_data/auth_state/<platform>.json`.
- Logs may include platform, path, item count, and outcome. They must not include Cookie names, values, serialized state, authorization headers, or HTTP Cookie headers.
- Disabling the existing login-state feature flag must skip both restore and save operations.
- A platform may display a delayed safety-verification overlay after the ordinary login UI has loaded. Do not automate, evade, or simulate completion of that challenge. Keep the dedicated browser visible for manual handling, and save state only after the normal live authentication check subsequently succeeds.

No environment variables are required by the current implementation.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| State file is absent | Return `False` without warning; continue to the live check and its interactive fallback |
| JSON is truncated or root/schema fields have invalid types | Emit a non-sensitive warning and return `False` |
| Version or platform does not match | Ignore the file and return `False` |
| Cookie URL/domain is malformed or outside the allowlist | Reject that Cookie without raising |
| Cookie `sameSite` or other constrained field has an invalid type/value | Reject that Cookie without raising |
| Persistent Cookie is expired | Drop it before `add_cookies()` |
| Session Cookie uses `expires = -1` | Preserve it; do not misclassify it as expired |
| `add_cookies()` fails | Emit a non-sensitive warning and return `False` |
| Restore succeeds but live authentication check fails | Run interactive login and overwrite state after success |
| A platform safety-verification overlay blocks interactive login | Pause or end with a non-sensitive instruction for manual handling; never automate or bypass the challenge |
| Save fails | Continue the current authenticated run; warn without secret values |

### 5. Good / Base / Bad Cases

- **Good:** A platform allowlist captures only required Cookies, atomically writes an ignored `0600` file, restores before the first authentication check, rejects malformed entries without crashing, falls back when no usable state remains or the live check fails, and leaves platform safety challenges to the user.
- **Base:** No state exists, so the live check still runs and the unchanged interactive login flow remains available; state is created after authentication is confirmed.
- **Bad:** The program logs a Cookie value, trusts file presence as proof of login, imports Cookies for unrelated domains, lets malformed state crash the crawler, or scripts a slider/CAPTCHA bypass.

### 6. Tests Required

1. Missing file: assert no `add_cookies()` call and a `False` result.
2. Valid persistent and session Cookies: assert allowlisted Cookies restore once and `expires = -1` survives filtering.
3. Expired and foreign-domain Cookies: assert they are excluded.
4. Malformed JSON, schema, URL, and Cookie field types: assert no exception escapes and interactive login remains reachable.
5. Browser API failure: assert non-sensitive warning and `False` result.
6. Save path: assert URL-filtered capture, atomic replacement, final `0600` mode on POSIX, and Git ignore coverage.
7. Orchestration: assert restore occurs before client creation/live login check, save occurs only after confirmed authentication, and the disabled flag performs no I/O.
8. Secret logging: use sentinel credential values in representative invalid-state and browser-API failure fixtures, and assert neither logs nor exception text contain them.
9. Real regression: after one interactive login, fully stop the browser and prove the next start's first live check passes without displaying a QR code.
10. Safety challenge: when an official overlay appears during manual regression, record only its non-sensitive presence and verify no automated bypass action is introduced.

### 7. Wrong vs Correct

#### Wrong

```python
state = json.loads(path.read_text())
logger.warning("restore failed: %s", state)
await context.add_cookies(state["cookies"])
return True  # File presence is treated as authenticated.
```

#### Correct

```python
restored = await auth_state.restore(context)  # Validates schema, domain, expiry.
client = await create_platform_client(context)
authenticated = await client.pong()           # Live check is authoritative.
if not authenticated:
    await interactive_login()
    authenticated = await client.pong()
if authenticated:
    await auth_state.save(context)             # Never log credential values.
```
