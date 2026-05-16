# Friday Autostart & Chrome Sign-in Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two Friday assistant bugs — work mode opens Chrome tabs that are not signed in, and a phantom `cmd.exe` window flashes at every login.

**Architecture:** No architectural change. Surgical fixes across four files plus a one-off PowerShell action: (1) move Chrome profile config out of `launcher.py` into `friday/config.py` with the correct profile directory names, (2) delete a broken orphan Task Scheduler entry, (3) harden `setup_startup.ps1` to wildcard-discover any Friday-related scheduled task or startup-folder shortcut, (4) increase the tray's auto-start delay from 3s to 30s so Whisper's cold-disk model load does not race Docker / OneDrive / Teams at login.

**Tech Stack:** Python 3 (no test framework in this repo — the codebase is verified by manual run + reboot, per `CLAUDE.md`), PowerShell 5.1, Windows Task Scheduler, Windows Registry Run keys.

**Spec:** `docs/superpowers/specs/2026-05-16-friday-autostart-and-chrome-signin-design.md`

---

## File Structure

| Path                                                                      | Role                                                                            |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `friday/config.py`                                                        | Add three Chrome-related constants (path + two profile dirs)                    |
| `friday/launcher.py`                                                      | Consume the new constants; delete inline hardcoded values; fix typo; warn-only profile existence check at import |
| `friday_tray.pyw`                                                         | Single-line delay change (3.0 → 30.0) + a log line                              |
| `setup_startup.ps1`                                                       | Replace hardcoded `$taskNames` array with wildcard discovery; same for Startup folder shortcuts |
| *(no file — one-off PowerShell action)*                                   | `Unregister-ScheduledTask -TaskName "Friday Assistant" -Confirm:$false`         |

**Note on tests:** `CLAUDE.md` says "There are no tests, lints, or build steps configured." Each task below uses **manual verification commands** in place of unit tests — running the script, inspecting output, and a final reboot test. Do not introduce a test framework as part of this plan.

---

### Task 1: Remove the broken orphan Task Scheduler entry (one-off)

This task does not modify any file. It deletes the `"Friday Assistant"` scheduled task that points to `C:\FridayAI\start_friday.bat` (a path that does not exist) and which is producing the cmd-flash at every login.

Doing this first means the rest of the plan can be verified at reboot without the orphan task confounding the result.

**Files:** none

- [ ] **Step 1: Confirm the orphan task exists**

Run:
```powershell
Get-ScheduledTask -TaskName "Friday Assistant" | Format-Table TaskName, State
```
Expected output: one row, `TaskName = Friday Assistant`, `State = Ready`.

If the row is missing, skip Step 2 and move to Task 2.

- [ ] **Step 2: Unregister the orphan task**

Run:
```powershell
Unregister-ScheduledTask -TaskName "Friday Assistant" -Confirm:$false
```
Expected output: none (silent success).

- [ ] **Step 3: Verify removal**

Run:
```powershell
Get-ScheduledTask | Where-Object { $_.TaskName -like "*Friday*" }
```
Expected output: empty (no rows).

- [ ] **Step 4: Nothing to commit** — this is a system-state change, not a file change. Continue to Task 2.

---

### Task 2: Add Chrome constants to `friday/config.py`

**Files:**
- Modify: `friday/config.py`

- [ ] **Step 1: Append the three constants to `friday/config.py`**

Current contents end at line 17 (`TTS_RATE = 180`). Append the following block at the end of the file:

```python

# ─────────────────────────────────────────────
# Chrome profile mapping (work mode)
# ─────────────────────────────────────────────
# Resolve profile dirs with:
#   Get-ChildItem "$env:LOCALAPPDATA\Google\Chrome\User Data" -Directory
# Pick the directory whose Preferences file contains the email you want.
CHROME_PATH             = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_WORK_PROFILE     = "Profile 5"  # malya.patel@bytestechnolab.com
CHROME_PERSONAL_PROFILE = "Default"    # malyapatel17@gmail.com
```

- [ ] **Step 2: Verify the file parses**

