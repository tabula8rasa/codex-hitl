"""Expiry wire validation and original-message editing without pending bot state."""
import json
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from codex_hitl.config import BotConfig
from codex_hitl.contracts import ExpiryNotification
from codex_hitl.telegram_bot import create_app, render_message
from codex_hitl.telegram_bot.service import EXPIRY_NOTICE

CONFIG = BotConfig('internal-secret', 'telegram-secret', -123, 42, 'http://mcp')
HEADERS = {'Authorization': 'Bearer internal-secret'}


def notification(kind='approval'):
    return {'message_id': 77, 'message': {'request_id': str(uuid4()), 'type': kind,
            'title': 'Original <title>', 'description': 'Original\ncontent'}}


@pytest.mark.parametrize('mutation', ['zero', 'negative', 'bool', 'string', 'extra', 'chat', 'nested_extra', 'uuid', 'missing'])
def test_expiry_contract_is_strict(mutation):
    payload = notification()
    if mutation == 'zero': payload['message_id'] = 0
    if mutation == 'negative': payload['message_id'] = -1
    if mutation == 'bool': payload['message_id'] = True
    if mutation == 'string': payload['message_id'] = '77'
    if mutation == 'extra': payload['extra'] = True
    if mutation == 'chat': payload['chat_id'] = 100
    if mutation == 'nested_extra': payload['message']['chat_id'] = 100
    if mutation == 'uuid': payload['message']['request_id'] = 'not-a-uuid'
    if mutation == 'missing': payload.pop('message')
    with pytest.raises(ValidationError):
        ExpiryNotification.model_validate(payload)


@pytest.mark.parametrize('kind', ['approval', 'manual_action', 'question'])
async def test_expiry_edits_original_once_without_separate_message(kind):
    calls = []
    current = None

    async def telegram(request):
        nonlocal current
        payload = json.loads(request.content)
        calls.append((request.url.path.rsplit('/', 1)[1], payload))
        if current == payload:
            return httpx.Response(400, json={'ok': False, 'error_code': 400,
                'description': 'Bad Request: message is not modified: specified new message content and reply markup are exactly the same'})
        current = payload
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': 77, **payload}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as tg:
        app = create_app(CONFIG, telegram_client=tg, mcp_client=tg)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://bot') as client:
            body = notification(kind)
            for _ in range(2):
                response = await client.post('/internal/expire', json=body, headers=HEADERS)
                assert response.status_code == 200 and response.json() == {'updated': True}
            original = render_message(ExpiryNotification.model_validate(body).message, -123)['text']
            assert calls == [('editMessageText', {'chat_id': -123, 'message_id': 77,
                    'text': original + '\n\n' + EXPIRY_NOTICE,
                    'reply_markup': {'inline_keyboard': []}})] * 2
            assert current['text'].count(EXPIRY_NOTICE) == 1
            assert not hasattr(app.state.bot, 'pending')


async def test_expiry_auth_and_payload_fail_before_telegram():
    calls = []
    async def telegram(request):
        calls.append(request)
        return httpx.Response(200, json={'ok': True, 'result': True})
    async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as tg:
        app = create_app(CONFIG, telegram_client=tg, mcp_client=tg)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://bot') as client:
            for headers in ({}, {'Authorization': 'Bearer wrong'}):
                assert (await client.post('/internal/expire', json=notification(), headers=headers)).status_code == 401
            for body in ({}, {**notification(), 'chat_id': 99}, {**notification(), 'message_id': 0},
                         {**notification(), 'message': {'request_id': 'bad'}}):
                assert (await client.post('/internal/expire', json=body, headers=HEADERS)).status_code == 422
            assert not calls


