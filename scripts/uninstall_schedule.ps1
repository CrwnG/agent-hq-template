# Removes the two scheduled tasks registered by install_schedule.ps1.
. (Join-Path $PSScriptRoot 'crew.config.ps1')
foreach ($name in "$ProjectName-DailyCrew", "$ProjectName-HQ") {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Output "removed $name"
    }
}
