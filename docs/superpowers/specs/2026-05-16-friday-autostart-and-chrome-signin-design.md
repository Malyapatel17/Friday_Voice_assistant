# Friday — Fix Chrome work-mode sign-in & autostart cmd-flash

**Date:** 2026-05-16
**Status:** Approved (pending user review of written spec)
**Scope:** Two focused bug fixes — no architectural change.

---

## Problems

### Problem 1 — Work mode opens Chrome tabs that are not signed in

Saying *"Friday, let's start the work"* opens Gmail, Claude.ai, and ChatGPT, but none of the tabs are signed in. The user expects Gmail to open as `malya.patel@bytestechnolab.com` and Claude.ai / ChatGPT to open as `malyapatel17@gmail.com`.

**Root cause:** `friday/launcher.py` maps:

- `ACCOUNT_A = "Profile 1"` (intended: bytes work account)
- `ACCOUNT_B = "Profile 2"` (intended: personal account)

Inspection of `%LOCALAPPDATA%\Google\Chrome\User Data\*\Preferences` shows:

| Profile dir | Display name      | Signed-in account                    |
| ----------- | ----------------- | ------------------------------------ |
| `Default`   | Person 1          | **malyapatel17@gmail.com**           |
| `Profile 1` | Your Chrome       | *(not signed in)*                    |
| `Profile 2` | Person 1          | *(not signed in)*                    |
| `Profile 4` | Work              | malya.aiml.moweb@gmail.com           |
| `Profile 5` | bytestechnolab    | **malya.patel@bytestechnolab.com**   |

The code points at the two unused, empty profiles. The two profiles that actually carry the right signed-in sessions are `Default` and `Profile 5`. Also: the inline comment misspells the work email as `malya.patel@technolab.com`.

### Problem 2 — At login a console flashes and disappears; Friday only loads after ~2 minutes

Two independent causes stacked together:

1. **Orphan Task Scheduler entry "Friday Assistant"** — a logon-triggered task with a 10-second delay, configured to run `C:\FridayAI\start_friday.bat` (a path that does not exist on this machine). It fails immediately with `LastTaskResult: 1`. The cmd window that briefly appears and "completely disappears" is this failed task — *not* Friday itself.
2. **`setup_startup.ps1` cannot clean it up** — the script's `$taskNames` array only matches `"Friday Tray Icon"` variants. It does not know about `"Friday Assistant"`, so re-running it never removes this orphan.

The "load after ~2 minutes" feel is a separate effect: at login, the Registry Run key `FridayTray` launches `friday_tray.pyw` correctly, which after 3 seconds spawns Friday via `start_friday.bat`. Friday's Whisper model load is competing for disk I/O against Docker Desktop, OneDrive, Teams, Discord, Chrome, Riot, and Edge autostarts that all fire at the same login. The model load is slow enough that the user perceives Friday as "not ready" for ~2 minutes. This is real but separate from the cmd-flash bug.

---

## Goals

1. Work mode opens all three tabs already signed in to the correct accounts.
2. No mysterious cmd window flash at login.
3. `setup_startup.ps1` is robust against future orphan tasks (idempotent wildcard cleanup).
4. Friday auto-starts ~30s after tray launch (giving heavy boot items time to settle), instead of 3s.

## Non-goals

- No change to `friday/conversation.py` (unused scaffolding for a future conversational mode).
- No attempt to speed up Whisper's cold-disk model load. That would require a precompiled CUDA cache and is a separate spec.
- No automatic Chrome profile discovery by email. Profile directory numbers are stable for this single-user machine; auto-discovery is over-engineering here.
- No new behavior for `launch_entertainment_apps`, `close_browsers`, or `open_shutdown_dialog`.

---

## Design

### Files changed

| File                  | Change                                                                                          |
| --------------------- | ----------------------------------------------------------------------------------------------- |
| `friday/config.py`    | Add `CHROME_PATH`, `CHROME_WORK_PROFILE`, `CHROME_PERSONAL_PROFILE` constants                   |
| `friday/launcher.py`  | Replace hardcoded constants with imports from `cfg`; fix comment typo; add startup profile-existence check |
| `friday_tray.pyw`     | Change `threading.Timer(3.0, ...)` → `30.0`; log the chosen delay                               |
| `setup_startup.ps1`   | Replace hardcoded `$taskNames` with wildcard discovery of any Friday-related task or shortcut    |
| *(one-off)*           | `Unregister-ScheduledTask -TaskName "Friday Assistant"` — runs once, before the script changes  |

### Problem 1 — Chrome profile fix

**`friday/config.py`** gains three new constants alongside `WAKE_WORD` / `TTS_RATE`:

```python
# Chrome
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_WORK_PROFILE     = "Profile 5"  # malya.patel@bytestechnolab.com
CHROME_PERSONAL_PROFILE = "Default"    # malyapatel17@gmail.com
```

**`friday/launcher.py`** changes:

- Import the three constants from `friday.config` (rename local references inside `launch_work_apps`).
- Delete the inline `CHROME_PATH`, `ACCOUNT_A`, `ACCOUNT_B` definitions.
- Fix the comment typo: `technolab.com` → `bytestechnolab.com`.
- Add a module-level `_verify_profiles()` helper invoked once at import on Windows: for each configured profile name, check that `%LOCALAPPDATA%\Google\Chrome\User Data\<name>` is a directory. If not, print `[WARN] Chrome profile '<name>' not found at <path> — work mode tabs will open unauthenticated`. Do not raise — Friday must still run.

