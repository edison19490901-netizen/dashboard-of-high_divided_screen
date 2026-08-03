"""
A 股全市场 市值 > 500 亿 + 股息率 > 5% 筛选器

数据源（按优先级）:
  1. Tushare daily_basic — 全市场市值 + 股息率TTM（一次调用覆盖 ~5500 只）
  2. Baostock — 每股分红明细 + 总股本（Tushare 不可用时回退）

输出: screened_stocks_full.csv
"""

import math
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# ===================== 配置 =====================
DIVIDEND_THRESHOLD = 5.0      # 股息率阈值 (%)
MIN_MARKET_CAP = 500           # 最低市值 (亿)

# ===================== 回退候选池（Tushare + efinance 均不可用时使用） =====================
FALLBACK_CANDIDATES = [
    "601398.SH", "601939.SH", "601288.SH", "601988.SH", "600036.SH",
    "601328.SH", "600016.SH", "600000.SH", "601166.SH", "601818.SH",
    "002142.SZ", "600919.SH", "601229.SH", "600926.SH", "601838.SH",
    "601169.SH", "600015.SH", "601998.SH", "601658.SH", "601077.SH",
    "600900.SH", "600011.SH", "600886.SH", "600023.SH", "600025.SH",
    "600795.SH", "601985.SH", "003816.SZ", "600905.SH", "601619.SH",
    "601088.SH", "601898.SH", "600188.SH", "601225.SH", "601699.SH",
    "601857.SH", "600028.SH", "601808.SH",
    "600377.SH", "600012.SH", "600548.SH", "001965.SZ",
    "601000.SH", "600033.SH", "600269.SH", "601006.SH",
    "000651.SZ", "000333.SZ", "600690.SH",
    "000999.SZ", "600887.SH", "000895.SZ", "002032.SZ",
    "001979.SZ", "600048.SH", "000002.SZ",
    "601728.SH", "600941.SH",
    "000630.SZ", "600362.SH", "601899.SH",
    "601318.SH", "601628.SH", "601601.SH",
]


def _load_tushare():
    """加载 Tushare，失败返回 None."""
    try:
        import tushare as ts
        from dotenv import load_dotenv
        env_path = Path('.env')
        if env_path.exists():
            load_dotenv(env_path)
        token = os.getenv('TUSHARE_TOKEN', '')
        if not token or token.startswith('your_'):
            return None
        return ts.pro_api(token=token)
    except Exception:
        return None


def _get_latest_trade_date(pro) -> str:
    """获取最近交易日（YYYYMMDD）."""
    for offset in range(5):
        d = (datetime.now() - timedelta(days=offset)).strftime('%Y%m%d')
        try:
            df = pro.daily(trade_date=d, fields='trade_date')
            if not df.empty:
                return d
        except Exception:
            continue
    return datetime.now().strftime('%Y%m%d')


# ===================== Tushare 路径（主力） =====================