Run:
```powershell
.\.venv\Scripts\python.exe -c "import friday.config as c; print(c.CHROME_PATH); print(c.CHROME_WORK_PROFILE); print(c.CHROME_PERSONAL_PROFILE)"
```
Expected output (three lines):
```
C:\Program Files\Google\Chrome\Application\chrome.exe
Profile 5
Default
```

- [ ] **Step 3: Commit**

```bash
git add friday/config.py
git commit -m "config: add Chrome path and profile-dir constants"
```

---

### Task 3: Refactor `friday/launcher.py` to consume the new constants

**Files:**
- Modify: `friday/launcher.py`

Three independent edits in one file (one commit because they are tightly coupled — a partial edit would break work mode).

- [ ] **Step 1: Replace the top of `friday/launcher.py`**

The current file (lines 1–12) is:

```python
"""
friday/launcher.py -- App launching, browser closing, shutdown dialog
"""

import subprocess
import time

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# Map emails to Chrome profiles
ACCOUNT_A = "Profile 1"   # malya.patel@technolab.com
ACCOUNT_B = "Profile 2"   # malyapatel17@gmail.com
```

Replace it with:

```python
"""
friday/launcher.py -- App launching, browser closing, shutdown dialog
"""

import os
import subprocess
import time
from pathlib import Path

from friday import config as cfg

CHROME_PATH = cfg.CHROME_PATH
ACCOUNT_WORK     = cfg.CHROME_WORK_PROFILE      # malya.patel@bytestechnolab.com
ACCOUNT_PERSONAL = cfg.CHROME_PERSONAL_PROFILE  # malyapatel17@gmail.com


def _verify_profiles() -> None:
    """Warn (do not crash) if either configured Chrome profile dir is missing."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return  # not Windows or unusual environment; skip silently
    user_data = Path(local) / "Google" / "Chrome" / "User Data"
    for profile in (ACCOUNT_WORK, ACCOUNT_PERSONAL):
        if not (user_data / profile).is_dir():
            print(
                f"[WARN] Chrome profile '{profile}' not found at "
                f"{user_data / profile} -- work mode tabs will open unauthenticated"
            )


_verify_profiles()
```

- [ ] **Step 2: Update `launch_work_apps` to use the new names**

Find the existing function (current lines 41–58):

```python
def launch_work_apps(os_type):
    """Open Gmail (bytes account), Claude.ai + ChatGPT (personal account), VS Code."""
    print("\n[WORK MODE] Launching apps...\n")

    open_profile(ACCOUNT_A, "https://mail.google.com")  # bytes work mail
    print("  [OK] Opened Gmail (bytes)")
    time.sleep(0.5)

    open_profile(ACCOUNT_B, "https://claude.ai")  # personal account
    print("  [OK] Opened Claude.ai (personal)")
    time.sleep(0.5)

    open_profile(ACCOUNT_B, "https://chatgpt.com")  # personal account
    print("  [OK] Opened ChatGPT (personal)")
    time.sleep(0.5)

    _launch_vscode(os_type)
    print("  [OK] Launched VS Code\n")
```

Replace it with (only the three `open_profile` calls and the inline comments change — the rest is byte-identical):

```python
def launch_work_apps(os_type):
    """Open Gmail (bytes account), Claude.ai + ChatGPT (personal account), VS Code."""
    print("\n[WORK MODE] Launching apps...\n")

    open_profile(ACCOUNT_WORK, "https://mail.google.com")  # bytes work mail
    print("  [OK] Opened Gmail (bytes)")
    time.sleep(0.5)

    open_profile(ACCOUNT_PERSONAL, "https://claude.ai")  # personal account
    print("  [OK] Opened Claude.ai (personal)")
    time.sleep(0.5)

    open_profile(ACCOUNT_PERSONAL, "https://chatgpt.com")  # personal account
    print("  [OK] Opened ChatGPT (personal)")
    time.sleep(0.5)

    _launch_vscode(os_type)
    print("  [OK] Launched VS Code\n")
```