**Resulting behavior of `launch_work_apps`:**

1. Open `https://mail.google.com` in `CHROME_WORK_PROFILE` (Profile 5) → already signed into bytes work account → loads authenticated.
2. Open `https://claude.ai` in `CHROME_PERSONAL_PROFILE` (Default) → signed in.
3. Open `https://chatgpt.com` in `CHROME_PERSONAL_PROFILE` (Default) → signed in.
4. Launch VS Code (unchanged).

**Why no automatic sign-in:** Google accounts cannot be programmatically logged in from the command line. Chrome's profile session cookies are the supported mechanism, and both target profiles already hold valid sessions. The fix is the mapping; the sessions persist as long as the user does not sign out of Chrome.

### Problem 2 — Autostart fix

**One-off cleanup (run once, by the user, before re-running the script):**

```powershell
Unregister-ScheduledTask -TaskName "Friday Assistant" -Confirm:$false
```

This removes the broken orphan task that has been producing the cmd flash at every login.

**`setup_startup.ps1`** Step 2 (Task Scheduler cleanup) replaces the hardcoded array:

```powershell
# Old: $taskNames = @("\Friday\Friday Tray Icon", "\Friday Tray Icon", "Friday Tray Icon")
# New: discover any task whose name or action references Friday / this project

Get-ScheduledTask | Where-Object {
    $_.TaskName -like "*Friday*" -or
    (($_.Actions | ForEach-Object { $_.Execute }) -like "*friday*") -or
    (($_.Actions | ForEach-Object { $_.Execute }) -like "*wake-up*")
} | ForEach-Object {
    Write-Host "  Removing scheduled task: $($_.TaskName)" -ForegroundColor Gray
    Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false -ErrorAction SilentlyContinue
}
```

Same wildcard approach for the Startup folder: enumerate `.lnk` files and remove any whose `TargetPath` or `Arguments` references the project directory (`wake-up`) or contains `friday_tray.pyw`, instead of matching three hardcoded shortcut names.

Both passes are idempotent — safe to re-run.

**`friday_tray.pyw`** change (single-line tuning + log):

```python
# Replace the existing line:
#     threading.Timer(3.0, lambda: start_friday(_icon_ref)).start()

_AUTOSTART_DELAY = 30.0  # seconds; lets Docker/OneDrive/audio drivers settle at boot
_log(f"Auto-start scheduled in {_AUTOSTART_DELAY}s")
threading.Timer(_AUTOSTART_DELAY, lambda: start_friday(_icon_ref)).start()
```

The mutex, watchdog, menu, stop/quit handlers, and desktop shortcut logic are unchanged.

**Why 30 seconds:** at this user's login, Docker Desktop, OneDrive, Teams, Discord, Chrome auto-launch, Edge auto-launch, and Riot Client all fire concurrently with `FridayTray`. Whisper's model load is disk-bound and loses that I/O race. 30 seconds is enough to let the heaviest items finish their initial spike (empirically Docker Desktop is the worst offender) before Friday starts loading models, while still being short enough that the user does not perceive the assistant as missing.

---

## Verification

**Problem 1:**

1. Say *"Friday"* → *"let's start the work"*.
2. Confirm Gmail opens already signed in to `malya.patel@bytestechnolab.com` (not a login page).
3. Confirm Claude.ai and ChatGPT open already signed in to `malyapatel17@gmail.com`.
4. Temporarily rename `%LOCALAPPDATA%\Google\Chrome\User Data\Profile 5` to `Profile 5_bak`, restart Friday, confirm the `[WARN]` line appears in the console; rename back.

**Problem 2:**

1. After running the one-off `Unregister-ScheduledTask` and the updated `setup_startup.ps1`, run:
   ```powershell
   Get-ScheduledTask | Where-Object { $_.TaskName -like "*Friday*" }
   ```
   Confirm zero results.
2. Reboot. Confirm: no cmd-window flashes at login. Tray icon appears within a few seconds. Friday auto-starts approximately 30 seconds after the tray loads. No "console appears and completely disappears" event.
3. Re-run `setup_startup.ps1` a second time and confirm it succeeds without errors (idempotency check).

---

## Risks and mitigations

| Risk                                                                                              | Mitigation                                                                                                                                                       |
| ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| User signs out of one of the two target Chrome profiles                                           | The startup `[WARN]` only covers missing directories, not session state. If sign-out happens, the user re-signs in once and Chrome restores the session.          |
| Chrome reset / profile renumber                                                                   | Documented in the comment next to the constants. If it ever happens, the user updates `friday/config.py` and restarts Friday.                                    |
| Wildcard task cleanup deletes a legitimate task that happens to mention "friday" or "wake-up"     | Restricted to `TaskName -like "*Friday*"` (proper noun, low collision risk) OR action path containing the literal project folder. False positives are unlikely. |
| 30-second delay is still not enough on some boots                                                 | The `_AUTOSTART_DELAY` constant lives at the top of `friday_tray.pyw`; trivial to bump. The `_log` line makes it visible in `friday_tray_error.log`.            |

---

## Out of scope

- `friday/conversation.py` cleanup.
- Whisper model cold-load optimization.
- Auto-discovery of Chrome profiles by email.
- Any behavior change to entertainment mode, browser close, or shutdown dialog.
