# Friday Assistant - Phase 1 Setup
# Run from PowerShell:
#   powershell -ExecutionPolicy Bypass -File "C:\Users\malya\.vscode\python practise\Friday\wake-up\setup_startup.ps1"

$ErrorActionPreference = "Stop"

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
Write-Host " Friday Assistant - Phase 1 Setup"          -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Project : $project"
Write-Host " PythonW : $pythonW"
Write-Host ""

# Step 1 - Install tray dependencies
Write-Host "Step 1/3  Installing tray dependencies ..." -ForegroundColor Yellow
& $pip install pystray pillow --quiet
Write-Host "Done" -ForegroundColor Green
Write-Host ""

# Step 2 - Register startup
Write-Host "Step 2/3  Registering startup ..." -ForegroundColor Yellow

# PRIMARY - Registry HKCU Run key
$regPath  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$regValue = "`"$pythonW`" `"$trayFile`""

try {
    Set-ItemProperty -Path $regPath -Name "FridayTray" -Value $regValue
    Write-Host "  [OK] Registry Run key set (primary - fires at login)" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] Registry write failed: $($_.Exception.Message)" -ForegroundColor Yellow
}

# SECONDARY - Task Scheduler with 5 second delay
$taskPath = "\Friday\"

$action = New-ScheduledTaskAction -Execute $pythonW -Argument "`"$trayFile`"" -WorkingDirectory $project

$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = "PT5S"

$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 24) -StartWhenAvailable

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

try {
    Register-ScheduledTask -TaskName "Friday Tray Icon" -TaskPath $taskPath -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Start Friday tray icon after login" -Force | Out-Null
    Write-Host "  [OK] Task Scheduler entry set (secondary - 5 second delay)" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] Task Scheduler failed - using Startup folder fallback" -ForegroundColor Yellow
    $wsh     = New-Object -ComObject WScript.Shell
    $startup = [Environment]::GetFolderPath("Startup")
    $sc      = $wsh.CreateShortcut("$startup\Friday Tray.lnk")
    $sc.TargetPath       = $pythonW
    $sc.Arguments        = "`"$trayFile`""
    $sc.WorkingDirectory = $project
    $sc.Description      = "Friday tray icon startup"
    $sc.Save()
    Write-Host "  [OK] Startup folder shortcut created" -ForegroundColor Green
}

Write-Host ""

# Step 3 - Desktop shortcut
Write-Host "Step 3/3  Creating desktop shortcut ..." -ForegroundColor Yellow

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

Write-Host "  [OK] Desktop shortcut created" -ForegroundColor Green
Write-Host ""

Write-Host "============================================" -ForegroundColor Green
Write-Host " Setup complete!"                            -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "What happens at next login:" -ForegroundColor Cyan
Write-Host "  1. Registry Run key fires  -> tray icon appears instantly"
Write-Host "  2. Tray auto-starts Friday after 2 seconds"
Write-Host "  3. Task Scheduler fires at 5 seconds as backup"
Write-Host ""
Write-Host "To remove auto-start later:" -ForegroundColor Yellow
Write-Host "  Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'FridayTray'"
Write-Host "  schtasks /delete /tn `\`"\Friday\Friday Tray Icon`\`" /f"
Write-Host ""

Read-Host "Press Enter to close"