- [ ] **Step 3: Verify the module imports cleanly and the warn-check fires correctly**

Run:
```powershell
.\.venv\Scripts\python.exe -c "from friday import launcher; print('OK', launcher.ACCOUNT_WORK, '|', launcher.ACCOUNT_PERSONAL)"
```
Expected output (one line):
```
OK Profile 5 | Default
```
(No `[WARN]` line should appear, because Profile 5 and Default both exist on disk.)

- [ ] **Step 4: Verify the warn path fires when a profile is missing**

Temporarily monkey-patch a missing profile and import again:
```powershell
.\.venv\Scripts\python.exe -c "import friday.config as c; c.CHROME_PERSONAL_PROFILE = 'NoSuchProfile_test'; from friday import launcher"
```
Expected output (one line):
```
[WARN] Chrome profile 'NoSuchProfile_test' not found at C:\Users\malya\AppData\Local\Google\Chrome\User Data\NoSuchProfile_test -- work mode tabs will open unauthenticated
```

- [ ] **Step 5: Commit**

```bash
git add friday/launcher.py
git commit -m "launcher: use Chrome profile config; fix profile-dir mappings"
```

---

### Task 4: Change tray auto-start delay from 3s to 30s in `friday_tray.pyw`

**Files:**
- Modify: `friday_tray.pyw`

- [ ] **Step 1: Replace the auto-start block**

Current lines 203–205 are:

```python
    # Auto-start Friday 3 seconds after tray loads.
    # Safe now because the mutex above guarantees only one tray ever runs.
    threading.Timer(3.0, lambda: start_friday(_icon_ref)).start()
```

Replace with:

```python
    # Auto-start Friday after a delay, so heavy boot items (Docker Desktop,
    # OneDrive, Teams, audio drivers) finish their initial spike before
    # Whisper starts loading its model. Safe because the mutex above
    # guarantees only one tray ever runs.
    _AUTOSTART_DELAY = 30.0  # seconds
    _log(f"Auto-start scheduled in {_AUTOSTART_DELAY}s")
    threading.Timer(_AUTOSTART_DELAY, lambda: start_friday(_icon_ref)).start()
```

- [ ] **Step 2: Verify the file parses**

Run:
```powershell
.\.venv\Scripts\python.exe -c "import ast, pathlib; ast.parse(pathlib.Path('friday_tray.pyw').read_text(encoding='utf-8')); print('OK')"
```
Expected output:
```
OK
```

- [ ] **Step 3: Commit**

```bash
git add friday_tray.pyw
git commit -m "tray: increase auto-start delay 3s -> 30s to avoid boot I/O contention"
```

---

### Task 5: Wildcard cleanup in `setup_startup.ps1`

**Files:**
- Modify: `setup_startup.ps1` (Step 2 block, currently lines 51–90)

- [ ] **Step 1: Replace the Task Scheduler cleanup block**

Current code in `setup_startup.ps1`, lines 60–71 (the hardcoded `$taskNames` array):

```powershell
# Task Scheduler - try multiple possible names/paths from old setups
$taskNames = @(
    "\Friday\Friday Tray Icon",
    "\Friday Tray Icon",
    "Friday Tray Icon"
)
foreach ($taskName in $taskNames) {
    $exists = Get-ScheduledTask -TaskName ($taskName.Split("\")[-1]) -ErrorAction SilentlyContinue
    if ($exists) {
        Unregister-ScheduledTask -TaskName ($taskName.Split("\")[-1]) -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "  [OK] Removed Task Scheduler entry: $taskName" -ForegroundColor Green
    }
}
```

Replace with:

```powershell
# Task Scheduler - discover ANY task whose name or action references Friday
# or this project folder. Wildcard sweep is idempotent and survives renames.
$friday_tasks = Get-ScheduledTask | Where-Object {
    $_.TaskName -like "*Friday*" -or
    (($_.Actions | ForEach-Object { $_.Execute }) -like "*friday*") -or
    (($_.Actions | ForEach-Object { $_.Execute }) -like "*wake-up*")
}
foreach ($t in $friday_tasks) {
    Unregister-ScheduledTask -TaskName $t.TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "  [OK] Removed Task Scheduler entry: $($t.TaskName)" -ForegroundColor Green
}
if (-not $friday_tasks) {
    Write-Host "  [OK] No Friday-related scheduled tasks to remove" -ForegroundColor Green
}
```

