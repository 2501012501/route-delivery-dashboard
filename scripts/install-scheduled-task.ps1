# Install the auto-refresh scheduled task in Windows Task Scheduler.
#
# Usage (open PowerShell in this folder, then run):
#     .\install-scheduled-task.ps1
#
# Default schedule: every hour, every day from 7:00 AM to 8:00 PM Central.
# To uninstall later: .\install-scheduled-task.ps1 -Uninstall

param(
    [switch]$Uninstall
)

$TaskName = "RouteToDelivery-AutoRefresh"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BatPath = Join-Path $ScriptDir "auto-refresh.bat"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed task '$TaskName'."
    } else {
        Write-Host "Task '$TaskName' not found - nothing to remove."
    }
    return
}

if (-not (Test-Path $BatPath)) {
    Write-Error "Cannot find auto-refresh.bat at: $BatPath"
    return
}

# Action: run the .bat (which runs Python + git push)
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$BatPath`""

# Trigger: every hour from 7am to 8pm
$Trigger = New-ScheduledTaskTrigger -Once -At 7am `
                                     -RepetitionInterval (New-TimeSpan -Hours 1) `
                                     -RepetitionDuration (New-TimeSpan -Hours 13)

# Settings: only run when network available; allow on demand
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

# Run as the current user, only when logged on (so VPN credentials are available)
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

# Register (replace if already exists)
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
Register-ScheduledTask -TaskName $TaskName `
                       -Action $Action `
                       -Trigger $Trigger `
                       -Settings $Settings `
                       -Principal $Principal `
                       -Description "Hourly auto-refresh of Route to Delivery dashboard data and push to GitHub for Streamlit Cloud."

Write-Host ""
Write-Host "Task '$TaskName' installed." -ForegroundColor Green
Write-Host "Schedule: every hour, 7:00 AM to 8:00 PM (Central)."
Write-Host "Logs:     $ScriptDir\..\logs\auto-refresh.log"
Write-Host ""
Write-Host "To run it once now from PowerShell:"
Write-Host "    Start-ScheduledTask -TaskName $TaskName"
Write-Host ""
Write-Host "To remove it later:"
Write-Host "    .\install-scheduled-task.ps1 -Uninstall"
