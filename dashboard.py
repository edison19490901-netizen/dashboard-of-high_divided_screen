"""
HTML 看板生成器 — 将筛选结果渲染为交互式网格看板。

输入: screened_stocks_full.csv (由 screener.py 生成)
输出: dashboard.html
"""

import json
import math
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


def _fmt_mcap(val) -> str:
    """格式化市值，NaN 时返回 N/A."""
    try:
        v = float(val)
        if math.isnan(v) or v <= 0:
            return "N/A"
        return f"{v:.0f} 亿"
    except (ValueError, TypeError):
        return "N/A"


def _fmt_price(val) -> str:
    """格式化价格，NaN 时返回 N/A."""
    try:
        v = float(val)
        if math.isnan(v) or v <= 0:
            return "N/A"
        return f"{v:.2f}"
    except (ValueError, TypeError):
        return "N/A"


def _fmt_pct(val) -> str:
    """格式化百分比，NaN 时返回 N/A."""
    try:
        v = float(val)
        if math.isnan(v):
            return "N/A"
        return f"+{v:.1f}%"
    except (ValueError, TypeError):
        return "N/A"


def _pct_class(val) -> str:
    """距最低价百分比的颜色."""
    try:
        v = float(val)
        if math.isnan(v):
            return ""
        if v < 10:
            return "pct-low"
        elif v < 30:
            return "pct-mid"
        return "pct-high"
    except (ValueError, TypeError):
        return ""


def _fmt_dps(val) -> str:
    """格式化每股分红，NaN 时返回 N/A."""
    try:
        v = float(val)
        if math.isnan(v) or v <= 0:
            return "N/A"
        return f"{v:.4f} 元"
    except (ValueError, TypeError):
        return "N/A"


def load_data(csv_path: str = "screened_stocks_full.csv") -> dict:
    """加载筛选结果并构建看板数据。"""
    path = Path(csv_path)
    if not path.exists():
        print(f"❌ 找不到 {csv_path}，请先运行 screener.py")
        return None

    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    stocks = df.to_dict(orient="records")

    # 计算摘要
    total = len(stocks)
    avg_yield = df["dividend_yield"].mean() if total > 0 else 0
    max_yield_row = df.loc[df["dividend_yield"].idxmax()] if total > 0 else None
    min_price_row = df.loc[df["latest_price"].idxmin()] if total > 0 else None

    return {
        "stocks": stocks,
        "total": total,
        "avg_yield": round(avg_yield, 2),
        "max_yield_stock": {
            "name": max_yield_row["name"],
            "value": round(max_yield_row["dividend_yield"], 2),
        } if max_yield_row is not None else None,
        "min_price_stock": {
            "name": min_price_row["name"],
            "value": round(min_price_row["latest_price"], 2),
        } if min_price_row is not None else None,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_date": df["data_date"].iloc[0] if total > 0 else "",
    }


