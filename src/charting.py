from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import yfinance as yf

from src.portfolio_parser import format_ticker_for_yfinance


def create_price_chart(ticker: str, output_dir: Path) -> Path | None:
    output_dir.mkdir(parents=True, exist_ok=True)
    yf_symbol = format_ticker_for_yfinance(ticker)
    df = yf.download(yf_symbol, period="3mo", interval="1d", progress=False, auto_adjust=True)
    if df.empty or "Close" not in df:
        return None

    chart_path = output_dir / f"{ticker}_chart.png"
    plt.figure(figsize=(10, 4))
    plt.plot(df.index, df["Close"], label="Close Price")
    plt.title(f"{ticker} - 3 Month Price Trend")
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(chart_path)
    plt.close()
    return chart_path
