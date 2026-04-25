from __future__ import annotations

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import yfinance as yf

from src.portfolio_parser import format_ticker_for_yfinance

logger = logging.getLogger(__name__)


CHART_PERIODS: list[tuple[str, str, str, str]] = [
    ("3mo", "1d", "3M", "3 Month"),
    ("1y", "1d", "1Y", "1 Year"),
    ("max", "1wk", "ALL", "All Time"),
]


def _render_chart(
    ticker: str,
    yf_symbol: str,
    period: str,
    interval: str,
    label_suffix: str,
    title_suffix: str,
    output_dir: Path,
) -> Path | None:
    try:
        df = yf.download(
            yf_symbol,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
        )
        if df.empty or "Close" not in df:
            logger.info("No data for %s (%s)", ticker, period)
            return None

        chart_path = output_dir / f"{ticker}_{label_suffix}_chart.png"
        plt.figure(figsize=(10, 4))
        plt.plot(df.index, df["Close"], label="Close Price")
        plt.title(f"{ticker} - {title_suffix} Price Trend")
        plt.xlabel("Date")
        plt.ylabel("Price")
        plt.grid(alpha=0.25)
        plt.legend()
        plt.tight_layout()
        plt.savefig(chart_path)
        return chart_path
    except Exception:
        logger.exception("Failed generating %s chart for %s", label_suffix, ticker)
        return None
    finally:
        plt.close()


def create_price_charts(ticker: str, output_dir: Path) -> list[tuple[str, Path]]:
    """Create 3M, 1Y and All-time charts for the given ticker.

    Returns a list of (label, path) tuples for charts that were created
    successfully.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    yf_symbol = format_ticker_for_yfinance(ticker)

    results: list[tuple[str, Path]] = []
    for period, interval, label, title in CHART_PERIODS:
        path = _render_chart(
            ticker=ticker,
            yf_symbol=yf_symbol,
            period=period,
            interval=interval,
            label_suffix=label,
            title_suffix=title,
            output_dir=output_dir,
        )
        if path is not None:
            results.append((title, path))
    return results


def create_price_chart(ticker: str, output_dir: Path) -> Path | None:
    """Backwards-compatible single-chart helper (3M)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    yf_symbol = format_ticker_for_yfinance(ticker)
    return _render_chart(
        ticker=ticker,
        yf_symbol=yf_symbol,
        period="3mo",
        interval="1d",
        label_suffix="3M",
        title_suffix="3 Month",
        output_dir=output_dir,
    )
