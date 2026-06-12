# Friday Assistant - Phase 1 Startup Cleanup + Re-register
# This script removes ALL old startup entries (Registry + Task Scheduler +
# Startup folder) and registers a clean single Registry Run key.
#
# Run from PowerShell:
#   powershell -ExecutionPolicy Bypass -File "C:\Users\malya\.vscode\python practise\Friday\wake-up\setup_startup.ps1"

$ErrorActionPreference = "SilentlyContinue"

$project  = "C:\Users\malya\.vscode\python practise\Friday\wake-up"
$trayFile = "$project\friday_tray.pyw"
$venvPyw  = "$project\.venv\Scripts\pythonw.exe"
$venvPip  = "$project\.venv\Scripts\pip.exe"

# Find pythonw.exe
if (Test-Path $venvPyw) {
    $pythonW = $venvPyw
    $pip     = $venvPip
} else {
    $pywCmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($pywCmd) {
        $pythonW = $pywCmd.Source
    } else {
        $py      = (Get-Command python.exe).Source
        $pythonW = $py -replace "python\.exe$", "pythonw.exe"
    }
    $pip = "pip"
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Friday Assistant - Startup Fix"            -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Project : $project"
Write-Host " PythonW : $pythonW"
Write-Host ""

# ── STEP 1: Kill any running tray instances ───────────────────────────────────
Write-Host "Step 1/5  Killing any running tray instances ..." -ForegroundColor Yellow
Get-Process -Name "pythonw" -ErrorAction SilentlyContinue | ForEach-Object {
    $cmdline = (Get-WmiObject Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
    if ($cmdline -like "*friday_tray*") {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        Write-Host "  Killed tray PID $($_.Id)" -ForegroundColor Gray
    }
}
Start-Sleep -Seconds 1
Write-Host "  [OK] Done" -ForegroundColor Green
Write-Host ""

# ── STEP 2: Remove ALL old startup entries ────────────────────────────────────
Write-Host "Step 2/5  Removing all old startup entries ..." -ForegroundColor Yellow

# Registry Run key
$regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
Remove-ItemProperty -Path $regPath -Name "FridayTray" -ErrorAction SilentlyContinue
Write-Host "  [OK] Registry Run key removed (if existed)" -ForegroundColor Green

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

Write-Host "  [OK] All old entries cleared" -ForegroundColor Green
Write-Host ""

# ── STEP 3: Install tray dependencies ────────────────────────────────────────
Write-Host "Step 3/5  Installing tray dependencies ..." -ForegroundColor Yellow
& $pip install pystray pillow --quiet
Write-Host "  [OK] Done" -ForegroundColor Green
Write-Host ""

# ── STEP 4: Register ONE Registry Run key (only) ─────────────────────────────
# We use ONLY the Registry key now. No Task Scheduler.
# The mutex in friday_tray.pyw prevents any duplicate even if something
# launches a second copy — it will just exit silently.
Write-Host "Step 4/5  Registering single startup entry ..." -ForegroundColor Yellow

$regValue = "`"$pythonW`" `"$trayFile`""
$ErrorActionPreference = "Stop"
try {
    Set-ItemProperty -Path $regPath -Name "FridayTray" -Value $regValue
    Write-Host "  [OK] Registry Run key set" -ForegroundColor Green
    Write-Host "       $regValue" -ForegroundColor Gray
} catch {
    Write-Host "  [WARN] Registry write failed: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "  Falling back to Startup folder shortcut ..." -ForegroundColor Yellow
    $wsh = New-Object -ComObject WScript.Shell
    $sc  = $wsh.CreateShortcut("$startup\Friday Tray.lnk")
    $sc.TargetPath       = $pythonW
    $sc.Arguments        = "`"$trayFile`""
    $sc.WorkingDirectory = $project
    $sc.Description      = "Friday tray icon startup"
    $sc.Save()
    Write-Host "  [OK] Startup folder shortcut created" -ForegroundColor Green
}
$ErrorActionPreference = "SilentlyContinue"
Write-Host ""

# ── STEP 5: Desktop shortcut ──────────────────────────────────────────────────
Write-Host "Step 5/5  Updating desktop shortcut ..." -ForegroundColor Yellow
$wsh     = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath("Desktop")
$sc      = $wsh.CreateShortcut("$desktop\Friday.lnk")
$sc.TargetPath       = $pythonW
$sc.Arguments        = "`"$trayFile`""
$sc.WorkingDirectory = $project
$sc.Description      = "Open Friday tray icon"
$sc.IconLocation     = "%SystemRoot%\System32\imageres.dll,109"
$sc.WindowStyle      = 7
$sc.Save()
Write-Host "  [OK] Desktop shortcut updated" -ForegroundColor Green
Write-Host ""

# ── Done ─────────────────────────────────────────────────────────────────────
Write-Host "============================================" -ForegroundColor Green
Write-Host " All done!"                                  -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "What changed:" -ForegroundColor Cyan
Write-Host "  - All old startup entries (Scheduler + folder) removed"
Write-Host "  - Only ONE Registry key now launches the tray at login"
Write-Host "  - Tray has a mutex: even if launched twice, only one runs"
Write-Host "  - Auto-start removed from tray: click Start Friday manually"
Write-Host ""
Write-Host "Test now (without rebooting):" -ForegroundColor Cyan
Write-Host "  Double-click Friday shortcut on your desktop"
Write-Host "  Right-click tray icon -> Start Friday"
Write-Host ""

Read-Host "Press Enter to close"