import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from codex_hitl.auth import internal_headers, require_internal_token
from codex_hitl.config import BotConfig, MCPConfig


@pytest.fixture
def environment(monkeypatch):
    values = dict(INTERNAL_API_TOKEN='test-token', BOT_API_URL='http://bot:8101', TELEGRAM_BOT_TOKEN='test-bot-token', TELEGRAM_CHAT_ID='-123', TELEGRAM_ALLOWED_USER_ID='456', HITL_API_URL='http://mcp:8100')
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


def test_service_config(environment, monkeypatch):
    assert BotConfig.from_env().telegram_chat_id == -123
    assert MCPConfig.from_env().bot_api_url == 'http://bot:8101'
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN')
    assert MCPConfig.from_env().internal_api_token == 'test-token'
    with pytest.raises(ValueError, match='TELEGRAM_BOT_TOKEN'):
        BotConfig.from_env()
    assert 'test-token' not in repr(MCPConfig.from_env())


@pytest.mark.parametrize('key', ['INTERNAL_API_TOKEN','BOT_API_URL','TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID','TELEGRAM_ALLOWED_USER_ID','HITL_API_URL'])
def test_missing_config(environment, monkeypatch, key):
    monkeypatch.delenv(key)
    factory = MCPConfig if key == 'BOT_API_URL' else BotConfig
    with pytest.raises(ValueError, match=key):
        factory.from_env()


@pytest.mark.parametrize('key,value', [('TELEGRAM_CHAT_ID','abc'), ('TELEGRAM_CHAT_ID','0'), ('TELEGRAM_ALLOWED_USER_ID','-1'), ('TELEGRAM_ALLOWED_USER_ID','2.0'), ('TELEGRAM_ALLOWED_USER_ID','0'), ('HITL_API_URL','file:///tmp/x'), ('BOT_API_URL','http://user:password@bot')])
def test_invalid_config(environment, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match=key):
        (MCPConfig if key == 'BOT_API_URL' else BotConfig).from_env()


@pytest.mark.parametrize('headers,expected', [({},401), ({'Authorization':'Bearer wrong'},401), ({'Authorization':'test-token'},401), (internal_headers('test-token'),200)])
async def test_auth_before_effects(headers, expected):
    app = FastAPI()
    effects = []
    @app.post('/internal', dependencies=[Depends(require_internal_token('test-token'))])
    async def endpoint():
        effects.append(True)
        return {'ok':True}
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/internal', headers=headers, json={})
    assert response.status_code == expected
    assert bool(effects) == (expected == 200)