- [ ] **Step 2: Replace the Startup-folder shortcut cleanup block**

Current code in `setup_startup.ps1`, lines 73–88 (the hardcoded `$staleShortcuts` array):

```powershell
# Startup folder shortcuts -- remove ALL known Friday entries.
# These bypass the tray mutex (especially the BAT-launching one), so they
# must be removed or they'll spawn extra Friday instances at login.
$startup       = [Environment]::GetFolderPath("Startup")
$staleShortcuts = @(
    "Friday Tray.lnk",
    "Friday Tray Startup.lnk",
    "Friday Assistant Startup.lnk"
)
foreach ($name in $staleShortcuts) {
    $lnk = Join-Path $startup $name
    if (Test-Path $lnk) {
        Remove-Item $lnk -Force -ErrorAction SilentlyContinue
        Write-Host "  [OK] Removed Startup folder shortcut: $name" -ForegroundColor Green
    }
}
```

Replace with:

```powershell
# Startup folder shortcuts -- remove ANY .lnk whose target references Friday
# or this project folder. These bypass the tray mutex if not removed.
$startup = [Environment]::GetFolderPath("Startup")
$wsh_check = New-Object -ComObject WScript.Shell
$removed_lnk = 0
Get-ChildItem -Path $startup -Filter "*.lnk" -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $sc_check = $wsh_check.CreateShortcut($_.FullName)
        $target   = "$($sc_check.TargetPath) $($sc_check.Arguments)"
    } catch {
        return  # skip unreadable shortcuts
    }
    if ($_.Name -like "*Friday*" -or $target -like "*friday_tray*" -or $target -like "*wake-up*") {
        Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
        Write-Host "  [OK] Removed Startup folder shortcut: $($_.Name)" -ForegroundColor Green
        $removed_lnk++
    }
}
if ($removed_lnk -eq 0) {
    Write-Host "  [OK] No Friday-related Startup folder shortcuts to remove" -ForegroundColor Green
}
```

- [ ] **Step 3: Verify the script still parses**

Run:
```powershell
powershell -Command "& { try { [void][System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path '.\setup_startup.ps1').Path, [ref]$null, [ref]$null); 'PARSE OK' } catch { 'PARSE FAIL: ' + $_.Exception.Message } }"
```
Expected output:
```
PARSE OK
```

- [ ] **Step 4: Dry-run the discovery blocks** (does not modify state — only enumerates)

Run:
```powershell
Get-ScheduledTask | Where-Object { $_.TaskName -like "*Friday*" -or (($_.Actions | ForEach-Object { $_.Execute }) -like "*friday*") -or (($_.Actions | ForEach-Object { $_.Execute }) -like "*wake-up*") } | Select-Object TaskName, @{N='Execute';E={$_.Actions.Execute}} | Format-Table -AutoSize
```
Expected output: empty (Task 1 already removed the only orphan).

```powershell
$s = [Environment]::GetFolderPath("Startup"); $w = New-Object -ComObject WScript.Shell; Get-ChildItem $s -Filter "*.lnk" -ErrorAction SilentlyContinue | ForEach-Object { $sc = $w.CreateShortcut($_.FullName); [PSCustomObject]@{ Name=$_.Name; Target=$sc.TargetPath; Args=$sc.Arguments } } | Where-Object { $_.Name -like "*Friday*" -or "$($_.Target) $($_.Args)" -like "*friday_tray*" -or "$($_.Target) $($_.Args)" -like "*wake-up*" } | Format-Table -AutoSize
```
Expected output: empty (no Friday-related shortcuts in Startup folder per the earlier audit).

- [ ] **Step 5: Commit**

