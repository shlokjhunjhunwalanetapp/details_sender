from src.portfolio_parser import format_ticker_for_yfinance, parse_tickers_from_text


def test_parse_tickers_from_command_text() -> None:
    tickers = parse_tickers_from_text("/updatestocks RELIANCE, tcs\nINFY;RELIANCE")
    assert tickers == ["RELIANCE", "TCS", "INFY"]


def test_format_ticker_for_yfinance_suffix() -> None:
    assert format_ticker_for_yfinance("INFY") == "INFY.NS"
    assert format_ticker_for_yfinance("TCS.NS") == "TCS.NS"