def render_dashboard(data: dict) -> str:
    """渲染完整 HTML 看板。"""
    stocks = data["stocks"]
    stocks_json = json.dumps(stocks, ensure_ascii=False, default=str)

    # ── 统计卡片 ──
    stat_cards = f"""
    <div class="stat-card green">
        <div class="stat-value">{data['total']}</div>
        <div class="stat-label">📈 符合条件的股票</div>
        <div class="stat-desc">市值 &gt; 500亿 + 股息率 &gt; 5%</div>
    </div>
    <div class="stat-card yellow">
        <div class="stat-value">{data['avg_yield']}%</div>
        <div class="stat-label">💰 平均股息率</div>
    </div>
    <div class="stat-card blue">
        <div class="stat-value">{data['max_yield_stock']['name'] if data['max_yield_stock'] else '-'}</div>
        <div class="stat-label">🏆 最高股息率 ({data['max_yield_stock']['value']}%)</div>
    </div>
    <div class="stat-card purple">
        <div class="stat-value">{data['min_price_stock']['name'] if data['min_price_stock'] else '-'}</div>
        <div class="stat-label">💎 最低股价 ({data['min_price_stock']['value']}元)</div>
    </div>"""

    # ── 卡片网格 ──
    cards = []
    for s in stocks:
        # 股息率越高，绿色越深
        div = s["dividend_yield"]
        if div >= 7:
            intensity = "high"
        elif div >= 6:
            intensity = "mid"
        else:
            intensity = "low"

        cards.append(f"""
        <div class="stock-card {intensity}" onclick="highlightCard(this)">
            <div class="card-header">
                <span class="card-name">{s['name']}</span>
                <span class="card-code">{s['code']}</span>
            </div>
            <div class="card-body">
                <div class="card-metric">
                    <span class="metric-label">股息率</span>
                    <span class="metric-value yield">{s['dividend_yield']:.2f}%</span>
                </div>
                <div class="card-metric">
                    <span class="metric-label">最新价</span>
                    <span class="metric-value">{s['latest_price']:.2f} 元</span>
                </div>
                <div class="card-metric">
                    <span class="metric-label">近1年最低</span>
                    <span class="metric-value">{_fmt_price(s.get('min_price_1y'))}</span>
                </div>
                <div class="card-metric">
                    <span class="metric-label">距最低</span>
                    <span class="metric-value {_pct_class(s.get('pct_from_low'))}">{_fmt_pct(s.get('pct_from_low'))}</span>
                </div>
                <div class="card-metric">
                    <span class="metric-label">每股分红</span>
                    <span class="metric-value">{_fmt_dps(s['dividend_per_share'])}</span>
                </div>
                <div class="card-metric">
                    <span class="metric-label">总市值</span>
                    <span class="metric-value">{_fmt_mcap(s['market_cap_billion'])}</span>
                </div>
            </div>
            <div class="card-footer">
                <div class="yield-bar-bg">
                    <div class="yield-bar-fill" style="width:{min(div / 8 * 100, 100)}%"></div>
                </div>
                <span class="yield-label">股息率 {s['dividend_yield']:.1f}%</span>
            </div>
        </div>""")

    # ── 表格行 ──
    table_rows = []
    for i, s in enumerate(stocks, 1):
        div = s["dividend_yield"]
        div_color = "#22c55e" if div >= 7 else ("#eab308" if div >= 6 else "#94a3b8")
        bar_pct = min(div / 8 * 100, 100)

        pct_low = s.get('pct_from_low', float('nan'))
        pct_color = '#22c55e' if pct_low == pct_low and pct_low < 10 else ('#eab308' if pct_low < 30 else '#ef4444')

        table_rows.append(f"""
        <tr onclick="highlightRow(this)">
            <td>{i}</td>
            <td>
                <span class="td-name">{s['name']}</span>
                <span class="td-code">{s['code']}</span>
            </td>
            <td class="num">{_fmt_mcap(s['market_cap_billion'])}</td>
            <td class="num">{s['latest_price']:.2f}</td>
            <td class="num">{_fmt_price(s.get('min_price_1y'))}</td>
            <td class="num" style="color:{pct_color};font-weight:600">{_fmt_pct(s.get('pct_from_low'))}</td>
            <td class="num" style="color:{div_color};font-weight:700">{s['dividend_yield']:.2f}%</td>
            <td class="num">{_fmt_dps(s['dividend_per_share'])}</td>
        </tr>""")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#0a0e27">
<title>高市值高股息率筛选看板</title>
<style>
:root {{
    --bg: #0a0e27;
    --card-bg: #111640;
    --border: #1e2456;
    --text: #e2e8f0;
    --text-secondary: #8892b0;
    --green: #22c55e;
    --yellow: #eab308;
    --blue: #3b82f6;
    --purple: #a855f7;
    --red: #ef4444;
    --accent: #6366f1;
}}

* {{ margin:0; padding:0; box-sizing:border-box; }}

body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    line-height: 1.6;
}}
body::before {{
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background:
        radial-gradient(ellipse at 20% 50%, rgba(99,102,241,0.06) 0%, transparent 50%),
        radial-gradient(ellipse at 80% 20%, rgba(34,197,94,0.04) 0%, transparent 50%);
    pointer-events: none;
    z-index: 0;
}}

.container {{
    max-width: 1400px;
    margin: 0 auto;
    padding: 24px;
    position: relative;
    z-index: 1;
}}