```bash
git add setup_startup.ps1
git commit -m "setup-startup: wildcard-discover Friday tasks/shortcuts (idempotent)"
```

---

### Task 6: Final verification (idempotency + reboot)

This is the end-to-end check. No code edits; only verification.

**Files:** none

- [ ] **Step 1: Re-run the cleanup script and confirm it succeeds with zero errors**

Run:
```powershell
powershell -ExecutionPolicy Bypass -File .\setup_startup.ps1
```
Expected: completes through all 5 steps, prints `[OK] No Friday-related scheduled tasks to remove` and `[OK] No Friday-related Startup folder shortcuts to remove` in Step 2, finishes with the `All done!` banner. No red `[WARN]` or `[ERROR]` lines.

- [ ] **Step 2: Reboot the machine**

After reboot, observe:

| Expectation                                                                                          | Pass criterion                                                                       |
| ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| No phantom `cmd.exe` window flashes at login                                                         | Watch the screen for ~30 seconds after login. Nothing appears and disappears.        |
| Friday tray icon appears within a few seconds                                                        | Check the system tray for the Friday icon (gray = stopped).                          |
| Approximately 30 seconds after the tray loads, a `start_friday.bat` console opens and Friday starts | Tray icon turns green; you hear the wake-word loading messages in the console.       |
| `friday_tray_error.log` contains the new log line                                                    | Tail the log: `Get-Content friday_tray_error.log -Tail 3` should show `Auto-start scheduled in 30.0s` |

- [ ] **Step 3: Voice-test work mode**

After Friday is loaded, say:
1. "Friday"  → should respond "Yes boss, I'm listening"
2. "Let's start the work"

Expected:
- Gmail opens already signed in to `malya.patel@bytestechnolab.com` (NOT a Google login page)
- Claude.ai opens already signed in to `malyapatel17@gmail.com`
- ChatGPT opens already signed in to `malyapatel17@gmail.com`
- VS Code launches

If any tab shows a login page instead, check Step 4 below.

- [ ] **Step 4: (Conditional) If any tab is not signed in**

Run the discovery to confirm the configured profile is the one that holds the session:
```powershell
$ud = "$env:LOCALAPPDATA\Google\Chrome\User Data"; "Profile 5", "Default" | ForEach-Object { $p = Join-Path $ud "$_\Preferences"; if (Test-Path $p) { $j = Get-Content $p -Raw | ConvertFrom-Json; [PSCustomObject]@{ Dir=$_; Email=$j.account_info[0].email } } }
```
Expected output:
```
Dir       Email
---       -----
Profile 5 malya.patel@bytestechnolab.com
Default   malyapatel17@gmail.com
```

If either email is missing, sign in once manually in that Chrome profile and re-test. Chrome's session cookies will persist after that.

- [ ] **Step 5: Final commit (only if anything changed in this task)**

Task 6 does not modify files. Nothing to commit here unless Step 4 surfaced a config tweak — in which case commit it as:

```bash
git add friday/config.py
git commit -m "config: adjust Chrome profile dir after verification"
```

---

## Notes for the implementing engineer

- **Order matters.** Task 1 (orphan task removal) must precede Task 6 (reboot) or the reboot test will still show the cmd-flash and you will wrongly believe the fix failed.
- **No test framework.** Per `CLAUDE.md`: "There are no tests, lints, or build steps configured." Use the manual verification steps as your pass/fail signal. Do not pip-install pytest.
- **Do not run `friday_tray.pyw` directly during Tasks 4 or 5** — the mutex `FridayTrayMutex_v1` is process-scoped, so a running tray will block the reboot-test verification. Stop any existing tray from its own menu first if you want to spot-check.
- **Hardcoded paths are intentional.** Per `CLAUDE.md`: "`friday_tray.pyw` and `friday/launcher.py` contain hardcoded absolute paths … they exist because the tray runs detached from the project's working directory." Do not 'fix' them to relative paths.
- **Do not amend commits.** Per the user's git safety rules in the system prompt, create new commits rather than amending.
