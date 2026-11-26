"""Đăng ký/kiểm tra lịch SSI bằng đường dẫn hiện tại; chạy trên Windows."""
import argparse
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
TASK_NAME = 'VN30Radar-UpdateSSI'
STATUS = r'''
$ErrorActionPreference = "Stop"
$name = "VN30Radar-UpdateSSI"
$task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "CHUA CAI LICH: VN30Radar-UpdateSSI"
    exit 3
}
Write-Host "Windows time zone: $((Get-TimeZone).Id)"
$task | Select-Object TaskName, State | Format-List | Out-Host
$task.Actions | Select-Object Execute, Arguments, WorkingDirectory | Format-List | Out-Host
Get-ScheduledTaskInfo -TaskName $name | Select-Object LastRunTime, LastTaskResult, NextRunTime | Format-List | Out-Host
$expected = Join-Path $env:VN30_RADAR_TASK_ROOT "scripts\data\update_data.py"
$expectedPython = Join-Path $env:VN30_RADAR_TASK_ROOT ".venv\Scripts\python.exe"
$expectedDb = Join-Path $env:VN30_RADAR_TASK_ROOT $env:VN30_RADAR_TASK_DB
$valid = $false
foreach ($action in $task.Actions) {
    if ($action.Execute -ieq $expectedPython -and $action.Arguments -and
        $action.WorkingDirectory -ieq $env:VN30_RADAR_TASK_ROOT -and
        $action.Arguments.IndexOf($expected, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $action.Arguments.IndexOf($expectedDb, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
        $valid = $true
    }
}
if (-not $valid) {
    Write-Host "SAI DUONG DAN: lich cu co the van tro den update_data.py o thu muc goc. Dang ky lai lich."
    exit 4
}
Write-Host "DUONG DAN LICH DUNG. LastTaskResult=0 chi xac nhan tien trinh, khong dam bao SSI da tra phien moi."
'''
POWERSHELL = r'''
$ErrorActionPreference = "Stop"
$projectRoot = $env:VN30_RADAR_TASK_ROOT
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$updatePath = Join-Path $projectRoot "scripts\data\update_data.py"
$dbPath = Join-Path $projectRoot $env:VN30_RADAR_TASK_DB
foreach ($required in @($pythonPath, $updatePath, $dbPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing file: $required. Extract the update package into the project folder."
    }
}
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$arguments = '"' + $updatePath + '" --db "' + $dbPath + '"'
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument $arguments -WorkingDirectory $projectRoot
$triggers = @(
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $env:VN30_RADAR_TASK_TIME
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $env:VN30_RADAR_TASK_RETRY_TIME
    New-ScheduledTaskTrigger -AtLogOn -User $identity
)
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$task = New-ScheduledTask -Action $action -Trigger $triggers -Principal $principal -Settings $settings `
    -Description "SSI update: current script path, evening retry and catch-up at logon. Backup SQLite and record logs."
Register-ScheduledTask -TaskName "VN30Radar-UpdateSSI" -InputObject $task -Force | Out-Null
Write-Host "Installed task: VN30Radar-UpdateSSI"
Write-Host "Monday-Friday at $env:VN30_RADAR_TASK_TIME and $env:VN30_RADAR_TASK_RETRY_TIME; catch up at user logon."
Write-Host "Windows time zone: $((Get-TimeZone).Id)"
Write-Host "Computer must be on, awake, online; this Windows user must be signed in."
if ($env:VN30_RADAR_TASK_RUN_NOW -eq "1") {
    Start-ScheduledTask -TaskName "VN30Radar-UpdateSSI"
    Write-Host "Requested an update NOW. It runs in the background; inspect report/update_logs."
}
Get-ScheduledTaskInfo -TaskName "VN30Radar-UpdateSSI" | Select-Object LastRunTime, LastTaskResult, NextRunTime | Format-List | Out-Host
'''


def main(argv=None, runner=subprocess.run, platform=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--at', default='18:00', help='Giờ Windows chạy chính, HH:MM')
    parser.add_argument('--retry-at', default='19:00', help='Giờ Windows chạy lại để lấy dữ liệu SSI công bố muộn')
    parser.add_argument('--db', default='storage/radar.db', help='DB bên trong dự án, dùng cùng file trên dashboard')
    parser.add_argument('--status', action='store_true', help='Chỉ kiểm tra lịch và đường dẫn, không tạo/chạy lịch')
    parser.add_argument('--run-now', action='store_true', help='Sau đăng ký, yêu cầu Windows chạy bù ngay trong nền')
    args = parser.parse_args(argv)
    for value in (args.at, args.retry_at):
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
            parser.error('Giờ chạy phải theo dạng HH:MM, ví dụ 18:00.')
    if args.status and args.run_now:parser.error('Không kết hợp --status và --run-now')
    if (os.name if platform is None else platform) != 'nt':
        parser.error('Chạy script này trên máy Windows chứa đồ án.')
    db_path=(ROOT/args.db).resolve()
    if not db_path.is_relative_to(ROOT):parser.error('--db phải nằm trong thư mục dự án')
    env=os.environ.copy()
    env.update(VN30_RADAR_TASK_ROOT=str(ROOT),VN30_RADAR_TASK_TIME=args.at,
               VN30_RADAR_TASK_RETRY_TIME=args.retry_at,VN30_RADAR_TASK_DB=str(db_path.relative_to(ROOT)),
               VN30_RADAR_TASK_RUN_NOW='1' if args.run_now else '0')
    result=runner(['powershell.exe','-NoLogo','-NoProfile','-NonInteractive','-Command',STATUS if args.status else POWERSHELL],env=env,check=False)
    return result.returncode


if __name__=='__main__':
    # CLI tiếng Việt dùng UTF-8 cả khi stdout/stderr bị chuyển vào pipe trên Windows.
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    raise SystemExit(main())
