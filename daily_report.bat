@echo off
REM 每日收盘自动筛选 — 供 Windows 任务计划程序调用

cd /d "D:\Claudeee\dashboard-of-high_divided_screen"

REM 日志文件
set LOG=auto_report.log
echo ========== %date% %time% ========== >> %LOG%

REM 运行 Python
D:\Python313\python.exe daily_report.py >> %LOG% 2>&1

echo. >> %LOG%