def _screen_via_local_cache() -> pd.DataFrame | None:
    """从本地 parquet 缓存筛选，最快路径。缓存不存在则返回 None。"""
    cache_dir = Path('cache')
    parquets = sorted(cache_dir.glob('daily_basic_*.parquet'), reverse=True)
    if not parquets:
        return None

    pqt = parquets[0]
    trade_date = pqt.stem.replace('daily_basic_', '')
    print(f"[本地缓存] {pqt.name}  ({trade_date})")

    df = pd.read_parquet(pqt)
    print(f"[本地缓存] {len(df)} 只股票")

    # 加载名称映射
    names_pqt = cache_dir / 'stock_names.parquet'
    name_map = {}
    if names_pqt.exists():
        names_df = pd.read_parquet(names_pqt)
        name_map = dict(zip(names_df['ts_code'], names_df['name']))

    # 市值过滤
    df['market_cap_billion'] = df['total_mv'] / 1e4
    large = df[df['market_cap_billion'] > MIN_MARKET_CAP].copy()
    print(f"[本地缓存] 市值 > {MIN_MARKET_CAP} 亿: {len(large)} 只")

    if large.empty:
        return pd.DataFrame()

    # 股息率过滤
    large['dv_ttm'] = pd.to_numeric(large['dv_ttm'], errors='coerce')
    high_div = large[large['dv_ttm'] > DIVIDEND_THRESHOLD].copy()
    print(f"[本地缓存] 市值 > {MIN_MARKET_CAP} 亿 + 股息率 > {DIVIDEND_THRESHOLD}%: {len(high_div)} 只")

    if high_div.empty:
        return pd.DataFrame()

    # 构建结果
    results = []
    for _, row in high_div.iterrows():
        code = row['ts_code']
        name = name_map.get(code, code)
        mcap = float(row['market_cap_billion'])
        price = float(row['close']) if pd.notna(row['close']) else 0.0
        div_yield = float(row['dv_ttm']) if pd.notna(row['dv_ttm']) else 0.0
        # 每股分红从 dv_ttm 推算（与股息率保持一致）
        div_per_share = round(div_yield / 100 * price, 4) if div_yield > 0 else float('nan')

        results.append({
            "code": code, "name": name,
            "market_cap_billion": round(mcap, 2),
            "latest_price": round(price, 2),
            "dividend_per_share": div_per_share,
            "dividend_yield": round(div_yield, 2),
            "data_date": trade_date,
        })

    df_result = pd.DataFrame(results)
    df_result = df_result.sort_values("dividend_yield", ascending=False).reset_index(drop=True)
    return df_result


def _screen_via_tushare_api() -> pd.DataFrame | None:
    """
    用 Tushare daily_basic API 实时拉取全市场数据。

    返回 DataFrame 或 None（失败时回退）。
    """
    pro = _load_tushare()
    if pro is None:
        print("[Tushare API] Token 未配置，跳过")
        return None

    try:
        trade_date = _get_latest_trade_date(pro)
        print(f"[Tushare API] 最新交易日: {trade_date}")

        df = pro.daily_basic(trade_date=trade_date)
        if df is None or df.empty:
            print("[Tushare API] daily_basic 返回空")
            return None

        total_stocks = len(df)
        print(f"[Tushare] 全市场 {total_stocks} 只股票")

        # 市值过滤
        df['market_cap_billion'] = df['total_mv'] / 1e4  # 万元→亿
        large = df[df['market_cap_billion'] > MIN_MARKET_CAP].copy()
        print(f"[Tushare] 市值 > {MIN_MARKET_CAP} 亿: {len(large)} 只")

        if large.empty:
            return pd.DataFrame()

        # 股息率过滤
        large['dv_ttm'] = pd.to_numeric(large['dv_ttm'], errors='coerce')
        high_div = large[large['dv_ttm'] > DIVIDEND_THRESHOLD].copy()
        print(f"[Tushare] 市值 > {MIN_MARKET_CAP} 亿 + 股息率 > {DIVIDEND_THRESHOLD}%: {len(high_div)} 只")

        if high_div.empty:
            return pd.DataFrame()

        # 批量获取股票名称
        codes = high_div['ts_code'].tolist()
        names = _get_names_tushare(pro, codes)

        # 构建结果
        results = []
        for _, row in high_div.iterrows():
            code = row['ts_code']
            name = names.get(code, code)
            mcap = float(row['market_cap_billion'])
            price = float(row['close']) if pd.notna(row['close']) else 0.0
            div_yield = float(row['dv_ttm']) if pd.notna(row['dv_ttm']) else 0.0

            # 每股分红从 dv_ttm 推算（保持一致性）
            div_per_share = round(div_yield / 100 * price, 4) if div_yield > 0 else float('nan')

            results.append({
                "code": code,
                "name": name,
                "market_cap_billion": round(mcap, 2),
                "latest_price": round(price, 2),
                "dividend_per_share": div_per_share,
                "dividend_yield": round(div_yield, 2),
                "data_date": trade_date,
            })

        df_result = pd.DataFrame(results)
        df_result = df_result.sort_values("dividend_yield", ascending=False).reset_index(drop=True)
        return df_result

    except Exception as e:
        print(f"[Tushare] 筛选失败: {e}")
        return None


