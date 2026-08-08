"""
Dashboard Stock Screener — Backend API
Start: python app.py
Dashboard HTML can be opened standalone (file:// or http://localhost:8080)
"""
import json, os, sys, time
from datetime import datetime, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / 'cache'
if not CACHE_DIR.exists():
    CACHE_DIR = BASE_DIR.parent / 'cache'

# Load .env at startup so all os.getenv() calls work everywhere
try:
    from dotenv import load_dotenv
    for p in [BASE_DIR / '.env', BASE_DIR.parent / '.env']:
        if p.exists():
            load_dotenv(p)
except ImportError:
    pass

DIVIDEND_THRESHOLD = 3.0
MIN_MARKET_CAP = 500
MAX_PCT_FROM_LOW = 15       # Price within 15% of 1Y low
MAX_PCT_FROM_LOWER = 15     # Price within 15% of weekly BB lower
PRICE_CACHE_FILE = CACHE_DIR / 'price_cache.json'


def load_token():
    return os.getenv('TUSHARE_TOKEN', '')


# ════════════════════ Data Layer ════════════════════

def screen_from_cache():
    pqts = sorted(CACHE_DIR.glob('daily_basic_*.parquet'), reverse=True)
    if not pqts:
        return None
    pqt = pqts[0]
    trade_date = pqt.stem.replace('daily_basic_', '')
    df = pd.read_parquet(pqt)

    names_pqt = CACHE_DIR / 'stock_names.parquet'
    name_map = {}
    if names_pqt.exists():
        ndf = pd.read_parquet(names_pqt)
        name_map = dict(zip(ndf['ts_code'], ndf['name']))

    df['mcap_b'] = df['total_mv'] / 1e4
    large = df[df['mcap_b'] > MIN_MARKET_CAP].copy()
    large['dv'] = pd.to_numeric(large['dv_ttm'], errors='coerce')
    high = large[large['dv'] > DIVIDEND_THRESHOLD].copy()
    if high.empty:
        return pd.DataFrame()

    results = []
    for _, r in high.iterrows():
        price = float(r['close']) if pd.notna(r['close']) else 0
        div_y = float(r['dv']) if pd.notna(r['dv']) else 0
        results.append({
            'code': r['ts_code'],
            'name': name_map.get(r['ts_code'], r['ts_code']),
            'market_cap_billion': round(float(r['mcap_b']), 2),
            'latest_price': round(price, 2),
            'dividend_yield': round(div_y, 2),
            'dividend_per_share': round(div_y / 100 * price, 4) if div_y > 0 else None,
            'min_price_1y': None,
            'pct_from_low': None,
            'bb_upper': None, 'bb_lower': None,
            'pct_from_upper': None, 'pct_from_lower': None,
            'data_date': trade_date,
            'price_date': datetime.now().strftime('%Y%m%d'),
        })
    return pd.DataFrame(results)