/* ===== Header ===== */
.header {{
    text-align: center;
    padding: 48px 20px 32px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 32px;
}}
.header h1 {{
    font-size: 2rem;
    font-weight: 700;
    margin-bottom: 8px;
    background: linear-gradient(135deg, #e2e8f0 0%, #a5b4fc 50%, #22c55e 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}}
.header .subtitle {{
    color: var(--text-secondary);
    font-size: 0.95rem;
    margin-bottom: 4px;
}}
.header .badge-row {{
    display: flex;
    gap: 12px;
    justify-content: center;
    flex-wrap: wrap;
    margin-top: 16px;
}}
.header .badge {{
    padding: 4px 16px;
    border-radius: 20px;
    font-size: 0.82rem;
    font-weight: 500;
}}
.badge-market {{ background: rgba(99,102,241,0.15); color: #a5b4fc; }}
.badge-div {{ background: rgba(34,197,94,0.12); color: #4ade80; }}
.badge-date {{ background: rgba(148,163,184,0.10); color: #94a3b8; }}

/* ===== Stat Cards ===== */
.stat-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 16px;
    margin-bottom: 36px;
}}
.stat-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 24px;
    text-align: center;
    transition: transform 0.2s, box-shadow 0.2s;
}}
.stat-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 30px rgba(0,0,0,0.3);
}}
.stat-card .stat-value {{
    font-size: 2.2rem;
    font-weight: 700;
    margin-bottom: 4px;
}}
.stat-card .stat-label {{
    color: var(--text-secondary);
    font-size: 0.9rem;
}}
.stat-card .stat-desc {{
    color: var(--text-secondary);
    font-size: 0.75rem;
    margin-top: 6px;
    opacity: 0.7;
}}
.stat-card.green .stat-value {{ color: var(--green); }}
.stat-card.yellow .stat-value {{ color: var(--yellow); }}
.stat-card.blue .stat-value {{ color: var(--blue); }}
.stat-card.purple .stat-value {{ color: var(--purple); }}

/* ===== View Toggle ===== */
.view-toggle {{
    display: flex;
    gap: 4px;
    margin-bottom: 24px;
    background: var(--card-bg);
    border-radius: 12px;
    padding: 4px;
    border: 1px solid var(--border);
    width: fit-content;
}}
.view-btn {{
    padding: 10px 24px;
    border: none;
    background: transparent;
    color: var(--text-secondary);
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 500;
    transition: all 0.2s;
}}
.view-btn.active {{
    background: var(--accent);
    color: #fff;
}}
.view-btn:hover:not(.active) {{ color: var(--text); }}

/* ===== Search ===== */
.toolbar {{
    display: flex;
    gap: 12px;
    align-items: center;
    margin-bottom: 24px;
    flex-wrap: wrap;
}}
.search-box {{
    padding: 10px 18px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.03);
    color: var(--text);
    font-size: 0.9rem;
    width: 280px;
    outline: none;
    transition: border-color 0.2s;
}}
.search-box:focus {{ border-color: var(--accent); }}
.search-box::placeholder {{ color: var(--text-secondary); }}
.sort-select {{
    padding: 10px 14px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--card-bg);
    color: var(--text);
    font-size: 0.9rem;
    outline: none;
    cursor: pointer;
}}
.sort-select:focus {{ border-color: var(--accent); }}
.result-count {{
    color: var(--text-secondary);
    font-size: 0.85rem;
    margin-left: auto;
}}

/* ===== Grid View ===== */
.grid-view {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
}}
.stock-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 16px;
    overflow: hidden;
    cursor: pointer;
    transition: all 0.25s;
    position: relative;
}}
.stock-card:hover {{
    transform: translateY(-3px);
    box-shadow: 0 12px 40px rgba(0,0,0,0.35);
    border-color: var(--accent);
}}
.stock-card.high {{ border-left: 3px solid var(--green); }}
.stock-card.mid {{ border-left: 3px solid var(--yellow); }}
.stock-card.low {{ border-left: 3px solid var(--text-secondary); }}

.card-header {{
    padding: 16px 20px 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}}
.card-name {{
    font-size: 1.05rem;
    font-weight: 600;
}}
.card-code {{
    font-size: 0.75rem;
    color: var(--text-secondary);
    font-family: "SF Mono", "JetBrains Mono", monospace;
    background: rgba(255,255,255,0.04);
    padding: 2px 10px;
    border-radius: 6px;
}}

.card-body {{
    padding: 0 20px 12px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
}}
.card-metric {{
    display: flex;
    flex-direction: column;
    gap: 2px;
}}
.metric-label {{
    font-size: 0.72rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.04em;
}}
.metric-value {{
    font-size: 1rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    font-family: "SF Mono", "JetBrains Mono", monospace;
}}
.metric-value.yield {{
    color: var(--green);
    font-size: 1.15rem;
}}

