"""
GitHub Actions 每日更新脚本
- 读取 Tushare 缓存 + Baostock 实时股价
- 更新 dashboard.html
- 通过 PushPlus 推送到微信
"""
import sys, os, json, re, shutil, html as html_module
from datetime import datetime
from pathlib import Path

# Ensure we're in the project root
os.chdir(Path(__file__).resolve().parent)
sys.path.insert(0, '.')

from app import screen_from_cache, supplement_baostock, apply_price_filter, update_tushare_cache, save_price_cache


def get_dashboard_url():
    """根据部署环境返回看板链接地址"""
    if os.getenv('RENDER'):
        return 'https://dashboard-of-high-divided-screen.onrender.com'
    if os.getenv('GITHUB_ACTIONS'):
        return 'https://edison19490901-netizen.github.io/dashboard-of-high_divided_screen/'
    # 本地环境：直接打开本地 HTML 文件
    root = os.path.dirname(os.path.abspath(__file__))
    return f'file:///{root.replace(chr(92), "/")}/dashboard.html'


def is_local_env():
    """判断是否为本地环境"""
    return not os.getenv('RENDER') and not os.getenv('GITHUB_ACTIONS')


def send_pushplus(token: str, title: str, content: str, template: str = 'html') -> bool:
    """通过 PushPlus 推送到微信"""
    import urllib.request
    url = 'http://www.pushplus.plus/send'
    data = json.dumps({
        'token': token,
        'title': title,
        'content': content,
        'template': template,
    }).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json'
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode())
        if result.get('code') == 200:
            print(f'  PushPlus OK: {title}')
            return True
        else:
            print(f'  PushPlus fail: {result}')
            return False


def build_static_html(df) -> str:
    """生成精简 TOP20 静态 HTML 表格（微信可直接渲染）"""
    count = len(df)
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    df_sorted = df.sort_values('pct_from_low', ascending=True)
    df_show = df_sorted.head(20)

    def pct_color(v):
        try:
            v = float(v)
            return '#059669' if v <= 8 else '#d97706' if v <= 12 else '#dc2626'
        except:
            return '#64748b'

    def div_color(v):
        try:
            v = float(v)
            return '#059669' if v >= 5 else '#d97706' if v >= 4 else '#dc2626'
        except:
            return '#64748b'

    rows_html = ''
    for _, row in df_show.iterrows():
        name = html_module.escape(str(row.get('name', '-')))
        code = html_module.escape(str(row.get('code', '-')))
        price = row.get('latest_price', 0)
        div_y = row.get('dividend_yield', 0)
        pct_low = row.get('pct_from_low', '-')
        pct_bb = row.get('pct_from_lower', '-')
        mcap = row.get('market_cap_billion', 0)

        rows_html += (
            f'<tr><td style="text-align:left;font-weight:500;white-space:nowrap">'
            f'{name}<br><span style="font-size:10px;color:#8892b0">{code}</span></td>'
            f'<td style="font-weight:600">{price:.2f}</td>'
            f'<td style="color:{div_color(div_y)};font-weight:600">{div_y:.1f}%</td>'
            f'<td style="color:{pct_color(pct_low)};font-weight:600">{pct_low}%</td>'
            f'<td style="color:{pct_color(pct_bb)};font-weight:600">{pct_bb}%</td>'
            f'<td style="white-space:nowrap">{mcap:.0f}亿</td></tr>')

    more = ''
    if count > 20:
        more = (f'<div style="text-align:center;padding:8px;color:#d97706;font-size:12px">'
                f'仅显示 TOP20，共 {count} 只</div>')

    return (
        f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1.0">'
        f'<title>高股息筛选日报</title></head>'
        f'<body style="margin:0;padding:10px;font-family:-apple-system,PingFang SC,Microsoft YaHei,sans-serif;background:#fff;color:#1a1a2e">'
        f'<div style="text-align:center;padding:10px 0 14px;border-bottom:1px solid #e2e8f0;margin-bottom:10px">'
        f'<div style="font-size:17px;font-weight:700;color:#1a1a2e">高股息筛选日报</div>'
        f'<div style="color:#64748b;font-size:11px;margin-top:5px">{now} | 符合条件: <b style="color:#059669">{count}</b> 只</div>'
        f'<div style="color:#94a3b8;font-size:10px;margin-top:2px">股息率>3% · 市值>500亿 · 距1年低点<15% · 距BB下轨<15%</div></div>'
        f'{more}'
        f'<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12px;background:#fff">'
        f'<thead><tr style="background:#f1f5f9;color:#64748b;font-size:10px;letter-spacing:.5px">'
        f'<th style="padding:8px 4px;text-align:left">名称</th><th style="padding:8px 4px">股价</th>'
        f'<th style="padding:8px 4px">股息率</th><th style="padding:8px 4px">距低点</th>'
        f'<th style="padding:8px 4px">距BB下</th><th style="padding:8px 4px">市值</th></tr></thead>'
        f'<tbody>{rows_html}</tbody></table></div>'
        f'<div style="text-align:center;padding:10px;color:#94a3b8;font-size:10px;border-top:1px solid #e2e8f0;margin-top:10px">'
        f'数据来源: Tushare + Baostock | 仅供参考<br>'
        f'<a href="{get_dashboard_url()}" style="color:#6366f1">查看完整交互看板</a></div></body></html>')