def supplement_baostock(df):
    import baostock as bs
    if df.empty:
        return df

    # Login to Baostock (with retry)
    login_ok = False
    for attempt in range(3):
        try:
            lg = bs.login()
            if lg.error_code == '0':
                login_ok = True
                break
            print(f'  Baostock login failed (attempt {attempt+1}/3): {lg.error_msg}')
            time.sleep(2)
        except Exception as e:
            print(f'  Baostock login error (attempt {attempt+1}/3): {e}')
            time.sleep(2)
    if not login_ok:
        print('  Baostock login failed, skipping real-time price update (using Tushare cache)')
        return df

    today = datetime.now().strftime('%Y%m%d %H:%M')
    fail_count = 0
    max_fail = 20  # consecutive failures threshold

    for i, (_, row) in enumerate(df.iterrows()):
        if fail_count >= max_fail:
            print(f'  Baostock: {max_fail} consecutive failures, skipping remaining {len(df) - i} stocks')
            break

        df.at[i, 'price_date'] = today
        parts = row['code'].split('.')
        bs_code = f'{parts[1].lower()}.{parts[0]}' if len(parts) == 2 else row['code']

        # Retry up to 2 times per stock
        success = False
        for retry in range(2):
            try:
                end = datetime.now()
                start = end - timedelta(days=400)
                rs = bs.query_history_k_data_plus(
                    bs_code, 'date,close',
                    start_date=start.strftime('%Y-%m-%d'),
                    end_date=end.strftime('%Y-%m-%d'),
                    frequency='d', adjustflag='2',
                )
                if rs.error_code != '0':
                    fail_count += 1
                    break
                dp = rs.get_data()
                if dp.empty:
                    fail_count += 1
                    break
                dp['close'] = pd.to_numeric(dp['close'], errors='coerce')
                dp.dropna(subset=['close'], inplace=True)
                if dp.empty:
                    fail_count += 1
                    break

                df.at[i, 'latest_price'] = round(float(dp['close'].iloc[-1]), 2)
                mn = float(dp['close'].min())
                df.at[i, 'min_price_1y'] = round(mn, 2)
                df.at[i, 'pct_from_low'] = round((df.at[i, 'latest_price'] - mn) / mn * 100, 1)

                # Dividend yield & market cap from Tushare dv_ttm, not recalculated with price
                # Bollinger Bands (weekly)
                try:
                    dp_dt = dp.copy()
                    dp_dt['trade_date'] = pd.to_datetime(dp_dt['date']) if 'date' in dp_dt.columns else pd.to_datetime(dp_dt.index)
                    dp_dt = dp_dt.set_index('trade_date').sort_index()
                    weekly = dp_dt['close'].resample('W-FRI').last().dropna()
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

                fail_count = 0  # reset consecutive failure count on success
                success = True
                break
            except Exception:
                if retry == 0:
                    time.sleep(0.5)
                else:
                    fail_count += 1

        # Rate limit: 150ms between stocks
        time.sleep(0.15)

        # Save daily price history + daily BB for mini chart (last 60 days)
        try:
            closes = [round(float(c), 2) for c in dp['close'].values[-60:].tolist()]
            df.at[i, 'price_history'] = json.dumps(closes)
            if len(closes) >= 20:
                import numpy as np
                s = pd.Series(closes)
                ma20_d = s.rolling(20).mean()
                std20_d = s.rolling(20).std()
                df.at[i, 'bb_daily_upper'] = json.dumps([round(float(v), 2) if pd.notna(v) else None for v in (ma20_d + 2 * std20_d).tolist()])
                df.at[i, 'bb_daily_mid'] = json.dumps([round(float(v), 2) if pd.notna(v) else None for v in ma20_d.tolist()])
                df.at[i, 'bb_daily_lower'] = json.dumps([round(float(v), 2) if pd.notna(v) else None for v in (ma20_d - 2 * std20_d).tolist()])
        except Exception:
            pass

    bs.logout()
    return df


def apply_price_filter(df):
    """Filter: price within 15% of 1Y low AND within 15% of weekly BB lower"""
    if df.empty:
        return df
    mask = df['pct_from_low'].notna() & df['pct_from_lower'].notna()
    mask &= (df['pct_from_low'] < MAX_PCT_FROM_LOW) & (df['pct_from_lower'] < MAX_PCT_FROM_LOWER)
    return df[mask].copy()


