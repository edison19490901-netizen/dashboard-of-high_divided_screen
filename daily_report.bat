@echo off
REM 每日收盘自动筛选 — 供 Windows 任务计划程序调用

cd /d "D:\Claudeee\highDivided_highValue_lowPrice\网格高市值高股息率\2%-3%看板识股"

REM 日志文件
set LOG=auto_report.log
echo ========== %date% %time% ========== >> %LOG%

REM 运行 Python
D:\Python313\python.exe daily_report.py >> %LOG% 2>&1

echo. >> %LOG%
