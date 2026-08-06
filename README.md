# Dashboard of High Dividend Screen

A-share high-dividend low-valuation stock screening dashboard.  
筛选条件：**股息率>3% · 市值>500亿 · 距1年低点<15% · 距周线BB下轨<15%**

## 手机看板

```
https://edison90901-netizen.github.io/dashboard-of-high_divided_screen/
```

每天 15:30 自动更新，手机浏览器直接打开即可。

---

## 仓库文件结构

```
.
├── dashboard.html              # ★ 看板前端（含 EMBED 数据，GitHub Pages 直接渲染）
├── index.html                  # dashboard.html 副本
│
├── gh_update.py                # ★ GitHub Actions 每日运行脚本
│   ├── 读取 Tushare 缓存       #      → screen_from_cache()
│   ├── Baostock 补充股价+布林带 #     → supplement_baostock()
│   ├── 价格过滤                #      → apply_price_filter()
│   ├── 更新 dividend_yield     #      DPS / 最新价（跟着股价每日重算）
│   ├── 写入 dashboard.html     #      内嵌 JSON 数据
│   └── PushPlus 推送到微信     #      TOP20 静态 HTML 表格
│
├── app.py                      # 核心管线 + Web API 服务
│   ├── screen_from_cache()     #      从 parquet 缓存读取 Tushare 数据
│   ├── supplement_baostock()   #      Baostock 补股价 + 1年最低 + BB布林带
│   ├── apply_price_filter()    #      价格过滤（<15%距低 + <15%距BB下）
│   ├── update_tushare_cache()  #      拉取 Tushare daily_basic（每周一执行）
│   ├── run_full_pipeline()     #      完整管线入口
│   └── HTTP API (/api/data, /api/update)
│
├── daily_report.py             # 本地 Windows 定时脚本（已有 gh_update.py 后为冗余）
├── auto_update.py              # 简易更新脚本（仅写 HTML，无推送）
│
├── .github/
│   └── workflows/
│       └── daily_update.yml    # ★ GitHub Actions 定时配置
│           cron: '30 7 * * 1-5'  → 北京时间周一至周五 15:30
│
├── cache/
│   ├── daily_basic_*.parquet   # Tushare 股息率+市值原始数据（每周一刷新）
│   └── stock_names.parquet     # 股票代码-名称映射
│
├── setup_task.ps1              # Windows 任务计划程序安装脚本（本地冗余）
├── daily_report.bat            # Windows 定时任务入口脚本（本地冗余）
│
├── requirements.txt            # Python 依赖
├── render.yaml                 # Render 部署配置（备用）
├── .env.example                # Token 配置模板
├── .gitignore                  # 排除 .env / price_cache / 日志
│
├── README.md                   # 本文件
└── HANDOFF.md                  # 项目交接文档（部署踩坑记录）
```

## 关键数据流

```
Tushare (每周一)                Baostock (每日)
     │                               │
     ├─ dv_ttm → DPS (固定值)  ──────┤
     │                               │
     │                          latest_price (每日)
     │                               │
     └─────── 股息率 = DPS / 最新价 * 100% ← 每日重算
```

## 自动更新架构

```
GitHub Actions (免费)
  │
  ├─ 工作日 15:30 自动触发
  │     └─ gh_update.py → 拉数据 → 写 dashboard.html
  │
  ├─ git push 回仓库 → GitHub Pages 自动发布
  │     └─ 手机随时访问
  │
  └─ PushPlus → 微信推送 TOP20 日报
```

## 手动更新

1. 打开 Actions 页面：`仓库 → Actions → Daily Dashboard Update → Run workflow`
2. 或本地运行：`python gh_update.py`

## 修改定时时间

编辑 `.github/workflows/daily_update.yml` 第 6 行 cron 表达式：

```yaml
- cron: '30 7 * * 1-5'
#      分 时  日 月 周
#      30  7 = UTC 07:30 = 北京时间 15:30
```

## 选股公式

```
买入权重 = 0.4 * LowScore + 0.4 * DivScore + 0.2 * BBScore

LowScore  = max(0, 50 - pctFromLow) / 45
DivScore  = (dividendYield - 3) / (maxYield - 3)
BBScore   = max(0, 30 - pctFromBBLower) / 30
```

## 免责声明

仅供参考，不构成投资建议。

## 本地定时任务管理

```powershell
# 禁用
Disable-ScheduledTask -TaskName HighDividendDailyReport

# 启用
Enable-ScheduledTask -TaskName HighDividendDailyReport

# 删除
Unregister-ScheduledTask -TaskName HighDividendDailyReport -Confirm:$false
```