def load_price_cache():
    """Load cached price data (fast)"""
    if PRICE_CACHE_FILE.exists():
        try:
            with open(PRICE_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return pd.DataFrame(data['stocks']), data.get('price_date', '')
        except Exception:
            pass
    return pd.DataFrame(), ''


def save_price_cache(df):
    """Save price data to cache"""
    data = {
        'stocks': json.loads(df.to_json(orient='records', force_ascii=False)),
        'price_date': datetime.now().strftime('%Y%m%d'),
    }
    with open(PRICE_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def run_full_pipeline(force_refresh=False):
    """Full pipeline: Tushare screen -> Baostock prices -> price filter -> cache
    - force_refresh=False: prefer cache (fast); fallback to Tushare base data only
    - force_refresh=True: full Baostock pipeline + cache update
    """
    if not force_refresh:
        cached_df, _ = load_price_cache()
        if not cached_df.empty:
            return cached_df, True  # from_cache=True
        # No cache: return Tushare base data only, skip slow pipeline
        df = screen_from_cache()
        return (df if df is not None else pd.DataFrame()), False

    df = screen_from_cache()
    if df is None or df.empty:
        return pd.DataFrame(), False

    df = supplement_baostock(df)
    df = apply_price_filter(df)
    if not df.empty:
        save_price_cache(df)
    return df, False


def update_tushare_cache():
    token = load_token()
    if not token:
        return False, 'TUSHARE_TOKEN not configured (add it to .env file in app.py directory)'
    import tushare as ts
    pro = ts.pro_api(token=token)
    trade_date = None
    for offset in range(5):
        d = (datetime.now() - timedelta(days=offset)).strftime('%Y%m%d')
        try:
            if not pro.daily(trade_date=d, fields='trade_date').empty:
                trade_date = d
                break
        except Exception:
            continue
    if not trade_date:
        return False, 'Could not find recent trading date'
    try:
        df = pro.daily_basic(trade_date=trade_date)
        if df is None or df.empty:
            return False, 'daily_basic returned empty'
    except Exception as e:
        return False, f'API call failed: {e}'
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE_DIR / f'daily_basic_{trade_date}.parquet', index=False)
    names = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
    names.to_parquet(CACHE_DIR / 'stock_names.parquet', index=False)
    return True, f'Updated {len(df)} stocks ({trade_date})'


# ════════════════════ PushPlus ════════════════════

import html as html_mod
import urllib.request

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
    url = 'http://www.pushplus.plus/send'
    data = json.dumps({'token': token, 'title': title, 'content': content, 'template': template}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode())
        return result.get('code') == 200


def build_push_html(df) -> str:
    count = len(df)
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    df_sorted = df.sort_values('pct_from_low', ascending=True).head(20)

    def pct_color(v):
        try: v = float(v); return '#059669' if v <= 8 else '#d97706' if v <= 12 else '#dc2626'
        except: return '#64748b'

    def div_color(v):
        try: v = float(v); return '#059669' if v >= 5 else '#d97706' if v >= 4 else '#dc2626'
        except: return '#64748b'

    rows = ''
    for _, r in df_sorted.iterrows():
        name = html_mod.escape(str(r.get('name', '-')))
        code = html_mod.escape(str(r.get('code', '-')))
        rows += (
            f'<tr><td style="text-align:left;font-weight:500;white-space:nowrap">'
            f'{name}<br><span style="font-size:10px;color:#8892b0">{code}</span></td>'
            f'<td style="font-weight:600">{r.get("latest_price",0):.2f}</td>'
            f'<td style="color:{div_color(r.get("dividend_yield",0))};font-weight:600">{r.get("dividend_yield",0):.1f}%</td>'
            f'<td style="color:{pct_color(r.get("pct_from_low","-"))};font-weight:600">{r.get("pct_from_low","-")}%</td>'
            f'<td style="color:{pct_color(r.get("pct_from_lower","-"))};font-weight:600">{r.get("pct_from_lower","-")}%</td>'
            f'<td style="white-space:nowrap">{r.get("market_cap_billion",0):.0f}B</td></tr>')

    more = f'<div style="text-align:center;padding:8px;color:#d97706;font-size:12px">Showing TOP 20 of {count} total</div>' if count > 20 else ''
    return (
        f'<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1.0"><title>High Dividend Daily Report</title></head>'
        f'<body style="margin:0;padding:10px;font-family:-apple-system,PingFang SC,Microsoft YaHei,sans-serif;background:#fff;color:#1a1a2e">'
        f'<div style="text-align:center;padding:10px 0 14px;border-bottom:1px solid #e2e8f0;margin-bottom:10px">'
        f'<div style="font-size:17px;font-weight:700;color:#1a1a2e">High Dividend Daily Report</div>'
        f'<div style="color:#64748b;font-size:11px;margin-top:5px">{now} | Matching: <b style="color:#059669">{count}</b> stocks</div></div>'
        f'{more}<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12px;background:#fff">'
        f'<thead><tr style="background:#f1f5f9;color:#64748b;font-size:10px;letter-spacing:.5px">'
        f'<th style="padding:8px 4px;text-align:left">Name</th><th style="padding:8px 4px">Price</th>'
        f'<th style="padding:8px 4px">Div Yield</th><th style="padding:8px 4px">From Low</th>'
        f'<th style="padding:8px 4px">From BB</th><th style="padding:8px 4px">Mkt Cap</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div>'
        f'<div style="text-align:center;padding:10px;color:#94a3b8;font-size:10px;border-top:1px solid #e2e8f0;margin-top:10px">'
        f'Data sources: Tushare + Baostock | For reference only<br>'
        f'<a href="{get_dashboard_url()}" style="color:#6366f1;font-size:12px">View Interactive Dashboard</a></div></body></html>')


# ════════════════════ Web Server ════════════════════

HTML_FILE = BASE_DIR / 'dashboard.html'


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/data':
            self._api_data()
        elif path == '/api/health':
            self._json({'status': 'ok', 'cache': CACHE_DIR.exists()})
        elif path in ('/', '/dashboard.html'):
            self._serve_html()
        elif path in ('/manifest.json', '/sw.js', '/icon-192.png', '/icon-512.png'):
            self._send_static(path)
        else:
            self.send_error(404)

    def _send_static(self, path):
        file_path = BASE_DIR / path.lstrip('/')
        if not file_path.exists():
            self.send_error(404)
            return
        content_types = {
            '.json': 'application/json',
            '.js': 'application/javascript',
            '.png': 'image/png',
        }
        ext = file_path.suffix
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', content_types.get(ext, 'application/octet-stream'))
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'public, max-age=86400')
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/update':
            self._api_update()
        elif path == '/api/refresh_prices':
            self._api_refresh_prices()
        else:
            self.send_error(404)

    def _api_refresh_prices(self):
        df, _ = run_full_pipeline(force_refresh=True)
        if df is None or df.empty:
            self._json({'ok': False, 'error': 'No cached data or no stocks matching criteria'}, 500)
            return
        data = json.loads(df.to_json(orient='records', force_ascii=False))
        today = datetime.now().strftime('%Y%m%d %H:%M')

        # PushPlus push (if token configured, works locally and on cloud)
        token = os.getenv('PUSHPLUS_TOKEN', '')
        if token and not df.empty:
            try:
                html_content = build_push_html(df)
                ok = send_pushplus(token, f'High Dividend Daily Report ({len(data)} stocks)', html_content, 'html')
                print(f'[{datetime.now():%H:%M}] PushPlus: {"OK" if ok else "FAIL"}')
            except Exception as e:
                print(f'[{datetime.now():%H:%M}] PushPlus error: {e}')

        self._json({'ok': True, 'stocks': data, 'count': len(data), 'price_date': today})

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_html(self):
        if HTML_FILE.exists():
            content = HTML_FILE.read_bytes()
        else:
            content = b'<h1>dashboard.html not found</h1>'
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _api_data(self):
        df, from_cache = run_full_pipeline(force_refresh=False)
        if not df.empty:
            data = json.loads(df.to_json(orient='records', force_ascii=False))
        else:
            data = []
        self._json({'stocks': data, 'count': len(data)})

    def _api_update(self):
        ok, msg = update_tushare_cache()
        if ok:
            self._json({'ok': True, 'message': msg})
        else:
            self._json({'ok': False, 'error': msg}, 500)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        print(f'[{datetime.now().strftime("%H:%M:%S")}] {args[0]}')


def main():
    port = int(os.getenv('PORT', '8080'))
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f'API Server: http://localhost:{port}')
    print(f'Data endpoint: http://localhost:{port}/api/data')
    print(f'Update endpoint: POST http://localhost:{port}/api/update')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped')
        server.server_close()


if __name__ == '__main__':
    main()