.card-footer {{
    padding: 10px 20px 14px;
    display: flex;
    align-items: center;
    gap: 10px;
}}
.yield-bar-bg {{
    flex: 1;
    height: 6px;
    background: rgba(255,255,255,0.06);
    border-radius: 3px;
    overflow: hidden;
}}
.yield-bar-fill {{
    height: 100%;
    border-radius: 3px;
    background: linear-gradient(90deg, var(--accent), var(--green));
    transition: width 0.6s ease;
}}
.yield-label {{
    font-size: 0.75rem;
    color: var(--text-secondary);
    white-space: nowrap;
}}

/* ===== Table View ===== */
.table-view {{
    display: none;
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 16px;
    overflow: hidden;
    margin-bottom: 32px;
}}
.table-view.active {{ display: block; }}
.grid-view.active {{ display: grid; }}
.grid-view {{ display: none; }}

table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
}}
th {{
    text-align: left;
    padding: 14px 18px;
    background: rgba(255,255,255,0.02);
    color: var(--text-secondary);
    font-weight: 500;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
}}
td {{
    padding: 12px 18px;
    border-bottom: 1px solid rgba(255,255,255,0.03);
}}
tr:hover {{ background: rgba(255,255,255,0.02); cursor: pointer; }}
tr.highlight {{ background: rgba(99,102,241,0.1) !important; }}

.td-name {{ font-weight: 500; display: block; }}
.td-code {{
    font-size: 0.72rem;
    color: var(--text-secondary);
    font-family: "SF Mono", "JetBrains Mono", monospace;
}}
.num {{
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-family: "SF Mono", "JetBrains Mono", monospace;
}}
.pct-low {{ color: var(--green); font-weight: 600; }}
.pct-mid {{ color: var(--yellow); font-weight: 600; }}
.pct-high {{ color: var(--red); font-weight: 600; }}
.mini-bar {{
    width: 80px;
    height: 6px;
    background: rgba(255,255,255,0.06);
    border-radius: 3px;
    overflow: hidden;
}}
.mini-bar-fill {{
    height: 100%;
    border-radius: 3px;
    background: linear-gradient(90deg, var(--accent), var(--green));
    transition: width 0.5s;
}}

/* ===== Footer ===== */
.footer {{
    text-align: center;
    padding: 32px;
    color: var(--text-secondary);
    font-size: 0.8rem;
    border-top: 1px solid var(--border);
}}
.footer a {{ color: var(--accent); text-decoration: none; }}

/* ===== Responsive ===== */
@media (max-width: 768px) {{
    .container {{ padding: 12px; }}
    .header {{ padding: 28px 10px 20px; }}
    .header h1 {{ font-size: 1.3rem; }}
    .stat-grid {{ grid-template-columns: 1fr 1fr; gap: 10px; }}
    .stat-card {{ padding: 16px 12px; }}
    .stat-card .stat-value {{ font-size: 1.5rem; }}
    .grid-view {{ grid-template-columns: 1fr; }}
    .search-box {{ width: 100%; }}
    .toolbar {{ flex-direction: column; align-items: stretch; }}
    .result-count {{ margin-left: 0; text-align: center; }}
    table {{ font-size: 0.75rem; }}
    th, td {{ padding: 8px 10px; }}
    th:nth-child(3), td:nth-child(3) {{ display: none; }}
    th:nth-child(7), td:nth-child(7) {{ display: none; }}
}}
</style>
</head>
<body>

