# Stop Windows from rebooting this laptop while it sits open overnight.
# Event log 2026-08-12/13: TrustedInstaller / MoUsoCoreWorker "Operating System: Upgrade (Planned)".
# Run once. May need "Run as administrator" for the Windows Update keys.

$ErrorActionPreference = "Continue"

Write-Host "Zeroing sleep / hibernate / unattended-sleep (AC and battery)..."
$sets = @(
  @("SUB_SLEEP", "STANDBYIDLE", 0),
  @("SUB_SLEEP", "HIBERNATEIDLE", 0),
  @("SUB_SLEEP", "UNATTENDSLEEP", 0),
  @("SUB_SLEEP", "HYBRIDSLEEP", 0)
)
foreach ($s in $sets) {
  powercfg /SETACVALUEINDEX SCHEME_CURRENT $s[0] $s[1] $s[2] | Out-Null
  powercfg /SETDCVALUEINDEX SCHEME_CURRENT $s[0] $s[1] $s[2] | Out-Null
}
powercfg /SETACTIVE SCHEME_CURRENT | Out-Null

Write-Host "Blocking Windows Update auto-reboot while you are logged on..."
$au = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"
New-Item -Path $au -Force | Out-Null
Set-ItemProperty -Path $au -Name "NoAutoRebootWithLoggedOnUsers" -Value 1 -Type DWord -Force
Set-ItemProperty -Path $au -Name "AUOptions" -Value 3 -Type DWord -Force

$ux = "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings"
if (Test-Path $ux) {
    Set-ItemProperty -Path $ux -Name "IsActiveHoursEnabled" -Value 1 -Type DWord -Force
    Set-ItemProperty -Path $ux -Name "ActiveHoursStart" -Value 0 -Type DWord -Force
    Set-ItemProperty -Path $ux -Name "ActiveHoursEnd" -Value 23 -Type DWord -Force
    $pauseUntil = (Get-Date).ToUniversalTime().AddDays(7).ToString("yyyy-MM-ddTHH:mm:ssZ")
    Set-ItemProperty -Path $ux -Name "PauseUpdatesExpiryTime" -Value $pauseUntil -Type String -Force
}

Write-Host "Done. Sleep-after should be Never. Windows Update should not reboot while you are logged in."
Write-Host "If a key failed with Access Denied, right-click this script -> Run with PowerShell as Administrator."