@pytest.mark.parametrize('failure', ['deleted', 'oversized', 'permissions', 'api', 'network', 'timeout', 'json', 'invalid_result'])
async def test_expiry_failures_surface_safely_without_retry(failure, caplog):
    calls = []
    async def telegram(request):
        calls.append(json.loads(request.content))
        if failure == 'network': raise httpx.ConnectError('telegram-secret')
        if failure == 'timeout': raise TimeoutError('telegram-secret')
        if failure == 'json': return httpx.Response(200, text='telegram-secret')
        if failure == 'invalid_result': return httpx.Response(200, json={'ok': True, 'result': None})
        return httpx.Response(400, json={'ok': False, 'error_code': 400,
            'description': {'deleted': 'Bad Request: message to edit not found',
                            'oversized': 'Bad Request: message is too long',
                            'permissions': 'Bad Request: message cannot be edited',
                            'api': 'private telegram-secret'}[failure]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as tg:
        app = create_app(CONFIG, telegram_client=tg, mcp_client=tg)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://bot') as client:
            body = notification()
            if failure == 'oversized': body['message']['description'] = 'x' * 5000
            response = await client.post('/internal/expire', json=body, headers=HEADERS)
            assert response.status_code == 502
            assert response.json() == {'detail': 'Telegram expiry edit failed'}
            assert len(calls) == 1
            assert calls[0]['text'].endswith(body['message']['description'] + '\n\n' + EXPIRY_NOTICE)
            assert 'secret' not in response.text + caplog.text
            assert 'expiry edit failed' in caplog.text


@pytest.mark.parametrize('failure', [None, 'http', 'network', 'timeout', 'bad_response'])
async def test_mcp_expiry_is_terminal_before_notification(monkeypatch, caplog, failure):
    import asyncio
    from codex_hitl.config import MCPConfig
    from codex_hitl.contracts import AnswerRequest, Request
    from codex_hitl.mcp_server import lifecycle
    from codex_hitl.mcp_server.lifecycle import RequestService

    calls = []
    delivered = None
    service = None
    async def expired(future, seconds):
        assert seconds == 850
        raise TimeoutError
    monkeypatch.setattr(lifecycle, 'wait_for', expired)

    async def route(request):
        nonlocal delivered
        body = json.loads(request.content)
        calls.append(request.url.path)
        if request.url.path == '/internal/messages':
            delivered = body
            return httpx.Response(200, json={'message_id': 77})
        assert request.url.path == '/internal/expire'
        assert request.headers['authorization'] == 'Bearer internal-secret'
        assert request.extensions['timeout']['read'] == 10
        assert body == {'message_id': 77, 'message': delivered}
        assert not service.pending
        assert not service.receive_answer(AnswerRequest(request_id=delivered['request_id'], answer={'status': 'approved'}))
        await asyncio.sleep(0)
        if failure == 'network': raise httpx.ConnectError('private-secret')
        if failure == 'timeout': raise TimeoutError('private-secret')
        if failure == 'http': return httpx.Response(502, text='private-secret')
        return httpx.Response(200, json={'updated': False} if failure == 'bad_response' else {'updated': True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as client:
        service = RequestService(MCPConfig('internal-secret', 'http://bot'), client)
        result = await service.request(Request(type='approval', title='test', description='original'))
        assert result == {'status': 'timeout', 'error_code': 'HITL_TIMEOUT'}
        assert calls == ['/internal/messages', '/internal/expire']
        assert not service.pending
        assert 'secret' not in caplog.text
        assert ('expiry notification failed' in caplog.text) == (failure is not None)


async def test_mcp_total_expiry_budget_and_cancellation(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from codex_hitl.config import MCPConfig
    from codex_hitl.contracts import Request
    from codex_hitl.mcp_server import lifecycle
    from codex_hitl.mcp_server.lifecycle import RequestService

    budgets = []
    entered = asyncio.Event()
    released = asyncio.Event()
    mode = 'timeout'
    @asynccontextmanager
    async def controlled_budget(seconds):
        budgets.append(seconds)
        yield
        if len(budgets) % 2 == 0 and mode == 'timeout':
            raise TimeoutError
    async def expired(future, seconds):
        assert seconds == 850
        raise TimeoutError
    async def route(request):
        if request.url.path == '/internal/messages':
            return httpx.Response(200, json={'message_id': 77})
        entered.set()
        if mode == 'cancel': await released.wait()
        return httpx.Response(200, json={'updated': True})
    monkeypatch.setattr(lifecycle, 'timeout', controlled_budget)
    monkeypatch.setattr(lifecycle, 'wait_for', expired)
    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as client:
        service = RequestService(MCPConfig('internal-secret', 'http://bot'), client)
        request = Request(type='question', title='t', description='d')
        assert await service.request(request) == {'status': 'timeout', 'error_code': 'HITL_TIMEOUT'}
        assert budgets == [10, 10] and not service.pending
        mode = 'cancel'
        entered.clear()
        task = asyncio.create_task(service.request(request))
        await asyncio.wait_for(entered.wait(), 1)
        assert not service.pending
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert not service.pending


async def test_accepted_request_never_sends_expiry(monkeypatch):
    from codex_hitl.config import MCPConfig
    from codex_hitl.contracts import AnswerRequest, Request
    from codex_hitl.mcp_server.lifecycle import RequestService
    calls = []
    service = None
    async def route(request):
        body = json.loads(request.content)
        calls.append(request.url.path)
        assert service.receive_answer(AnswerRequest(request_id=body['request_id'], answer={'status': 'approved'}))
        return httpx.Response(200, json={'message_id': 77})
    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as client:
        service = RequestService(MCPConfig('internal-secret', 'http://bot'), client)
        assert await service.request(Request(type='approval', title='t', description='d')) == {'status': 'approved'}
        assert calls == ['/internal/messages'] and not service.pending


async def test_mcp_expiry_budget_cancels_stalled_http_body(monkeypatch):
    import asyncio
    from codex_hitl.config import MCPConfig
    from codex_hitl.contracts import Request
    from codex_hitl.mcp_server import lifecycle
    from codex_hitl.mcp_server.lifecycle import RequestService
    budgets = []
    cancelled = asyncio.Event()
    class StalledBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            try:
                await asyncio.Event().wait()
                yield b'never'
            finally:
                cancelled.set()
    async def expired(future, seconds):
        assert seconds == 850
        raise TimeoutError
    def controlled_timeout(seconds):
        budgets.append(seconds)
        assert seconds == 10
        return asyncio.timeout(.02 if len(budgets) == 2 else 1)
    async def route(request):
        if request.url.path == '/internal/messages':
            return httpx.Response(200, json={'message_id': 77})
        return httpx.Response(200, stream=StalledBody())
    monkeypatch.setattr(lifecycle, 'wait_for', expired)
    monkeypatch.setattr(lifecycle, 'timeout', controlled_timeout)
    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as client:
        service = RequestService(MCPConfig('internal-secret', 'http://bot'), client)
        assert await service.request(Request(type='approval', title='t', description='d')) == {
            'status': 'timeout', 'error_code': 'HITL_TIMEOUT'}
        assert cancelled.is_set() and not service.pending and budgets == [10, 10]


@pytest.mark.parametrize('body', [{}, {'updated': False}, {'updated': 1}, {'updated': 'true'},
                                   {'updated': True, 'extra': True}])
def test_expiry_response_requires_explicit_boolean_confirmation(body):
    from codex_hitl.contracts import ExpiryResponse
    with pytest.raises(ValidationError):
        ExpiryResponse.model_validate(body)


def test_exact_expiry_notice():
    assert EXPIRY_NOTICE == 'This request is no longer active. Your answer was not accepted.'