def main():
    print(f'[{datetime.now():%Y-%m-%d %H:%M}] Starting pipeline...')

    # Step 1: Ensure cache exists
    cache_dir = Path('cache')
    if not list(cache_dir.glob('daily_basic_*.parquet')):
        print('No cache found, fetching from Tushare...')
        ok, msg = update_tushare_cache()
        print(f'  Tushare: {msg}')
        if not ok:
            print('FATAL: Cannot get Tushare data')
            sys.exit(1)

    # Step 2: Screen + supplement + filter
    df = screen_from_cache()
    if df is None or df.empty:
        print('No stocks in cache')
        if not is_local_env():
            pushplus_token = os.getenv('PUSHPLUS_TOKEN', '')
            if pushplus_token:
                send_pushplus(pushplus_token, '高股息筛选 - 无数据', '缓存无数据', 'txt')
        sys.exit(0)

    print(f'  Screened: {len(df)} stocks, fetching prices...')
    df = supplement_baostock(df)
    df = apply_price_filter(df)
    print(f'  After filter: {len(df)} stocks')
    if not df.empty:
        save_price_cache(df)  # 持久化缓存, 供 Render 部署使用

    if df.empty:
        print('No stocks match criteria')
        stocks = []
    else:
        stocks = json.loads(df.to_json(orient='records', force_ascii=False))

    # Step 3: Update dashboard.html
    dashboard_path = Path('dashboard.html')
    with open(dashboard_path, 'r', encoding='utf-8') as f:
        html = f.read()

    if 'var EMBED=' in html:
        html = re.sub(
            r'var EMBED=\[.*?\];',
            f'var EMBED={json.dumps(stocks, ensure_ascii=False)};',
            html
        )

    with open(dashboard_path, 'w', encoding='utf-8') as f:
        f.write(html)
    shutil.copy(dashboard_path, 'index.html')
    print(f'  dashboard.html updated')

    # Step 4: Monday Tushare refresh
    if datetime.now().weekday() == 0:
        ok, msg = update_tushare_cache()
        print(f'  Dividend yield refresh: {msg}')

    # Step 5: PushPlus 微信推送（有 token 就推送，本地/云端通用）
    pushplus_token = os.getenv('PUSHPLUS_TOKEN', '')
    if pushplus_token and stocks:
        html_content = build_static_html(df)
        send_pushplus(pushplus_token, f'高股息筛选日报 ({len(stocks)}只)', html_content, 'html')
    elif pushplus_token:
        send_pushplus(pushplus_token, '高股息筛选 - 无结果',
                      '今日无符合条件的股票（股息率>3% + 市值>500亿 + 价格低位）', 'txt')

    # 本地环境：尝试打开浏览器（交互式有效，定时任务静默失败）
    if is_local_env():
        import webbrowser
        local_url = get_dashboard_url()
        print(f'  看板文件: {local_url}')
        try:
            webbrowser.open(local_url)
        except Exception:
            pass

    print(f'[{datetime.now():%Y-%m-%d %H:%M}] Done: {len(stocks)} stocks')


if __name__ == '__main__':
    main()
