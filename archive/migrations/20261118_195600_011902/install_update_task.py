"""Tạo lịch Windows Task Scheduler cho update_data.py, không cần kích hoạt venv."""
import argparse
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent
POWERSHELL = r'''
$ErrorActionPreference = "Stop"
$projectRoot = $env:VN30_RADAR_TASK_ROOT
$At = $env:VN30_RADAR_TASK_TIME
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$updatePath = Join-Path $projectRoot "update_data.py"
$dbPath = Join-Path $projectRoot "storage\radar.db"
foreach ($required in @($pythonPath, $updatePath, $dbPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing file: $required. Put both downloaded Python files in the project root."
    }
}
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$arguments = '"' + $updatePath + '" --db "' + $dbPath + '"'
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument $arguments -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $At
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
    -Description "Update SSI market data for VN30 Radar. Backup SQLite and write a log before each run."
Register-ScheduledTask -TaskName "VN30Radar-UpdateSSI" -InputObject $task -Force | Out-Null
Write-Host "Installed task: VN30Radar-UpdateSSI"
Write-Host "Schedule: Monday-Friday at $At, using the Windows local time zone."
Write-Host "Windows time zone: $((Get-TimeZone).Id)"
Write-Host "The computer must be on, awake, online, and this Windows user must be signed in."
Get-ScheduledTaskInfo -TaskName "VN30Radar-UpdateSSI" | Select-Object TaskName, LastRunTime, LastTaskResult, NextRunTime
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--at", default="18:00", help="Giờ chạy theo giờ máy Windows, dạng HH:MM")
    args = parser.parse_args()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", args.at):
        parser.error("Giờ chạy phải theo dạng HH:MM, ví dụ 18:00.")
    if os.name != "nt":
        parser.error("Chạy file này trên máy Windows chứa đồ án của bạn.")
    env = os.environ.copy()
    env["VN30_RADAR_TASK_ROOT"] = str(ROOT)
    env["VN30_RADAR_TASK_TIME"] = args.at
    result = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", POWERSHELL],
        env=env, check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
