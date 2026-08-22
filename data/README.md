# Data folder

## CSV format for `--source csv`

Required columns:
- time (or datetime / date)
- open, high, low, close

Example:
```csv
time,open,high,low,close
2024-01-02 00:00:00,2050.10,2051.50,2049.20,2050.80
```

## yfinance (real gold)

```bash
python run_backtest.py --source yfinance
python run_backtest.py --source yfinance --symbol GC=F --interval 1h --period 730d
```

- `GC=F` = Gold Futures (good proxy for XAUUSD research)
- `15m` limited to ~60 days period
- `1h` supports longer periods (e.g. 730d)
