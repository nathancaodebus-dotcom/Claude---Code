<#
.SYNOPSIS
    Removes the Scheduled Tasks created by install_orion_tasks.ps1.
#>

$ErrorActionPreference = "Stop"

foreach ($name in @("web", "telegram", "voice")) {
    $taskName = "Orion-" + (Get-Culture).TextInfo.ToTitleCase($name)
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Removed '$taskName'"
    } else {
        Write-Host "'$taskName' not registered, skipping"
    }
}
