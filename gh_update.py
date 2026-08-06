"""
GitHub Actions 每日更新脚本
- 读取 Tushare 缓存 + Baostock 实时股价
- 更新 dashboard.html
- 不处理 git push / PushPlus（由 workflow 负责）
"""
import sys, os, json, re, shutil
from datetime import datetime
from pathlib import Path

# Ensure we're in the project root
os.chdir(Path(__file__).resolve().parent)
sys.path.insert(0, '.')

from app import screen_from_cache, supplement_baostock, apply_price_filter, update_tushare_cache


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
        sys.exit(0)

    print(f'  Screened: {len(df)} stocks, fetching prices...')
    df = supplement_baostock(df)
    df = apply_price_filter(df)
    print(f'  After filter: {len(df)} stocks')

    if df.empty:
        print('No stocks match criteria')
        # Still update HTML with empty data so the dashboard reflects reality
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

    print(f'[{datetime.now():%Y-%m-%d %H:%M}] Done: {len(stocks)} stocks')


if __name__ == '__main__':
    main()
