"""
GitHub Actions daily update script
- Read Tushare cache + Baostock real-time prices
- Update dashboard.html
- Push via PushPlus to WeChat
"""
import sys, os, json, re, shutil, time, html as html_module
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

# Beijing timezone (UTC+8)
BJ_TZ = timezone(timedelta(hours=8))

def bj_now():
    """Return current datetime in Beijing timezone"""
    return datetime.now(BJ_TZ)

# Ensure we're in the project root
os.chdir(Path(__file__).resolve().parent)
sys.path.insert(0, '.')

from app import screen_from_cache, apply_price_filter, update_tushare_cache, save_price_cache

# ════════════════════ akshare Supplement ════════════════════

def supplement_akshare(df):
    """Supplement stock data with akshare (replaces Baostock when server is down)"""
    import akshare as ak
    import numpy as np

    if df.empty:
        return df

    today = bj_now().strftime('%Y%m%d %H:%M')
    fail_count = 0
    max_fail = 15

    for i, (_, row) in enumerate(df.iterrows()):
        if fail_count >= max_fail:
            print(f'  akshare: {max_fail} consecutive failures, skipping remaining {len(df) - i} stocks')
            break

        df.at[i, 'price_date'] = today
        code_raw = row['code']
        # Convert "600519.SH" → "600519"
        parts = code_raw.split('.')
        symbol = parts[0] if len(parts) == 2 else code_raw

        try:
            end = bj_now()
            start = end - timedelta(days=400)
            dp = ak.stock_zh_a_hist(
                symbol=symbol,
                period='daily',
                start_date=start.strftime('%Y%m%d'),
                end_date=end.strftime('%Y%m%d'),
                adjust='qfq',
            )
            if dp is None or dp.empty:
                fail_count += 1
                continue

            closes = pd.Series(pd.to_numeric(dp['收盘'], errors='coerce')).dropna()
            if len(closes) < 20:
                fail_count += 1
                continue

            df.at[i, 'latest_price'] = round(float(closes.iloc[-1]), 2)
            df.at[i, 'min_price_1y'] = round(float(closes.min()), 2)
            df.at[i, 'pct_from_low'] = round((df.at[i, 'latest_price'] - float(closes.min())) / float(closes.min()) * 100, 1)

            # Weekly Bollinger Bands
            try:
                dp['trade_date'] = pd.to_datetime(dp['日期'])
                dp_w = dp.set_index('trade_date')['收盘'].resample('W-FRI').last().dropna()
                weekly = pd.Series(pd.to_numeric(dp_w, errors='coerce')).dropna()
                if len(weekly) >= 20:
                    ma20 = weekly.rolling(20).mean()
                    std20 = weekly.rolling(20).std()
                    bb_up = float(ma20.iloc[-1] + 2 * std20.iloc[-1])
                    bb_lo = float(ma20.iloc[-1] - 2 * std20.iloc[-1])
                    df.at[i, 'bb_upper'] = round(bb_up, 2)
                    df.at[i, 'bb_lower'] = round(bb_lo, 2)
                    df.at[i, 'pct_from_upper'] = round((df.at[i, 'latest_price'] - bb_up) / bb_up * 100, 1)
                    df.at[i, 'pct_from_lower'] = round((df.at[i, 'latest_price'] - bb_lo) / bb_lo * 100, 1)
            except Exception:
                pass

            # Daily price history + daily BB for mini chart (last 60 days)
            try:
                close_list = [round(float(c), 2) for c in closes.values[-60:].tolist()]
                df.at[i, 'price_history'] = json.dumps(close_list)
                if len(close_list) >= 20:
                    s = pd.Series(close_list)
                    ma20_d = s.rolling(20).mean()
                    std20_d = s.rolling(20).std()
                    df.at[i, 'bb_daily_upper'] = json.dumps([round(float(v), 2) if pd.notna(v) else None for v in (ma20_d + 2 * std20_d).tolist()])
                    df.at[i, 'bb_daily_mid'] = json.dumps([round(float(v), 2) if pd.notna(v) else None for v in ma20_d.tolist()])
                    df.at[i, 'bb_daily_lower'] = json.dumps([round(float(v), 2) if pd.notna(v) else None for v in (ma20_d - 2 * std20_d).tolist()])
            except Exception:
                pass

            fail_count = 0

        except Exception as e:
            fail_count += 1
            if fail_count <= 3:
                print(f'  akshare error [{symbol}]: {e}')

        # Rate limit: 200ms between stocks
        time.sleep(0.2)

        if (i + 1) % 10 == 0:
            print(f'  akshare progress: {i + 1}/{len(df)}')

    return df


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
    """Build compact HTML table for PushPlus (under 20k chars)"""
    count = len(df)
    now = bj_now().strftime('%Y-%m-%d %H:%M')
    df_sorted = df.sort_values('dividend_yield', ascending=False)

    rows = ''
    for _, r in df_sorted.iterrows():
        name = html_module.escape(str(r.get('name', '-')))
        code = html_module.escape(str(r.get('code', '-')))
        price = r.get('latest_price', 0)
        dps = r.get('dividend_per_share')
        t6 = f'{dps/0.06:.2f}' if dps and dps > 0 else '-'
        t55 = f'{dps/0.055:.2f}' if dps and dps > 0 else '-'
        t5 = f'{dps/0.05:.2f}' if dps and dps > 0 else '-'
        t45 = f'{dps/0.045:.2f}' if dps and dps > 0 else '-'
        rows += f'<tr><td class="nl">{name}<span>{code}</span></td><td>{price:.2f}</td><td>{t6}</td><td>{t55}</td><td>{t5}</td><td>{t45}</td></tr>'

    css = 'body{margin:0;padding:10px;font-family:-apple-system,PingFang SC,Microsoft YaHei,sans-serif;background:#fff;color:#1a1a2e;font-size:12px}' \
          'h2{font-size:16px;text-align:center;margin:0 0 4px;color:#1a1a2e}' \
          '.info{text-align:center;font-size:10px;color:#64748b;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}' \
          'table{width:100%;border-collapse:collapse}' \
          'th{background:#f1f5f9;color:#64748b;font-size:10px;padding:6px 3px;text-align:left}' \
          'td{padding:5px 3px;border-bottom:1px solid #f1f5f9}' \
          '.nl{font-weight:500}.nl span{display:block;font-size:9px;color:#8892b0}' \
          '.ft{text-align:center;font-size:9px;color:#94a3b8;padding-top:8px;border-top:1px solid #e2e8f0;margin-top:8px}'

    return f'<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">' \
           f'<title>High Dividend Daily Report</title><style>{css}</style></head><body>' \
           f'<h2>High Dividend Daily Report</h2>' \
           f'<div class="info">{now} | <b style="color:#059669">{count}</b> stocks | Div&gt;3% · MktCap&gt;50B · Low&lt;15% · BB&lt;15%</div>' \
           f'<table><thead><tr><th>Name</th><th>Price</th><th>P@6%</th><th>P@5.5%</th><th>P@5%</th><th>P@4.5%</th></tr></thead>' \
           f'<tbody>{rows}</tbody></table>' \
           f'<div class="ft">Tushare + Baostock | <a href="{get_dashboard_url()}" style="color:#6366f1">Open Dashboard</a></div></body></html>'


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
    df_full = supplement_akshare(df.copy())
    akshare_ok = df_full['pct_from_low'].notna().any()
    if not akshare_ok:
        print('  akshare failed — using cached prices, skipping price filter')
        df = df_full
    else:
        df = apply_price_filter(df_full)
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

    # Step 5: PushPlus push — filtered stocks (after price filter), if token set
    pushplus_token = os.getenv('PUSHPLUS_TOKEN', '')
    if pushplus_token and stocks:
        html_content = build_static_html(df)
        ok = send_pushplus(pushplus_token, f'High Dividend Daily Report ({len(stocks)} stocks)', html_content, 'html')
        if not ok:
            print(f'  PushPlus: content size ~{len(html_content)} chars')
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
