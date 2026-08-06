---
name: dashboard-deployment-handoff
description: 看板识股 GitHub Pages + GitHub Actions 部署方案完整 handoff
metadata:
  node_type: memory
  type: project
  modified: 2026-08-06
---

# 看板识股 — 部署 Handoff

## 项目位置
`D:\Claudeee\highDivided_highValue_lowPrice\网格高市值高股息率\2%-3%看板识股\`

## 选股策略
- 股息率 > 3%
- 市值 > 500亿
- 最新价距1年最低 < 15%
- 最新价距周线BB下轨 < 15%

## 看板地址
```
https://edison90901-netizen.github.io/dashboard-of-high_divided_screen/
```
手机浏览器直接打开即可查看。

## GitHub 仓库
`https://github.com/edison19490901-netizen/dashboard-of-high_divided_screen`

---

# 方案一：GitHub Actions 自动更新（主力方案，免费）

## 部署架构

```
GitHub Actions (免费 cron)                  手机
     │                                       │
     ├─ 工作日 15:30 自动触发                 │
     │     └─ gh_update.py                   │
     │           ├─ Tushare 缓存读取          │
     │           ├─ Baostock 股价+布林带      │
     │           ├─ 股息率重算 (DPS÷最新价)   │
     │           ├─ 写 dashboard.html         │
     │           └─ PushPlus 微信推送         │
     │                                       │
     └─ git push ──► GitHub Pages ────────────┘
                     始终在线，随时访问
```

**完全免费，不需要本地电脑开机。**

## 定时配置

文件：`.github/workflows/daily_update.yml` 第 5-6 行

```yaml
schedule:
  - cron: '30 7 * * 1-5'   # UTC 07:30 = 北京时间 15:30，周一至周五
```

修改时间：改 cron 表达式即可。格式：`分 时 日 月 周`（UTC 时间，北京时间 = UTC+8）。

## 所需 GitHub Secrets

在 `仓库 → Settings → Secrets and variables → Actions` 设置：

| Secret | 说明 |
|---|---|
| `TUSHARE_TOKEN` | Tushare API token |
| `PUSHPLUS_TOKEN` | PushPlus token，用于微信推送日报 |

## 手动触发

`仓库 → Actions → Daily Dashboard Update → Run workflow`

## GitHub Actions 工作流文件结构

```
daily_update.yml
  ├─ checkout 代码
  ├─ 安装 Python 依赖
  ├─ 运行 gh_update.py（带 TUSHARE_TOKEN + PUSHPLUS_TOKEN 环境变量）
  └─ 提交 dashboard.html 并 push → GitHub Pages 自动发布
```

---

# 方案二：本地 Windows 定时任务（备用方案）

保留此方案作为 GitHub Actions 故障时的备份。

## 调用链

```
Windows 任务计划程序 (HighDividendDailyReport)
  └─ C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe
       └─ C:\Users\HD07\run_report.ps1          ← 纯英文路径，UTF-8 BOM 编码
            └─ python daily_report.py            ← 绝对路径，在 ps1 中指定
                 ├─ 拉数据 → 写 dashboard.html
                 ├─ git push 到 GitHub Pages
                 ├─ PushPlus 微信推送
                 └─ _Tee 类双写日志到 auto_report.log
```

## 安装/修改定时任务

以**管理员身份**运行 PowerShell：

```powershell
& "D:\Claudeee\highDivided_highValue_lowPrice\网格高市值高股息率\2%-3%看板识股\setup_task.ps1"
```

修改时间：编辑 `setup_task.ps1` 第 17 行 `-At HH:MM`，重新运行上述命令。

## 手动测试

```powershell
schtasks /run /tn HighDividendDailyReport
```

## 查看任务

`Win+R` → `taskschd.msc` → 搜索 `HighDividendDailyReport`

## 电源设置（必须开启）

`Win+R` → `powercfg.cpl` → 当前计划 → 更改高级电源设置 → 睡眠 → **允许唤醒计时器** → **启用**

## 定时任务踩坑记录

Windows 任务计划程序存储含中文字符的路径时会出现编码损坏。最终方案：

| 尝试 | 方案 | 结果 |
|---|---|---|
| 1 | 任务直接调用 `daily_report.bat`（中文路径） | ❌ 路径乱码 |
| 2 | `python.exe` + `-WorkingDirectory`（中文） | ❌ WorkingDirectory 乱码 |
| 3 | `python.exe` + 绝对路径参数（中文） | ❌ 参数路径乱码 |
| 4 | 纯英文路径 `run_report.bat` 做跳板 | ❌ bat UTF-8 中文路径 cmd 不识别 |
| 5 | **纯英文路径 `run_report.ps1` + UTF-8 BOM + 绝对路径** | ✅ 成功 |

关键注意事项：
- `powershell.exe` 必须用完整路径 `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`
- 跳板 `.ps1` 必须用 `Out-File -Encoding UTF8` 或 `Set-Content -Encoding UTF8` 保存
- `Write` 工具写入的是 UTF-8 无 BOM，中文 PowerShell 会读成乱码

---

# 仓库文件结构