def _get_names_tushare(pro, codes: list[str]) -> dict[str, str]:
    """批量获取股票名称."""
    try:
        df = pro.stock_basic(ts_code=','.join(codes), fields='ts_code,name')
        if df is not None and not df.empty:
            return dict(zip(df['ts_code'], df['name']))
    except Exception:
        pass
    return {}


def _supplement_baostock(df: pd.DataFrame) -> pd.DataFrame:
    """
    用 Baostock 补充每只股票的最新价 + 近 1 年最低价 + 差值%。

    为每只股票查询近 1 年日线，获取实际最新收盘价和最低价，
    计算 (最新价 - 最低价) / 最低价 × 100%。
    """
    if df.empty:
        return df

    import baostock as bs

    print(f'\n[Baostock] 补充最新价 + 近1年最低价（共 {len(df)} 只）...')
    bs.login()

    new_rows = []
    for i, (_, row) in enumerate(df.iterrows()):
        ts_code = row['code']
        parts = ts_code.split('.')
        bs_code = f'{parts[1].lower()}.{parts[0]}' if len(parts) == 2 else ts_code

        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=400)  # 1年 + margin
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')

            rs = bs.query_history_k_data_plus(
                bs_code, 'date,close',
                start_date=start_str, end_date=end_str,
                frequency='d', adjustflag='2',  # 前复权
            )
            if rs.error_code != '0':
                new_rows.append(row.to_dict())
                continue

            df_price = rs.get_data()
            if df_price.empty:
                new_rows.append(row.to_dict())
                continue

            df_price['close'] = pd.to_numeric(df_price['close'], errors='coerce')
            df_price.dropna(subset=['close'], inplace=True)
            if df_price.empty:
                new_rows.append(row.to_dict())
                continue

            bs_latest = float(df_price['close'].iloc[-1])
            bs_min_1y = float(df_price['close'].min())
            pct_from_low = (bs_latest - bs_min_1y) / bs_min_1y * 100 if bs_min_1y > 0 else 0

            new_row = row.to_dict()
            new_row['latest_price'] = round(bs_latest, 2)
            new_row['min_price_1y'] = round(bs_min_1y, 2)
            new_row['pct_from_low'] = round(pct_from_low, 1)
            new_rows.append(new_row)

            print(f'  [{i+1:2d}/{len(df)}] {row["name"]:8s}  最新={bs_latest:.2f}  '
                  f'最低(1年)={bs_min_1y:.2f}  距最低+{pct_from_low:.1f}%')

        except Exception as e:
            print(f'  [{i+1:2d}/{len(df)}] {row["name"]:8s}  查询失败: {e}')
            new_rows.append(row.to_dict())
            continue

    bs.logout()
    return pd.DataFrame(new_rows)


def _get_dividend_per_share_bs(ts_code: str) -> float:
    """从 Baostock 获取每股分红（仅 Baostock 回退路径使用）."""
    try:
        import baostock as bs
        parts = ts_code.split('.')
        if len(parts) != 2:
            return float('nan')
        bs_code = f'{parts[1].lower()}.{parts[0]}'
        bs.login()
        try:
            for year in ['2024', '2025']:
                rs = bs.query_dividend_data(code=bs_code, year=year, yearType='operate')
                if rs.error_code != '0':
                    continue
                df_div = rs.get_data()
                if df_div.empty:
                    continue
                div_col = 'dividCashPsBeforeTax'
                if div_col not in df_div.columns:
                    continue
                today = datetime.now()
                total = 0.0
                for _, row in df_div.iterrows():
                    date_str = str(row.get('dividOperateDate', '')).strip()
                    if not date_str or date_str == '0':
                        continue
                    try:
                        d = datetime.strptime(date_str, '%Y-%m-%d')
                        if d > today:
                            continue
                    except ValueError:
                        continue
                    val = pd.to_numeric(row[div_col], errors='coerce')
                    if val > 0:
                        total += val
                if total > 0:
                    return round(total, 4)
        finally:
            bs.logout()
    except Exception:
        pass
    return float('nan')


