"""定时更新脚本 — 供 Windows 任务计划程序调用"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from app import screen_from_cache, supplement_baostock, apply_price_filter, update_tushare_cache
import json, re, shutil
from datetime import datetime

print(f'[{datetime.now():%Y-%m-%d %H:%M}] 开始定时更新...')

# 1. 更新股价（Baostock，无限制）
df = screen_from_cache()
if df is not None and not df.empty:
    df = supplement_baostock(df)
    df = apply_price_filter(df)
    stocks = json.loads(df.to_json(orient='records', force_ascii=False))
    print(f'  股价已更新: {len(stocks)} 只')

    # 2. 更新看板 HTML
    with open('dashboard.html', 'r', encoding='utf-8') as f:
        html = f.read()
    if 'var EMBED=' in html:
        html = re.sub(r'var EMBED=\[.*?\];', f'var EMBED={json.dumps(stocks, ensure_ascii=False)};', html)
    with open('dashboard.html', 'w', encoding='utf-8') as f:
        f.write(html)
    shutil.copy('dashboard.html', 'index.html')

    # 3. 推送 GitHub（可选，取消注释启用）
    # import subprocess
    # subprocess.run(['git', 'add', 'dashboard.html', 'index.html'])
    # subprocess.run(['git', 'commit', '-m', f'auto update {datetime.now():%Y%m%d_%H%M}'])
    # subprocess.run(['git', 'push'])

    print(f'  看板已更新')

# 4. 每周一更新股息率（Tushare，5次/天限制）
if datetime.now().weekday() == 0:  # 周一
    ok, msg = update_tushare_cache()
    print(f'  股息率: {msg}')

print(f'[{datetime.now():%Y-%m-%d %H:%M}] 完成')