```
.
├── dashboard.html              # ★ 看板前端（含 EMBED 数据，GitHub Pages 直接渲染）
├── index.html                  # dashboard.html 副本
│
├── gh_update.py                # ★ GitHub Actions 每日运行脚本
│   ├── screen_from_cache()     #      读取 Tushare parquet 缓存
│   ├── supplement_baostock()   #      Baostock 补股价 + 1年最低 + BB布林带
│   ├── apply_price_filter()    #      价格过滤
│   ├── 股息率重算              #      DPS / 最新价（每日自动）
│   ├── 写 dashboard.html       #      内嵌 JSON 数据
│   └── PushPlus 微信推送       #      TOP20 静态 HTML 表格
│
├── app.py                      # 核心管线 + Web API 服务
│   ├── screen_from_cache()     #      从 parquet 缓存读取 Tushare 数据
│   ├── supplement_baostock()   #      Baostock 补股价 + 1年最低 + BB布林带
│   ├── apply_price_filter()    #      价格过滤（<15%距低 + <15%距BB下）
│   ├── update_tushare_cache()  #      拉取 Tushare daily_basic（Tushare API）
│   ├── run_full_pipeline()     #      完整管线入口
│   └── HTTP API (/api/data, /api/update, /api/refresh_prices)
│
├── daily_report.py             # 本地 Windows 定时脚本（备用）
├── auto_update.py              # 简易更新脚本（仅写 HTML，无推送）
│
├── .github/
│   └── workflows/
│       └── daily_update.yml    # ★ GitHub Actions 定时配置
│
├── cache/
│   ├── daily_basic_*.parquet   # Tushare 股息率+市值原始数据（每周一刷新）
│   └── stock_names.parquet     # 股票代码-名称映射
│
├── setup_task.ps1              # Windows 任务计划程序安装脚本
├── daily_report.bat            # Windows 定时任务入口（已弃用，保留备用）
│
├── C:\Users\HD07\run_report.ps1  # 跳板脚本（纯英文路径）→ 调用 python
│
├── requirements.txt            # Python 依赖（tushare, baostock, pandas, pyarrow, python-dotenv）
├── render.yaml                 # Render 部署配置（备用）
├── .env.example                # Token 配置模板
├── .gitignore                  # 排除 .env / cache/price_cache.json / auto_report.log
│
├── README.md                   # 项目说明
└── HANDOFF.md                  # 本文件
```

---

# 股息率每日重算机制

Tushare `daily_basic` 的 `dv_ttm`（股息率 TTM）是基于当日收盘价的。缓存后股价变动会导致股息率失真。

**解决方案**（`app.py` `supplement_baostock()`）：

```
Tushare → dv_ttm × 当日收盘价 / 100 = DPS（每股分红，每周一更新）
Baostock 每日 → latest_price
股息率 = DPS / latest_price × 100    ← 每次股价更新后自动重算
```

- DPS 只在公司公告分红时变动，一周更新一次足够
- 股息率每天跟着股价自动刷新

---

# 数据源

| 字段 | 来源 | 更新频率 |
|---|---|---|
| 市值 | Tushare `daily_basic` | 每周一 |
| 每股分红 (DPS) | Tushare `dv_ttm` 反推 | 每周一 |
| 股息率 | **DPS ÷ Baostock 最新价 × 100%** | 每日重算 |
| 最新价、近1年最低 | Baostock 日线 | 每日 |
| BB 布林带（周线） | Baostock 日线 → 周线重采样 → MA20±2σ | 每日 |
| 买入权重 | JS 公式: 0.4×距低 + 0.4×股息 + 0.2×BB下 | 每日 |

---

# 首次拉取缓存

如果 `cache/` 目录为空：

```bash
cd D:\Claudeee\highDivided_highValue_lowPrice\网格高市值高股息率\看板识股
python -c "
from app import update_tushare_cache
ok, msg = update_tushare_cache()
print(msg)
"
```

---

# Tushare Token

保存在 `.env` 文件和 GitHub Secrets（`TUSHARE_TOKEN`）中。

免费账户限制：`daily_basic` 1次/小时，5次/天。

---

# PushPlus 微信推送

- 服务: [PushPlus](http://www.pushplus.plus) — 微信公众号消息推送
- 模板: `html` — 推送静态 HTML 表格，微信内直接渲染
- 内容: TOP20 股票表格（按距低点升序），颜色标记（绿≤8% / 黄≤12% / 红>12%）
- Token: 存储在 `.env` → `PUSHPLUS_TOKEN=xxx`（本地）和 GitHub Secrets（Actions）

---

# 注意事项 & 已知限制

- **两个方案互为备份**：GitHub Actions 主力，本地 Windows 定时任务备用
- **数据源限制**：efiance (eastmoney) 在这台机器被屏蔽；Tushare 免费账户有频率限制
- **PowerShell 编码**：`setup_task.ps1` 用英文输出来避免控制台乱码
- **推送看板 vs Pages 看板**：微信推送精简 TOP20 静态表格（浅色主题）；GitHub Pages 完整交互看板（深色主题，含 JS 筛选/排序）
- **GitHub 连接**：这台机器 HTTPS (schannel) 间歇性超时，SSH 稳定

[[project-handoff-summary]]

## 本地定时任务管理

```powershell
# 禁用（推荐：保留任务定义，随时可恢复）
Disable-ScheduledTask -TaskName HighDividendDailyReport

# 启用
Enable-ScheduledTask -TaskName HighDividendDailyReport

# 彻底删除
Unregister-ScheduledTask -TaskName HighDividendDailyReport -Confirm:$false
```
