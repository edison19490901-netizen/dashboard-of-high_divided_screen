"""
GitHub Actions daily update script
- Read Tushare cache + Baostock real-time prices
- Update dashboard.html
- Push via PushPlus to WeChat
"""
import sys, os, json, re, shutil, html as html_module
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Beijing timezone (UTC+8)
BJ_TZ = timezone(timedelta(hours=8))

def bj_now():
    """Return current datetime in Beijing timezone"""
    return datetime.now(BJ_TZ)

# Ensure we're in the project root
os.chdir(Path(__file__).resolve().parent)
sys.path.insert(0, '.')

from app import screen_from_cache, supplement_baostock, apply_price_filter, update_tushare_cache, save_price_cache


def get_dashboard_url():
    """Return dashboard URL based on deployment environment"""
    if os.getenv('RENDER'):
        return 'https://dashboard-of-high-divided-screen.onrender.com'
    if os.getenv('GITHUB_ACTIONS'):
        return 'https://edison19490901-netizen.github.io/dashboard-of-high_divided_screen/'
    # Local: open local HTML file directly
    root = os.path.dirname(os.path.abspath(__file__))
    return f'file:///{root.replace(chr(92), "/")}/dashboard.html'


def is_local_env():
    """Check if running in local environment"""
    return not os.getenv('RENDER') and not os.getenv('GITHUB_ACTIONS')


def send_pushplus(token: str, title: str, content: str, template: str = 'html') -> bool:
    """Send push notification via PushPlus to WeChat"""
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
    """Build compact TOP20 static HTML table (WeChat renderable)"""
    count = len(df)
    now = bj_now().strftime('%Y-%m-%d %H:%M')

    df_sorted = df.sort_values('dividend_yield', ascending=False)

    rows_html = ''
    for _, row in df_sorted.iterrows():
        name = html_module.escape(str(row.get('name', '-')))
        code = html_module.escape(str(row.get('code', '-')))
        price = row.get('latest_price', 0)
        dps = row.get('dividend_per_share')
        t6 = round(dps / 0.06, 2) if dps and dps > 0 else '-'
        t55 = round(dps / 0.055, 2) if dps and dps > 0 else '-'
        t5 = round(dps / 0.05, 2) if dps and dps > 0 else '-'
        t45 = round(dps / 0.045, 2) if dps and dps > 0 else '-'

        rows_html += (
            f'<tr><td style="text-align:left;font-weight:500;white-space:nowrap">'
            f'{name}<br><span style="font-size:10px;color:#8892b0">{code}</span></td>'
            f'<td style="font-weight:600">{price:.2f}</td>'
            f'<td style="font-weight:600">{t6}</td>'
            f'<td style="font-weight:600">{t55}</td>'
            f'<td style="font-weight:600">{t5}</td>'
            f'<td style="font-weight:600">{t45}</td></tr>')

    return (
        f'<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1.0">'
        f'<title>High Dividend Daily Report</title></head>'
        f'<body style="margin:0;padding:10px;font-family:-apple-system,PingFang SC,Microsoft YaHei,sans-serif;background:#fff;color:#1a1a2e">'
        f'<div style="text-align:center;padding:10px 0 14px;border-bottom:1px solid #e2e8f0;margin-bottom:10px">'
        f'<div style="font-size:17px;font-weight:700;color:#1a1a2e">High Dividend Daily Report</div>'
        f'<div style="color:#64748b;font-size:11px;margin-top:5px">{now} | Matching: <b style="color:#059669">{count}</b> stocks</div>'
        f'<div style="color:#94a3b8;font-size:10px;margin-top:2px">Div Yield>3% · Mkt Cap>50B · From 1Y Low<15% · From BB Low<15%</div></div>'
        f'<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12px;background:#fff">'
        f'<thead><tr style="background:#f1f5f9;color:#64748b;font-size:10px;letter-spacing:.5px">'
        f'<th style="padding:8px 4px;text-align:left">Name</th><th style="padding:8px 4px">Price</th>'
        f'<th style="padding:8px 4px">P@6%Div</th><th style="padding:8px 4px">P@5.5%Div</th>'
        f'<th style="padding:8px 4px">P@5%Div</th><th style="padding:8px 4px">P@4.5%Div</th></tr></thead>'
        f'<tbody>{rows_html}</tbody></table></div>'
        f'<div style="text-align:center;padding:10px;color:#94a3b8;font-size:10px;border-top:1px solid #e2e8f0;margin-top:10px">'
        f'Data sources: Tushare + Baostock | For reference only<br>'
        f'<a href="{get_dashboard_url()}" style="color:#6366f1">View Interactive Dashboard</a></div></body></html>')


def main():
    print(f'[{bj_now():%Y-%m-%d %H:%M}] Starting pipeline...')

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
                send_pushplus(pushplus_token, 'High Dividend Screener - No Data', 'No stocks in cache', 'txt')
        sys.exit(0)

    print(f'  Screened: {len(df)} stocks, fetching prices...')
    df_full = supplement_baostock(df.copy())  # All screened stocks with prices
    df = apply_price_filter(df_full)  # Filtered for EMBED
    print(f'  After filter: {len(df)} stocks')
    if not df.empty:
        save_price_cache(df)  # persist cache for Render deployment

    # EMBED update: use filtered stocks only
    if df.empty:
        print('No stocks match criteria — skipping EMBED update (keeping previous data)')
        stocks = None  # Signal: don't update EMBED
    else:
        stocks = json.loads(df.to_json(orient='records', force_ascii=False))

    # Step 3: Update dashboard.html (only if we have data)
    if stocks:
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
        print(f'  dashboard.html updated ({len(stocks)} stocks)')

    # Step 4: Monday Tushare refresh
    if bj_now().weekday() == 0:
        ok, msg = update_tushare_cache()
        print(f'  Dividend yield refresh: {msg}')

    # Step 5: PushPlus push — ALL screened stocks (before price filter), if token set
    pushplus_token = os.getenv('PUSHPLUS_TOKEN', '')
    if pushplus_token and not df_full.empty:
        html_content = build_static_html(df_full)
        send_pushplus(pushplus_token, f'High Dividend Daily Report ({len(df_full)} stocks)', html_content, 'html')
    elif pushplus_token:
        send_pushplus(pushplus_token, 'High Dividend Screener - No Results',
                      'No stocks match today (Div Yield>3% + Mkt Cap>50B + Low Price)', 'txt')

    # Local: try opening browser (works interactively, silent fail for scheduled tasks)
    if is_local_env():
        import webbrowser
        local_url = get_dashboard_url()
        print(f'  Dashboard: {local_url}')
        try:
            webbrowser.open(local_url)
        except Exception:
            pass

    print(f'[{bj_now():%Y-%m-%d %H:%M}] Done: {len(df_full)} stocks screened, {len(stocks) if stocks else 0} filtered')


if __name__ == '__main__':
    main()
