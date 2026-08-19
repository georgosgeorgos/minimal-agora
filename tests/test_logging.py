import logging

from minimal_agora.logging import configure_logging, get_logger, trajectory_context


def test_get_logger_returns_bound_logger():
    configure_logging()
    log = get_logger("test.module")
    assert hasattr(log, "info")
    assert hasattr(log, "warning")
    assert hasattr(log, "bind")


def test_configure_logging_console_mode():
    configure_logging(force_json=False)
    log = get_logger("test.console")
    log.info("test_event", key="value")


def test_configure_logging_json_mode():
    configure_logging(force_json=True)
    log = get_logger("test.json")
    log.info("test_event", key="value")


def test_trajectory_id_binding():
    configure_logging()
    token = trajectory_context.set(42)
    try:
        tid = trajectory_context.get()
        assert tid == 42
    finally:
        trajectory_context.reset(token)
    assert trajectory_context.get() is None


def test_trajectory_id_default_none():
    assert trajectory_context.get() is None


def test_logger_with_trajectory_context(capfd):
    configure_logging(force_json=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    token = trajectory_context.set(7)
    try:
        log = get_logger("test.ctx")
        log.info("ctx_event", step=1)
        captured = capfd.readouterr()
        assert "trajectory_id" in captured.err
        assert "7" in captured.err
    finally:
        trajectory_context.reset(token)
