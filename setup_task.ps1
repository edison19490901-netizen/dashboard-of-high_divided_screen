# 安装自动任务：每个交易日 16:00 运行高股息筛选
# 请以管理员身份运行此脚本：
#   右键 PowerShell → 以管理员身份运行 → 粘贴下面一行：
#   powershell -ExecutionPolicy Bypass -File "setup_task.ps1"

$taskName = "HighDividendDailyReport"
$batPath  = "D:\Claudeee\highDivided_highValue_lowPrice\网格高市值高股息率\2%-3%看板识股\daily_report.bat"

# 删除旧任务（如果存在）
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# 创建新任务 — 周一到周五 16:00
$action   = New-ScheduledTaskAction -Execute $batPath
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 16:00
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "高股息筛选日报推送 - 每个交易日 16:00"

Write-Host ""
Write-Host "任务已创建:" -ForegroundColor Green
Write-Host "  名称: $taskName"
Write-Host "  时间: 周一至周五 16:00"
Write-Host "  运行: $batPath"
Write-Host ""
Write-Host "查看: taskschd.msc → HighDividendDailyReport"
Write-Host "测试: schtasks /run /tn HighDividendDailyReport"
