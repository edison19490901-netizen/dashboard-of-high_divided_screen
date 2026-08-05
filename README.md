# Dashboard of High Dividend Screen

A-share all-market high-dividend low-valuation stock screening dashboard.  
Filters **market cap > 500B CNY**, **dividend yield > 3%**, **price within 15% of 1-year low**, and **price within 15% of weekly BB lower band** from ~5,500 listed stocks, with Bollinger Bands and buy-weight scoring.

## Quick Start

```bash
pip install -r requirements.txt

# Set your Tushare token
echo TUSHARE_TOKEN=your_token > .env

# Start the API server
python app.py

# Open dashboard.html in browser
```

## Architecture

```
dashboard.html  ──AJAX──>  app.py (port 8080)
   │                          │
   │  Embedded fallback       ├── GET  /api/data    → screening results JSON
   │  data (offline mode)     ├── POST /api/update  → refresh Tushare cache
   │                          └── GET  /            → serve dashboard.html
   │
   └── Standalone: open directly via file://
```

## Data Pipeline

| Step | Source | Data |
|---|---|---|
| Market cap + dividend yield | Tushare `daily_basic` (cached as parquet) | ~5,500 stocks |
| Filter | JS in dashboard | mcap > 500B, yield > 3%, pct_from_low < 15%, pct_from_lower < 15% |
| Latest price + 1Y low + BB | Baostock | OHLC daily → weekly BB(20,2) |
| Buy weight | JS formula | See below |

## Buy Weight Formula

```
Buy Weight = 0.4 × LowScore + 0.4 × DivScore + 0.2 × BBScore

LowScore  = max(0, 50 − pctFromLow) / 45
DivScore  = (dividendYield − 3) / (maxYield − 3)
BBScore   = max(0, 30 − pctFromBBLower) / 30
```

## Dashboard Columns

| # | Column | Source |
|---|---|---|
| 1 | Stock name + code | Tushare |
| 2 | Market cap (B CNY) | Tushare |
| 3 | Latest price | Baostock |
| 4 | 1-year low | Baostock |
| 5 | % from low | Calculated |
| 6 | Dividend yield (TTM) | Tushare |
| 7 | Dividend per share | Calculated |
| 8 | BB lower band (weekly) | Baostock → calculated |
| 9 | % from BB lower | Calculated |
| 10 | Buy weight (0–100) | Formula |

## Features

- **Card grid** / **Data table** dual view
- Search, sort by any column
- Color-coded indicators (green/yellow/red)
- Export to Excel (.xls)
- Mobile responsive
- Offline mode (embedded fallback data)

## Files

```
├── app.py              # Python API server
├── dashboard.html       # Standalone dashboard (open directly)
├── requirements.txt     # tushare, baostock, pandas, pyarrow, python-dotenv
├── .env.example         # Config template
├── .gitignore
└── README.md
```

## Rate Limits

Tushare free tier: `daily_basic` limited to **1 call/hour** and **5 calls/day**.  
Data is cached locally as parquet — subsequent runs are instant.

## Disclaimer

For educational purposes only. Not investment advice.
