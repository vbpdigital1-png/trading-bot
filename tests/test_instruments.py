import pytest

from fxbot.instruments import currencies, pip_size, timeframe_delta


def test_pip_size():
    assert pip_size("EUR_USD") == 0.0001
    assert pip_size("USD_JPY") == 0.01
    assert pip_size("GBP_JPY") == 0.01


def test_currencies():
    assert currencies("AUD_NZD") == ("AUD", "NZD")


@pytest.mark.parametrize("bad", ["EURUSD", "eur_usd", "EUR/USD", ""])
def test_bad_pair(bad):
    with pytest.raises(ValueError):
        pip_size(bad)


def test_unknown_timeframe():
    with pytest.raises(ValueError):
        timeframe_delta("M5")