# ===================== Baostock 回退路径 =====================

def _to_bs_code(ts_code: str) -> str:
    parts = ts_code.split(".")
    return f"{parts[1].lower()}.{parts[0]}" if len(parts) == 2 else ts_code


def _get_total_shares_bs(bs_code: str) -> float:
    """Baostock 利润表 → 总股本."""
    import baostock as bs
    for year in ['2025', '2024']:
        try:
            rs = bs.query_profit_data(code=bs_code, year=year, quarter=4)
            if rs.error_code != '0':
                continue
            df = rs.get_data()
            if df.empty or 'totalShare' not in df.columns:
                continue
            shares = pd.to_numeric(df['totalShare'], errors='coerce').iloc[0]
            if shares > 0:
                return float(shares)
        except Exception:
            continue
    return float('nan')


def _get_dividend_bs(bs_code: str) -> float:
    """
    Baostock 分红查询 — 2024 优先，2025 兜底。
    过滤空日期/未来日期的记录。
    """
    import baostock as bs
    for year in ['2024', '2025']:
        rs = bs.query_dividend_data(code=bs_code, year=year, yearType='operate')
        if rs.error_code != '0':
            continue
        df_div = rs.get_data()
        if df_div.empty:
            continue
        div_col = 'dividCashPsBeforeTax'
        if div_col not in df_div.columns:
            continue

        today = datetime.now()
        total = 0.0
        for _, row in df_div.iterrows():
            date_str = str(row.get('dividOperateDate', '')).strip()
            if not date_str or date_str == '0':
                continue
            try:
                d = datetime.strptime(date_str, '%Y-%m-%d')
                if d > today:
                    continue
            except ValueError:
                continue
            val = pd.to_numeric(row[div_col], errors='coerce')
            if val > 0:
                total += val
        if total > 0:
            return total
    return 0.0


def _screen_via_baostock() -> pd.DataFrame:
    """
    Baostock 回退路径 — 遍历候选池，逐只查询最新价 + 分红 + 总股本。

    当 Tushare 不可用时使用。
    """
    import baostock as bs

    print(f"\n[Baostock] 正在逐只查询...（共 {len(FALLBACK_CANDIDATES)} 只）")

    end_date = datetime.now()
    lookback = end_date - timedelta(days=90)
    start_str = lookback.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    bs.login()
    results = []

    for i, ts_code in enumerate(FALLBACK_CANDIDATES, 1):
        bs_code = _to_bs_code(ts_code)
        try:
            # 最新价
            time.sleep(0.25)
            rs = bs.query_history_k_data_plus(
                bs_code, 'date,close',
                start_date=start_str, end_date=end_str,
                frequency='d', adjustflag='2',
            )
            if rs.error_code != '0':
                continue
            df_price = rs.get_data()
            if df_price.empty:
                continue
            df_price['close'] = pd.to_numeric(df_price['close'], errors='coerce')
            df_price.dropna(subset=['close'], inplace=True)
            if df_price.empty:
                continue
            latest_price = float(df_price['close'].iloc[-1])

            # 分红
            dividend = _get_dividend_bs(bs_code)
            if dividend <= 0:
                continue
            div_yield = (dividend / latest_price) * 100
            if div_yield < DIVIDEND_THRESHOLD:
                continue

            # 名称
            time.sleep(0.25)
            name = ts_code
            rs_name = bs.query_stock_basic(code=bs_code)
            if rs_name.error_code == '0':
                df_name = rs_name.get_data()
                if not df_name.empty and 'code_name' in df_name.columns:
                    name = df_name['code_name'].iloc[0]

            # 市值 = 总股本 × 最新价
            total_shares = _get_total_shares_bs(bs_code)
            mcap = total_shares * latest_price if total_shares == total_shares else float('nan')
            mcap_b = round(mcap / 1e8, 2) if mcap == mcap else float('nan')
            mcap_str = f'{mcap_b:.0f}亿' if mcap == mcap else 'N/A'

            print(f'  [{i:3d}/{len(FALLBACK_CANDIDATES)}] {name:8s} ({ts_code})  '
                  f'股息率={div_yield:.2f}%  价格={latest_price:.2f}  '
                  f'分红={dividend:.4f}  市值={mcap_str}')

            results.append({
                'code': ts_code, 'name': name,
                'market_cap_billion': mcap_b,
                'latest_price': round(latest_price, 2),
                'dividend_per_share': round(dividend, 4),
                'dividend_yield': round(div_yield, 2),
                'data_date': datetime.now().strftime('%Y-%m-%d'),
            })

        except Exception as e:
            print(f'  [{i}/{len(FALLBACK_CANDIDATES)}] {ts_code} 查询失败: {e}')
            continue

    bs.logout()

    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values('dividend_yield', ascending=False).reset_index(drop=True)
    return df


