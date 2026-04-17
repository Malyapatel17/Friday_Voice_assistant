# Friday Assistant — Windows Startup Setup
# Run ONCE as Administrator

$batPath = "C:\Users\malya\.vscode\python practise\Friday\wake-up\start_friday.bat"

schtasks /create /tn "Friday Assistant" /tr `"$batPath`" /sc onlogon /delay 0000:05 /rl highest /f

Write-Host ""
Write-Host "Friday Assistant registered in Task Scheduler!" -ForegroundColor Green
Write-Host "Friday will start automatically 5 seconds after you log in." -ForegroundColor Cyan
Write-Host ""
Write-Host "To remove: schtasks /delete /tn ""Friday Assistant"" /f" -ForegroundColor Yellow
