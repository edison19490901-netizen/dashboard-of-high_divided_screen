"""
看板识股 — 后端 API 服务
启动: python app.py
HTML 看板可独立打开（file:// 或 http://localhost:8080）
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

DIVIDEND_THRESHOLD = 3.0
MIN_MARKET_CAP = 500
MAX_PCT_FROM_LOW = 15       # 最新价距1年最低 < 15%
MAX_PCT_FROM_LOWER = 15     # 最新价距周线BB下轨 < 15%
PRICE_CACHE_FILE = CACHE_DIR / 'price_cache.json'


def load_token():
    from dotenv import load_dotenv
    for p in [BASE_DIR / '.env', BASE_DIR.parent / '.env']:
        if p.exists():
            load_dotenv(p)
    return os.getenv('TUSHARE_TOKEN', '')


# ════════════════════ 数据层 ════════════════════

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
    bs.login()
    today = datetime.now().strftime('%Y%m%d')
    for i, (_, row) in enumerate(df.iterrows()):
        df.at[i, 'price_date'] = today
        parts = row['code'].split('.')
        bs_code = f'{parts[1].lower()}.{parts[0]}' if len(parts) == 2 else row['code']
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
                continue
            dp = rs.get_data()
            if dp.empty:
                continue
            dp['close'] = pd.to_numeric(dp['close'], errors='coerce')
            dp.dropna(subset=['close'], inplace=True)
            if dp.empty:
                continue
            df.at[i, 'latest_price'] = round(float(dp['close'].iloc[-1]), 2)
            mn = float(dp['close'].min())
            df.at[i, 'min_price_1y'] = round(mn, 2)
            df.at[i, 'pct_from_low'] = round((df.at[i, 'latest_price'] - mn) / mn * 100, 1)

            # Bollinger Bands (周线: 20周MA ± 2×std)
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
        except Exception:
            pass
    bs.logout()
    return df


def apply_price_filter(df):
    """筛选：最新价距离1年最低 < 15% 且 距离周线BB下轨 < 15%"""
    if df.empty:
        return df
    mask = df['pct_from_low'].notna() & df['pct_from_lower'].notna()
    mask &= (df['pct_from_low'] < MAX_PCT_FROM_LOW) & (df['pct_from_lower'] < MAX_PCT_FROM_LOWER)
    return df[mask].copy()


def load_price_cache():
    """读取缓存的股价数据（快速）"""
    if PRICE_CACHE_FILE.exists():
        try:
            with open(PRICE_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return pd.DataFrame(data['stocks']), data.get('price_date', '')
        except Exception:
            pass
    return pd.DataFrame(), ''


def save_price_cache(df):
    """保存股价数据到缓存"""
    data = {
        'stocks': json.loads(df.to_json(orient='records', force_ascii=False)),
        'price_date': datetime.now().strftime('%Y%m%d'),
    }
    with open(PRICE_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def run_full_pipeline(force_refresh=False):
    """执行完整管线：Tushare筛选 → Baostock价格 → 价格过滤 → 缓存
    - force_refresh=False: 优先返回缓存（快速）；无缓存时仅返回Tushare基础数据（不含Baostock）
    - force_refresh=True: 强制执行Baostock管线并更新缓存
    """
    if not force_refresh:
        cached_df, _ = load_price_cache()
        if not cached_df.empty:
            return cached_df, True  # from_cache=True
        # 无缓存：只返回 Tushare 基础数据，不跑慢管线
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
        return False, 'TUSHARE_TOKEN 未配置（请在 .env 中设置）'
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
        return False, '找不到最近交易日'
    try:
        df = pro.daily_basic(trade_date=trade_date)
        if df is None or df.empty:
            return False, 'daily_basic 返回空'
    except Exception as e:
        return False, f'API 调用失败: {e}'
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE_DIR / f'daily_basic_{trade_date}.parquet', index=False)
    names = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
    names.to_parquet(CACHE_DIR / 'stock_names.parquet', index=False)
    return True, f'已更新 {len(df)} 只股票 ({trade_date})'


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
        else:
            self.send_error(404)

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
            self._json({'ok': False, 'error': '无缓存数据或无符合条件股票'}, 500)
            return
        data = json.loads(df.to_json(orient='records', force_ascii=False))
        today = datetime.now().strftime('%Y%m%d')
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
    print(f'API 服务: http://localhost:{port}')
    print(f'数据接口: http://localhost:{port}/api/data')
    print(f'更新接口: POST http://localhost:{port}/api/update')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')
        server.server_close()


if __name__ == '__main__':
    main()
