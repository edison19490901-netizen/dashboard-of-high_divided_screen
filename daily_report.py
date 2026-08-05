"""
每日收盘后自动运行 → 筛选结果发送到手机微信
触发时间：每个交易日 16:00
手机推送：PushPlus（微信公众号）
看板托管：GitHub Pages（免费）

使用前：
  1. 打开 pushplus.plus → 微信扫码登录 → 获取 token
  2. 将 token 写入 .env 文件: PUSHPLUS_TOKEN=你的token
  3. GitHub 仓库 Settings → Pages → Source: main/root → Save
     看板地址: https://edison19490901-netizen.github.io/dashboard-of-high_divided_screen/
  4. 设置 Windows 任务计划程序每日 16:00 运行此脚本
"""

import sys, os, json, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

# GitHub Pages 看板地址
PAGES_URL = 'https://edison19490901-netizen.github.io/dashboard-of-high_divided_screen/'
GIT_PUSH_URL = 'git@github.com:edison19490901-netizen/dashboard-of-high_divided_screen.git'

from app import (screen_from_cache, supplement_baostock, apply_price_filter,
                 update_tushare_cache, save_price_cache, load_token)

import re, shutil


def load_pushplus_token():
    """从 .env 读取 PushPlus token"""
    from dotenv import load_dotenv
    for p in [os.path.join(os.path.dirname(__file__), '.env'),
              os.path.join(os.path.dirname(__file__), '..', '.env')]:
        if os.path.exists(p):
            load_dotenv(p)
    return os.getenv('PUSHPLUS_TOKEN', '')


def is_trading_day() -> bool:
    """简单判断：周一到周五"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    return True


def run_pipeline():
    """运行完整筛选管线"""
    print(f'[{datetime.now():%Y-%m-%d %H:%M}] 开始运行筛选管线...')

    df = screen_from_cache()
    if df is None or df.empty:
        return None, '缓存无数据，请先运行 app.py 更新 Tushare 缓存'

    print(f'  基础筛选: {len(df)} 只股票，正在补充股价...')
    df = supplement_baostock(df)

    df = apply_price_filter(df)
    print(f'  价格过滤后: {len(df)} 只股票')

    if not df.empty:
        save_price_cache(df)

    if datetime.now().weekday() == 0:
        ok, msg = update_tushare_cache()
        print(f'  股息率更新: {msg}')

    if not df.empty:
        stocks = json.loads(df.to_json(orient='records', force_ascii=False))
        dashboard_path = os.path.join(os.path.dirname(__file__), 'dashboard.html')
        if os.path.exists(dashboard_path):
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
            shutil.copy(dashboard_path,
                        os.path.join(os.path.dirname(__file__), 'index.html'))
            print(f'  看板 HTML 已更新')

    return df, None


def git_push_dashboard() -> bool:
    """将 dashboard.html 推送到 Pages 仓库根目录（作为 index.html）"""
    try:
        import subprocess
        import tempfile

        root = os.path.dirname(__file__)
        dashboard_src = os.path.join(root, 'dashboard.html')
        if not os.path.exists(dashboard_src):
            print('  dashboard.html 不存在，跳过推送')
            return False

        pages_dir = os.path.join(tempfile.gettempdir(), 'dashboard_pages_repo')

        # 克隆或更新 Pages 仓库
        if os.path.exists(os.path.join(pages_dir, '.git')):
            print('  拉取 Pages 仓库...')
            subprocess.run(['git', 'fetch', 'origin', 'master'],
                           cwd=pages_dir, capture_output=True, timeout=30)
            subprocess.run(['git', 'reset', '--hard', 'origin/master'],
                           cwd=pages_dir, capture_output=True, timeout=30)
        else:
            print('  克隆 Pages 仓库...')
            r = subprocess.run(
                ['git', 'clone', '--depth=1', GIT_PUSH_URL, pages_dir],
                capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                # 空仓库，初始化
                if os.path.exists(pages_dir):
                    import shutil as _s
                    _s.rmtree(pages_dir, ignore_errors=True)
                os.makedirs(pages_dir, exist_ok=True)
                subprocess.run(['git', 'init'], cwd=pages_dir,
                               capture_output=True, check=True)
                subprocess.run(['git', 'remote', 'add', 'origin', GIT_PUSH_URL],
                               cwd=pages_dir, capture_output=True, check=True)

        # 复制 dashboard.html 为根目录 index.html
        shutil.copy(dashboard_src, os.path.join(pages_dir, 'index.html'))

        # 提交推送
        subprocess.run(['git', 'add', 'index.html'],
                       cwd=pages_dir, capture_output=True, check=True)
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        r = subprocess.run(['git', 'diff', '--cached', '--quiet'],
                           cwd=pages_dir, capture_output=True)
        if r.returncode == 0:
            subprocess.run(['git', 'commit', '--allow-empty',
                           '-m', f'auto: dashboard update {now}'],
                           cwd=pages_dir, capture_output=True, check=True)
        else:
            subprocess.run(['git', 'commit', '-m', f'auto: dashboard update {now}'],
                           cwd=pages_dir, capture_output=True, check=True)
        subprocess.run(['git', 'push', '-u', 'origin', 'master'],
                       cwd=pages_dir, capture_output=True, check=True, timeout=60)
        print('  看板已推送到 GitHub Pages')
        return True
    except Exception as e:
        print(f'  git push 失败: {e}')
        return False


def send_pushplus(token: str, title: str, content: str, template: str = 'html') -> bool:
    """通过 PushPlus 推送到微信"""
    try:
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
                print(f'  PushPlus推送成功: {title}')
                return True
            else:
                print(f'  PushPlus推送失败: {result}')
                return False
    except Exception as e:
        print(f'  PushPlus推送异常: {e}')
        return False


def build_static_html(df) -> str:
    """生成纯静态 HTML 表格（TOP20，微信里可直接渲染）"""
    import html as html_module

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
        f'<a href="{PAGES_URL}" style="color:#6366f1">查看完整交互看板</a></div></body></html>')


def main():
    if not is_trading_day():
        print(f'[{datetime.now():%Y-%m-%d %H:%M}] 非交易日，跳过')
        return

    token = load_pushplus_token()
    if not token:
        print('未配置 PUSHPLUS_TOKEN')
        print('   请写入 .env 文件: PUSHPLUS_TOKEN=你的token')
        return

    df, error = run_pipeline()
    if error:
        print(f'[!] {error}')
        send_pushplus(token, '高股息筛选 - 运行异常', error, 'txt')
        return

    if df is None or df.empty:
        send_pushplus(token, '高股息筛选 - 无结果',
                      '今日无符合条件的股票（股息率>3% + 市值>500亿 + 价格低位）', 'txt')
        print('无符合条件的股票')
        return

    git_push_dashboard()

    html_content = build_static_html(df)
    send_pushplus(token, f'高股息筛选日报 ({len(df)}只)', html_content, 'html')

    print(f'  推送完成: {len(df)}只 | 看板: {PAGES_URL}')
    print(f'\n[{datetime.now():%Y-%m-%d %H:%M}] 完成')


if __name__ == '__main__':
    main()