<div class="container">

    <!-- Header -->
    <div class="header">
        <h1>📊 高市值 · 高股息率 筛选看板</h1>
        <div class="subtitle">A 股全市场扫描 — 市值 &gt; 500 亿 + 股息率 &gt; 5% 蓝筹股</div>
        <div class="badge-row">
            <span class="badge badge-market">🏦 市值 &gt; 500 亿</span>
            <span class="badge badge-div">💰 股息率 &gt; 5%</span>
            <span class="badge badge-date">📅 {data['data_date']}</span>
        </div>
    </div>

    <!-- Stat Cards -->
    <div class="stat-grid">
        {stat_cards}
    </div>

    <!-- Toolbar -->
    <div class="toolbar">
        <div class="view-toggle">
            <button class="view-btn active" onclick="switchView('grid')">📱 卡片网格</button>
            <button class="view-btn" onclick="switchView('table')">📋 数据表格</button>
        </div>
        <input type="text" class="search-box" id="searchInput" placeholder="🔍 搜索名称或代码..." oninput="filterAll()">
        <select class="sort-select" id="sortSelect" onchange="filterAll()">
            <option value="yield_desc">股息率 ↓</option>
            <option value="yield_asc">股息率 ↑</option>
            <option value="price_asc">价格 ↓</option>
            <option value="price_desc">价格 ↑</option>
            <option value="pct_asc">距最低% ↑</option>
            <option value="mcap_desc">市值 ↓</option>
        </select>
        <span class="result-count" id="resultCount"></span>
    </div>

    <!-- Grid View -->
    <div class="grid-view active" id="gridView">
        {"".join(cards)}
    </div>

    <!-- Table View -->
    <div class="table-view" id="tableView">
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>名称 / 代码</th>
                    <th style="text-align:right">市值</th>
                    <th style="text-align:right">最新价</th>
                    <th style="text-align:right">近1年最低</th>
                    <th style="text-align:right">距最低</th>
                    <th style="text-align:right">股息率</th>
                    <th style="text-align:right">每股分红</th>
                </tr>
            </thead>
            <tbody id="tableBody">
                {"".join(table_rows)}
            </tbody>
        </table>
    </div>

    <!-- Footer -->
    <div class="footer">
        市值/股息率: Tushare daily_basic &nbsp;|&nbsp;
        最新价/近1年最低: Baostock &nbsp;|&nbsp;
        筛选: 市值 &gt; 500 亿 &nbsp; 股息率 &gt; 5% &nbsp;|&nbsp;
        {data['generated_at']} &nbsp;|&nbsp;
        ⚠️ 仅供参考，不构成投资建议
    </div>

</div>

<script>
// ── Data ──
const STOCKS = {stocks_json};
let currentView = 'grid';
let currentSort = 'yield_desc';
let currentQuery = '';

// ── View Switch ──
function switchView(view) {{
    currentView = view;
    document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll(`.view-btn`)[view === 'grid' ? 0 : 1].classList.add('active');
    document.getElementById('gridView').classList.toggle('active', view === 'grid');
    document.getElementById('tableView').classList.toggle('active', view === 'table');
    filterAll();
}}

// ── Sort ──
function getSorted() {{
    let arr = [...STOCKS];
    switch(currentSort) {{
        case 'yield_desc': arr.sort((a,b) => b.dividend_yield - a.dividend_yield); break;
        case 'yield_asc':  arr.sort((a,b) => a.dividend_yield - b.dividend_yield); break;
        case 'price_asc':  arr.sort((a,b) => a.latest_price - b.latest_price); break;
        case 'price_desc': arr.sort((a,b) => b.latest_price - a.latest_price); break;
        case 'mcap_desc':  arr.sort((a,b) => b.market_cap_billion - a.market_cap_billion); break;
        case 'pct_asc':   arr.sort((a,b) => (a.pct_from_low||999) - (b.pct_from_low||999)); break;
    }}
    return arr;
}}

