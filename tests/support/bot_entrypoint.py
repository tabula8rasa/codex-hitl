"""Factory URL injection for a QA container; production defaults stay intact."""
from codex_hitl.telegram_bot import create_app


def factory():
    return create_app(telegram_api_url='http://telegram-double:9000')
