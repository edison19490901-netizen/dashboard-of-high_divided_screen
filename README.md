# 网格 · 高市值高股息率 筛选系统

A 股全市场扫描 — 市值 > 500 亿 + 股息率 > 5% 蓝筹股筛选 + HTML 看板。

## 快速开始

```bash
pip install -r requirements.txt

# 在当前目录创建 .env，写入 Tushare Token
echo TUSHARE_TOKEN=你的token > .env

# 首次运行：拉取 Tushare 全市场数据
python run.py

# 后续运行：自动使用本地缓存，秒级出结果
python run.py --open   # 生成后自动打开浏览器
```

## 配置

在**当前目录**的 `.env` 中设置 Tushare Token（参考 `.env.example`）：

```
TUSHARE_TOKEN=你的token
```

Tushare 免费账户即可使用，注册地址：https://tushare.pro

## 数据流

```
1. Tushare API — daily_basic 一次拉取全市场 5528 只
   ↓ 失败（频率限制/权限）
2. 本地 parquet 缓存 — cache/daily_basic_*.parquet
   ↓ 失败
3. Baostock 候选池 — 64 只大盘蓝筹兜底
   ↓
4. Baostock 补充 — 最新价 + 近1年最低价 + 距最低%
   ↓
5. HTML 看板
```

## 数据来源明细

| 字段 | 来源 | 接口 |
|---|---|---|
| 总市值 | Tushare | `daily_basic` → `total_mv` |
| 股息率 (TTM) | Tushare | `daily_basic` → `dv_ttm` |
| 最新价 | Baostock | `query_history_k_data_plus`（前复权） |
| 近1年最低价 | Baostock | `query_history_k_data_plus`（前复权） |
| 距最低价% | 计算 | `(最新价 - 最低价) / 最低价 × 100%` |
| 每股分红 | 计算 | `股息率 / 100 × 最新价` |
| 股票名称 | Tushare | `stock_basic` |

## 缓存

| 文件 | 内容 | 大小 |
|---|---|---|
| `cache/daily_basic_20260731.parquet` | 全市场 5528 只，18 字段（市值、股息率、PE、PB 等） | ~638 KB |
| `cache/stock_names.parquet` | 5535 只股票名称映射 | ~150 KB |

首次运行自动拉取并缓存，后续从本地秒级读取。删除缓存重跑即可更新数据。

## Tushare 频率限制

免费账户 `daily_basic` 限制 **1次/小时**，因此缓存机制确保只在需要更新数据时才调用 API。

## 筛选条件

| 条件 | 阈值 |
|---|---|
| 总市值 | > 500 亿 |
| 股息率 (TTM) | > 5% |

## 看板功能

- 卡片网格 / 数据表格双视图切换
- 搜索、排序（股息率 / 价格 / 市值 / 距最低价%）
- 距最低价颜色编码：🟢 <10% | 🟡 10-30% | 🔴 >30%
- 移动端响应式

## 文件结构

```
├── .env.example        # 配置模板
├── .gitignore
├── README.md
├── requirements.txt
├── run.py              # 一键入口
├── screener.py         # 筛选引擎
├── dashboard.py        # HTML 看板生成器
├── cache/              # 本地数据缓存（gitignore）
├── dashboard.html      # 生成的看板（gitignore）
└── screened_stocks_full.csv  # 筛选结果（gitignore）
```

## 免责声明

仅供学习研究，不构成投资建议。
