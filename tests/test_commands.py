from src.portfolio_parser import parse_single_ticker
from src.bot import _portfolio_list_message, HELP_TEXT


def test_parse_single_ticker_basic() -> None:
    assert parse_single_ticker("/addstock ZOMATO", "addstock") == "ZOMATO"


def test_parse_single_ticker_with_bot_suffix() -> None:
    assert parse_single_ticker("/addstock@mybot INFY", "addstock") == "INFY"


def test_parse_single_ticker_lowercase_normalised() -> None:
    assert parse_single_ticker("/removestock reliance", "removestock") == "RELIANCE"


def test_parse_single_ticker_empty_returns_none() -> None:
    assert parse_single_ticker("/addstock", "addstock") is None


def test_portfolio_list_message_empty() -> None:
    msg = _portfolio_list_message([])
    assert "empty" in msg.lower()


def test_portfolio_list_message_shows_tickers() -> None:
    msg = _portfolio_list_message(["RELIANCE", "TCS"])
    assert "RELIANCE" in msg
    assert "TCS" in msg
    assert "2 stock(s)" in msg


def test_portfolio_list_message_shows_company_name() -> None:
    msg = _portfolio_list_message(["INFY"])
    assert "Infosys" in msg


def test_help_text_lists_all_commands() -> None:
    for cmd in ("/start", "/help", "/list", "/addstock", "/removestock", "/updatestocks"):
        assert cmd in HELP_TEXT
