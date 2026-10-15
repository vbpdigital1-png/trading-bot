import json
import logging

from fxbot.monitor.logger import get_logger, log_event, setup_logging


def test_json_lines_written_per_utc_day(tmp_path):
    setup_logging(tmp_path, "INFO", console=False)
    log = get_logger("risk")
    log_event(log, "signal_rejected", pair="EUR_USD", reason="max_open_trades")
    log_event(log, "debug_noise", level=logging.DEBUG)
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        log.exception("unhandled")

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1 and len(files[0].stem) == 10  # YYYY-MM-DD
    lines = [json.loads(line) for line in files[0].read_text().splitlines()]
    assert len(lines) == 2  # DEBUG filtered out
    first = lines[0]
    assert first["event"] == "signal_rejected"
    assert first["module"] == "risk"
    assert first["pair"] == "EUR_USD"
    assert first["reason"] == "max_open_trades"
    assert first["ts"].endswith("+00:00")
    assert "RuntimeError: boom" in lines[1]["exc"]
