"""
一键运行: 筛选 + 看板生成

用法:
    python run.py                  # 筛选 + 生成看板
    python run.py --skip-screener  # 只看板（使用已有 CSV）
    python run.py --open           # 生成后在浏览器中打开
"""

import argparse
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    parser = argparse.ArgumentParser(description="高市值高股息率筛选 + 看板")
    parser.add_argument("--skip-screener", action="store_true", help="跳过筛选，直接生成看板")
    parser.add_argument("--open", action="store_true", help="在浏览器中打开看板")
    parser.add_argument("--dividend", type=float, default=5.0, help="股息率阈值 (default: 5%%)")
    parser.add_argument("--market-cap", type=int, default=500, help="市值阈值 亿 (default: 500)")
    args = parser.parse_args()

    start_time = datetime.now()
    print("=" * 60)
    print("  网格 · 高市值高股息率 筛选系统")
    print(f"  市值 > {args.market_cap} 亿  |  股息率 > {args.dividend}%")
    print(f"  启动: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ── 1. 筛选 ──
    if not args.skip_screener:
        print("\n" + "=" * 60)
        print("  [1/2] 高股息率股票筛选")
        print("=" * 60)
        try:
            import screener
            # 覆盖阈值
            screener.DIVIDEND_THRESHOLD = args.dividend
            screener.MIN_MARKET_CAP = args.market_cap
            screener.main()
        except Exception as e:
            print(f"❌ 筛选失败: {e}")
            return 1
    else:
        print("\n⏭️ 跳过筛选")

    # ── 2. 看板 ──
    print("\n" + "=" * 60)
    print("  [2/2] 生成 HTML 看板")
    print("=" * 60)
    try:
        import dashboard
        dashboard.main()
    except Exception as e:
        print(f"❌ 看板生成失败: {e}")
        return 1

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n✅ 全部完成 — 耗时 {elapsed:.0f}s")

    # ── 打开浏览器 ──
    dashboard_path = Path("dashboard.html").absolute()
    if args.open:
        webbrowser.open(f"file:///{dashboard_path}")
        print(f"📱 已在浏览器中打开看板")
    else:
        print(f"📱 看板路径: file:///{dashboard_path}")
        print(f"   手动打开 或 运行 python run.py --open")


if __name__ == "__main__":
    main()