// ── Filter ──
function filterAll() {{
    currentSort = document.getElementById('sortSelect').value;
    currentQuery = document.getElementById('searchInput').value.toLowerCase();
    const sorted = getSorted();
    const filtered = sorted.filter(s =>
        !currentQuery || s.name.toLowerCase().includes(currentQuery) || s.code.toLowerCase().includes(currentQuery)
    );

    // Update grid
    const grid = document.getElementById('gridView');
    grid.innerHTML = filtered.map(s => {{
        const div = s.dividend_yield;
        const intensity = div >= 7 ? 'high' : (div >= 6 ? 'mid' : 'low');
        const pctLow = s.pct_from_low;
        const pctStr = (pctLow != null && !isNaN(pctLow)) ? '+' + pctLow.toFixed(1) + '%' : 'N/A';
        const pctCls = (pctLow != null && !isNaN(pctLow)) ? (pctLow < 10 ? 'pct-low' : (pctLow < 30 ? 'pct-mid' : 'pct-high')) : '';
        const min1y = (s.min_price_1y != null && s.min_price_1y > 0) ? s.min_price_1y.toFixed(2) : 'N/A';
        return `<div class="stock-card ${{intensity}}" onclick="highlightCard(this)">
            <div class="card-header">
                <span class="card-name">${{s.name}}</span>
                <span class="card-code">${{s.code}}</span>
            </div>
            <div class="card-body">
                <div class="card-metric"><span class="metric-label">股息率</span><span class="metric-value yield">${{s.dividend_yield.toFixed(2)}}%</span></div>
                <div class="card-metric"><span class="metric-label">最新价</span><span class="metric-value">${{s.latest_price.toFixed(2)}} 元</span></div>
                <div class="card-metric"><span class="metric-label">近1年最低</span><span class="metric-value">${{min1y}}</span></div>
                <div class="card-metric"><span class="metric-label">距最低</span><span class="metric-value ${{pctCls}}">${{pctStr}}</span></div>
                <div class="card-metric"><span class="metric-label">每股分红</span><span class="metric-value">${{(s.dividend_per_share && s.dividend_per_share > 0) ? s.dividend_per_share.toFixed(4)+' 元' : 'N/A'}}</span></div>
                <div class="card-metric"><span class="metric-label">总市值</span><span class="metric-value">${{(s.market_cap_billion && s.market_cap_billion > 0) ? s.market_cap_billion.toFixed(0)+' 亿' : 'N/A'}}</span></div>
            </div>
            <div class="card-footer">
                <div class="yield-bar-bg"><div class="yield-bar-fill" style="width:${{Math.min(div/8*100,100)}}%"></div></div>
                <span class="yield-label">股息率 ${{s.dividend_yield.toFixed(1)}}%</span>
            </div>
        </div>`;
    }}).join('');

    // Update table
    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = filtered.map((s, i) => {{
        const div = s.dividend_yield;
        const divColor = div >= 7 ? '#22c55e' : (div >= 6 ? '#eab308' : '#94a3b8');
        const pctLow = s.pct_from_low;
        const pctColor = (pctLow != null && !isNaN(pctLow)) ? (pctLow < 10 ? '#22c55e' : (pctLow < 30 ? '#eab308' : '#ef4444')) : '#94a3b8';
        const pctStr = (pctLow != null && !isNaN(pctLow)) ? '+' + pctLow.toFixed(1) + '%' : 'N/A';
        const min1y = (s.min_price_1y != null && s.min_price_1y > 0) ? s.min_price_1y.toFixed(2) : 'N/A';
        return `<tr onclick="highlightRow(this)">
            <td>${{i + 1}}</td>
            <td><span class="td-name">${{s.name}}</span><span class="td-code">${{s.code}}</span></td>
            <td class="num">${{(s.market_cap_billion && s.market_cap_billion > 0) ? s.market_cap_billion.toFixed(0)+' 亿' : 'N/A'}}</td>
            <td class="num">${{s.latest_price.toFixed(2)}}</td>
            <td class="num">${{min1y}}</td>
            <td class="num" style="color:${{pctColor}};font-weight:600">${{pctStr}}</td>
            <td class="num" style="color:${{divColor}};font-weight:700">${{s.dividend_yield.toFixed(2)}}%</td>
            <td class="num">${{(s.dividend_per_share && s.dividend_per_share > 0) ? s.dividend_per_share.toFixed(4) : 'N/A'}}</td>
        </tr>`;
    }}).join('');

    document.getElementById('resultCount').textContent = `显示 ${{filtered.length}} / ${{STOCKS.length}} 只`;
}}

// ── Interaction ──
function highlightCard(card) {{
    card.style.transition = 'background 0.3s';
    card.style.background = 'rgba(99,102,241,0.12)';
    setTimeout(() => card.style.background = '', 800);
}}

function highlightRow(tr) {{
    tr.classList.add('highlight');
    setTimeout(() => tr.classList.remove('highlight'), 800);
}}

// ── Init ──
filterAll();
</script>

</body>
</html>"""


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Loading screening results...")
    data = load_data()
    if data is None:
        return

    print(f"Found {data['total']} stocks matching criteria")
    html = render_dashboard(data)

    output_path = Path("dashboard.html")
    output_path.write_text(html, encoding="utf-8")
    print(f"✅ Dashboard saved: {output_path}")
    print(f"   Open: file:///{output_path.absolute()}")


if __name__ == "__main__":
    main()
