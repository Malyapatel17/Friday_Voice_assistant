# ==============================================================================
# Friday Assistant - One-Time Setup
# Right-click this file -> Run with PowerShell (no Admin needed)
# ==============================================================================

$ErrorActionPreference = "Stop"

# Paths
$project  = "C:\Users\malya\.vscode\python practise\Friday\wake-up"
$batFile  = "$project\start_friday.bat"
$trayFile = "$project\friday_tray.pyw"

# Find pythonw.exe
$venvPythonW = "$project\.venv\Scripts\pythonw.exe"

if (Test-Path $venvPythonW) {
    $pythonW = $venvPythonW
    $pythonPip = "$project\.venv\Scripts\pip.exe"
}
else {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        $pythonW = $cmd.Source
    }

    $pythonPip = "pip"

    if (-not $pythonW) {
        $pyExe = (Get-Command python.exe).Source
        $pythonW = $pyExe -replace "python\.exe$", "pythonw.exe"
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Friday Assistant - Setup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Project : $project"
Write-Host " PythonW : $pythonW"
Write-Host ""

# Step 1
Write-Host "Step 1/3 Installing tray dependencies..." -ForegroundColor Yellow
& $pythonPip install pystray pillow --quiet
Write-Host "Done`n" -ForegroundColor Green

# Step 2
Write-Host "Step 2/3 Registering startup tasks..." -ForegroundColor Yellow
$taskPath = "\Friday\"
$scheduledTaskRegistrationFailed = $false
$wsh = New-Object -ComObject WScript.Shell

# Main app task
$action30 = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$batFile`"" `
    -WorkingDirectory $project

$trigger30 = New-ScheduledTaskTrigger -AtLogOn
$trigger30.Delay = "PT20S"

$settings30 = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 24) `
    -StartWhenAvailable

$principal30 = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

try {
    Register-ScheduledTask `
        -TaskName "Friday Assistant" `
        -TaskPath $taskPath `
        -Action $action30 `
        -Trigger $trigger30 `
        -Settings $settings30 `
        -Principal $principal30 `
        -Description "Auto-start Friday 30 seconds after login" `
        -Force | Out-Null

    Write-Host "Friday main task registered" -ForegroundColor Green
}
catch {
    Write-Host "Failed to register 'Friday Assistant': $($_.Exception.Message)" -ForegroundColor Red
    $scheduledTaskRegistrationFailed = $true
}

# Tray task
$action15 = New-ScheduledTaskAction `
    -Execute $pythonW `
    -Argument "`"$trayFile`"" `
    -WorkingDirectory $project

$trigger15 = New-ScheduledTaskTrigger -AtLogOn
$trigger15.Delay = "PT15S"

$settings15 = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 24) `
    -StartWhenAvailable

$principal15 = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

try {
    Register-ScheduledTask `
        -TaskName "Friday Tray Icon" `
        -TaskPath $taskPath `
        -Action $action15 `
        -Trigger $trigger15 `
        -Settings $settings15 `
        -Principal $principal15 `
        -Description "Start Friday tray icon after login" `
        -Force | Out-Null

    Write-Host "Tray icon task registered`n" -ForegroundColor Green
}
catch {
    Write-Host "Failed to register 'Friday Tray Icon': $($_.Exception.Message)" -ForegroundColor Red
    $scheduledTaskRegistrationFailed = $true
}

if ($scheduledTaskRegistrationFailed) {
    $startupFolder = [Environment]::GetFolderPath("Startup")

    $startupMain = $wsh.CreateShortcut("$startupFolder\Friday Assistant Startup.lnk")
    $startupMain.TargetPath = "cmd.exe"
    $startupMain.Arguments = "/c timeout /t 30 /nobreak >nul && `"$batFile`""
    $startupMain.WorkingDirectory = $project
    $startupMain.Description = "Fallback startup for Friday Assistant"
    $startupMain.Save()

    $startupTray = $wsh.CreateShortcut("$startupFolder\Friday Tray Startup.lnk")
    $startupTray.TargetPath = "cmd.exe"
    $startupTray.Arguments = "/c timeout /t 15 /nobreak >nul && `"$pythonW`" `"$trayFile`""
    $startupTray.WorkingDirectory = $project
    $startupTray.Description = "Fallback startup for Friday Tray Icon"
    $startupTray.Save()

    Write-Host "Startup folder fallback created (Task Scheduler access denied).`n" -ForegroundColor Yellow
}

# Step 3
Write-Host "Step 3/3 Creating desktop shortcut..." -ForegroundColor Yellow

$desktop = [Environment]::GetFolderPath("Desktop")

$sc = $wsh.CreateShortcut("$desktop\Friday.lnk")
$sc.TargetPath = $pythonW
$sc.Arguments = "`"$trayFile`""
$sc.WorkingDirectory = $project
$sc.Description = "Open Friday tray icon - Start / Stop the assistant"
$sc.IconLocation = "%SystemRoot%\System32\imageres.dll,109"
$sc.WindowStyle = 7
$sc.Save()

Write-Host "'Friday' shortcut created on Desktop`n" -ForegroundColor Green

# Done
Write-Host "============================================" -ForegroundColor Green
Write-Host " Setup complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "What happens next:" -ForegroundColor Cyan
Write-Host "* Friday auto-launches 30 seconds after login."
Write-Host "* Tray icon appears after 15 seconds."
Write-Host "* Right-click tray icon -> Start / Stop Friday."
Write-Host "* Desktop shortcut created."
Write-Host ""
Write-Host "To disable auto-start later:" -ForegroundColor Yellow
Write-Host "schtasks /delete /tn `"\Friday\Friday Assistant`" /f"
Write-Host "schtasks /delete /tn `"\Friday\Friday Tray Icon`" /f"
Write-Host ""

Read-Host "Press Enter to close"