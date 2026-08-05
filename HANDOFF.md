---
name: dashboard-deployment-handoff
description: 看板识股 GitHub Pages 部署方案完整 handoff
metadata: 
  node_type: memory
  type: project
  originSessionId: 8ac2dd65-175f-4427-94bf-7779f5badcec
  modified: 2026-08-03T08:37:18.517Z
---

# 看板识股 — 部署 Handoff

## 项目位置
`D:\Claudeee\highDivided_highValue_lowPrice\网格高市值高股息率\2%-3%看板识股\`

## 选股策略
- 股息率 > 3%
- 市值 > 500亿
- 最新价距1年最低 < 15%
- 最新价距周线BB下轨 < 15%

## GitHub 仓库
`https://github.com/edison19490901-netizen/dashboard-of-high_divided_screen`

## 部署架构

```
GitHub Pages (免费静态托管)          本地 Windows (数据更新)
     │                                     │
index.html ─── 内嵌 JSON 数据 ←──── app.py 生成 dashboard.html
     │                                     │
手机/任何设备                          Tushare + Baostock
永久在线访问                           拉取最新数据
```

- **看板地址**: `https://edison19490901-netizen.github.io/dashboard-of-high_divided_screen`
- **零费用**: GitHub Pages 免费 + 无服务器
- **数据更新**: 本地跑 Python 生成新 HTML → 推送到 GitHub

## 首次启用 GitHub Pages

1. 打开 https://github.com/edison19490901-netizen/dashboard-of-high_divided_screen/settings/pages
2. Branch 选 `master`，文件夹选 `/ (root)`
3. 点 Save，等 1 分钟生效

## 更新数据流程

```bash
# 1. 进入项目目录
cd D:\Claudeee\highDivided_highValue_lowPrice\网格高市值高股息率\看板识股

# 2. 启动 API 服务
python app.py

# 3. 浏览器打开 http://localhost:8080，点「更新股息率」

# 4. 生成新看板并推送
cp dashboard.html index.html
git add index.html
git commit -m "update data $(date +%Y%m%d)"
git push
```

## 首次拉取缓存

如果 `cache/` 目录为空，需要先拉取 Tushare 数据：

```bash
cd D:\Claudeee\highDivided_highValue_lowPrice\网格高市值高股息率\看板识股
python -c "
from app import update_tushare_cache
ok, msg = update_tushare_cache()
print(msg)
"
```

## 文件说明

| 文件 | 作用 | 提交到 GitHub |
|---|---|---|
| `app.py` | Python API 服务 | ✓ |
| `dashboard.html` | 看板模板 | ✓ |
| `index.html` | GitHub Pages 入口（dashboard.html 副本+数据） | ✓ |
| `render.yaml` | Render 部署配置（备用） | ✓ |
| `requirements.txt` | Python 依赖 | ✓ |
| `README.md` | 项目说明 | ✓ |
| `.env.example` | Token 配置模板 | ✓ |
| `.env` | 实际 Token | ✗ gitignore |
| `cache/*.parquet` | Tushare 数据缓存 | ✗ gitignore |

## Tushare Token

当前有效 token 保存在 `.env`：
```
TUSHARE_TOKEN=2267b4d5cb028236d04f16796221c23716d110fbece03e43926c1a90
```

免费账户限制：`daily_basic` 1次/小时，5次/天。更换 token 时修改 `.env` 即可。

## 数据源

| 字段 | 来源 |
|---|---|
| 市值、股息率 | Tushare `daily_basic` |
| 最新价、近1年最低 | Baostock 日线 |
| BB 布林带（周线） | Baostock 日线 → 周线重采样 → MA20±2σ |
| 买入权重 | JS 公式: 0.4×距低 + 0.4×股息 + 0.2×BB下 |

## 已知限制

- efiance (eastmoney) 在这台机器被屏蔽
- Tushare 免费账户有频率限制
- GitHub Pages 只托管静态文件，数据更新需本地操作
- 首次打开或长时间未访问时数据可能过时

[[project-handoff-summary]]