# ===================== 主入口 =====================

def screen_high_dividend() -> pd.DataFrame:
    """
    全市场高股息筛选流程:
      1. Tushare API — 实时全市场市值 + 股息率
      2. 本地缓存 — API 失败时从 parquet 读取
      3. Baostock 候选池 — 以上均失败时的兜底
    筛选完成后，用 Baostock 补充最新价 + 近1年最低价 + 差值%。
    """
    print('=' * 60)
    print('  高股息率股票筛选器')
    print(f'  市值 > {MIN_MARKET_CAP} 亿  |  股息率 > {DIVIDEND_THRESHOLD}%')
    print('=' * 60)

    df = None
    source = ''

    # ── 1. Tushare API（主力）──
    print()
    df = _screen_via_tushare_api()
    if df is not None and not df.empty:
        source = 'Tushare API（全市场实时）'

    # ── 2. 本地缓存 ──
    if df is None:
        df = _screen_via_local_cache()
        if df is not None and not df.empty:
            source = '本地缓存（parquet）'

    # ── 3. Baostock 候选池回退 ──
    if df is None:
        print('\n⚠️  Tushare API 和本地缓存均不可用，回退到 Baostock 候选池（非全市场）')
        df = _screen_via_baostock()
        source = 'Baostock 候选池（非全市场）'

    # ── Baostock 补充价差数据 ──
    if not df.empty:
        print(f'\n数据来源: {source}')
        df = _supplement_baostock(df)

    return df


def save_results(df: pd.DataFrame):
    """保存 CSV."""
    if df.empty:
        print('\n⚠️ 未找到符合条件的股票')
        return

    path = 'screened_stocks_full.csv'
    df.to_csv(path, index=False, encoding='utf-8-sig')

    print(f'\n✅ 筛选完成! 共 {len(df)} 只股票')
    print(f'   完整数据: {path}')

    print(f'\n{"=" * 60}')
    print('  股息率排名:')
    for i, (_, row) in enumerate(df.iterrows(), 1):
        mcap = f'{row["market_cap_billion"]:.0f}亿' if row['market_cap_billion'] == row['market_cap_billion'] else 'N/A'
        div_share = f'{row["dividend_per_share"]:.4f}' if row['dividend_per_share'] == row['dividend_per_share'] else 'N/A'
        pct_low = row.get('pct_from_low', float('nan'))
        pct_str = f'+{pct_low:.1f}%' if pct_low == pct_low else 'N/A'
        min_1y = row.get('min_price_1y', float('nan'))
        min_str = f' 最低(1年)={min_1y:.2f}' if min_1y == min_1y else ''
        print(f'  {i:2d}. {row["name"]:8s} ({row["code"]:12s})  '
              f'股息率: {row["dividend_yield"]:5.2f}%  '
              f'最新: {row["latest_price"]:6.2f}  '
              f'{min_str}  '
              f'距最低: {pct_str}')


def main():
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    df = screen_high_dividend()
    save_results(df)
    return df


if __name__ == '__main__':
    main()
