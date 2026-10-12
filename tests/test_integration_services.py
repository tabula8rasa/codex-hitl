"""Real SDK transport plus both service apps and a Telegram HTTP double."""
import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from codex_hitl.config import BotConfig, MCPConfig
from codex_hitl.mcp_server import create_app as create_mcp
from codex_hitl.telegram_bot import create_app as create_bot

TOKEN = 'qa-internal'
HEADERS = {'Authorization': f'Bearer {TOKEN}'}


class TelegramDouble:
    def __init__(self):
        self.calls = []
        self.messages = asyncio.Queue()
        self.updates = asyncio.Queue()
        self.fail_send = False
        self.fail_edit = False
        self.early = None
        self.serial = 0
        self.sent = {}

    async def request(self, request):
        method = request.url.path.rsplit('/', 1)[1]
        body = json.loads(request.content)
        self.calls.append((method, body))
        if method == 'getMe':
            result = {'id': 777, 'is_bot': True}
        elif method == 'getUpdates':
            result = [await self.updates.get()]
        elif method == 'sendMessage':
            if self.fail_send:
                return httpx.Response(503)
            self.serial += 1
            result = {'message_id': self.serial, 'from': {'id': 777, 'is_bot': True},
                      'chat': {'id': 42}, **body}
            self.sent[self.serial] = result
            if body['text'].startswith('HITL '):
                await self.messages.put(result)
                if self.early:
                    await self.early(result)
        elif method == 'editMessageText':
            if self.fail_edit:
                return httpx.Response(400, json={'ok': False, 'error_code': 400,
                                               'description': 'Bad Request: message cannot be edited'})
            result = self.sent[body['message_id']]
            assert result['chat']['id'] == body['chat_id']
            result.update(text=body['text'], reply_markup=body['reply_markup'])
        else:
            result = True
        return httpx.Response(200, json={'ok': True, 'result': result})

    def update(self, message, status='approved', user=99):
        self.serial += 1
        common = {'update_id': self.serial}
        if status == 'answered' or status == 'text':
            return {**common, 'message': {'message_id': self.serial, 'from': {'id': user},
                    'chat': {'id': 42}, 'text': 'QA text', 'reply_to_message': message}}
        action = {'approved': 'approve', 'rejected': 'reject', 'completed': 'done', 'unable': 'unable'}[status]
        request_id = message['text'].split()[1]
        return {**common, 'callback_query': {'id': str(self.serial), 'from': {'id': user},
                'message': message, 'data': f'{action}:{request_id}'}}


@asynccontextmanager
async def integrated():
    telegram = TelegramDouble()
    apps = {}
    answer_responses = []

    async def route_mcp(request):
        assert request.headers['Authorization'] == HEADERS['Authorization']
        response = await httpx.ASGITransport(app=apps['mcp']).handle_async_request(request)
        await response.aread()
        answer_responses.append(response.json())
        return response

    async def route_bot(request):
        assert request.headers['Authorization'] == HEADERS['Authorization']
        return await httpx.ASGITransport(app=apps['bot']).handle_async_request(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(telegram.request)) as tg, \
            httpx.AsyncClient(transport=httpx.MockTransport(route_mcp)) as answer, \
            httpx.AsyncClient(transport=httpx.MockTransport(route_bot)) as delivery:
        apps['mcp'] = create_mcp(MCPConfig(TOKEN, 'http://bot'), bot_client=delivery)
        apps['bot'] = create_bot(BotConfig(TOKEN, 'qa-bot', 42, 99, 'http://mcp'), telegram_client=tg, mcp_client=answer)
        async with apps['bot'].router.lifespan_context(apps['bot']), apps['mcp'].router.lifespan_context(apps['mcp']):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=apps['mcp'])) as client:
                async with streamable_http_client('http://127.0.0.1:8100/mcp', http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        yield session, apps, telegram, answer_responses
        assert not apps['mcp'].state.service.pending
        assert apps['bot'].state.bot.polling_task is None


def call(session, kind):
    return asyncio.create_task(session.call_tool('hitl.request', {'type': kind, 'title': 'QA title', 'description': 'QA description'}))


async def next_message(telegram):
    return await asyncio.wait_for(telegram.messages.get(), 3)


async def eventually(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(.005)


@pytest.mark.parametrize(('kind', 'status'), [('approval','approved'), ('approval','rejected'), ('question','answered'), ('manual_action','completed'), ('manual_action','unable')])
async def test_full_sdk_polling_roundtrip(kind, status):
    async with integrated() as (session, apps, tg, answers):
        task = call(session, kind)
        message = await next_message(tg)
        assert 'QA title' in message['text'] and 'QA description' in message['text']
        await tg.updates.put(tg.update(message, status))
        result = await asyncio.wait_for(task, 3)
        expected = {'status': status, **({'answer': 'QA text'} if status == 'answered' else {})}
        assert not result.isError and result.structuredContent == expected
        await eventually(lambda: answers == [{'accepted': True}])
        if kind != 'question':
            await eventually(lambda: any(m == 'editMessageReplyMarkup' for m, _ in tg.calls))
        assert not apps['mcp'].state.service.pending
        assert not any(m == 'editMessageText' for m, _ in tg.calls)


async def test_reversed_parallel_answers_and_duplicate():
    async with integrated() as (session, apps, tg, answers):
        first = call(session, 'approval')
        m1 = await next_message(tg)
        second = call(session, 'question')
        m2 = await next_message(tg)
        await tg.updates.put(tg.update(m2, 'answered'))
        assert (await asyncio.wait_for(second, 3)).structuredContent['status'] == 'answered'
        assert not first.done()
        await tg.updates.put(tg.update(m1, 'rejected'))
        assert (await asyncio.wait_for(first, 3)).structuredContent == {'status': 'rejected'}
        edits_before = sum(m == 'editMessageReplyMarkup' for m, _ in tg.calls)
        await tg.updates.put(tg.update(m1, 'approved'))
        await eventually(lambda: len(answers) == 3)
        assert answers == [{'accepted': True}, {'accepted': True}, {'accepted': False}]
        assert sum(m == 'editMessageReplyMarkup' for m, _ in tg.calls) == edits_before
        await eventually(lambda: any(m == 'sendMessage' and 'no longer active' in b['text'] for m, b in tg.calls))


async def test_answer_before_delivery_returns():
    async with integrated() as (session, apps, tg, answers):
        tg.early = lambda msg: apps['bot'].state.bot.handle_update(tg.update(msg))
        result = await asyncio.wait_for(call(session, 'approval'), 3)
        assert result.structuredContent == {'status': 'approved'}
        assert answers == [{'accepted': True}]


@pytest.mark.parametrize('kind', ['approval', 'manual_action'])
async def test_unauthorized_and_forbidden_text_leave_call_pending(kind):
    async with integrated() as (session, apps, tg, answers):
        task = call(session, kind)
        msg = await next_message(tg)
        bot = apps['bot'].state.bot
        await bot.handle_update(tg.update(msg, 'text', user=100))
        assert not answers and not any(m == 'deleteMessage' for m, _ in tg.calls)
        await bot.handle_update(tg.update(msg, 'text'))
        assert any(m == 'deleteMessage' for m, _ in tg.calls)
        assert not answers and not task.done()
        await bot.handle_update(tg.update(msg, 'approved' if kind == 'approval' else 'completed'))
        assert not (await asyncio.wait_for(task, 3)).isError


async def test_auth_and_invalid_answers_have_no_effect():
    async with integrated() as (session, apps, tg, answers):
        task = call(session, 'approval')
        msg = await next_message(tg)
        payload = {'request_id': msg['text'].split()[1], 'answer': {'status': 'approved'}}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=apps['mcp']), base_url='http://mcp') as client:
            for headers in ({}, {'Authorization': 'Bearer wrong'}):
                assert (await client.post('/internal/answer', json=payload, headers=headers)).status_code == 401
            wrong = {**payload, 'answer': {'status': 'answered', 'answer': 'wrong type'}}
            assert (await client.post('/internal/answer', json=wrong, headers=HEADERS)).json() == {'accepted': False}
            malformed = {**payload, 'answer': {'status': 'answered'}}
            assert (await client.post('/internal/answer', json=malformed, headers=HEADERS)).status_code == 422
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=apps['bot']), base_url='http://bot') as client:
            before = len(tg.calls)
            assert (await client.post('/internal/messages', json={}, headers={})).status_code == 401
            assert len(tg.calls) == before
        assert not task.done()
        await apps['bot'].state.bot.handle_update(tg.update(msg))
        assert not (await asyncio.wait_for(task, 3)).isError


@pytest.mark.parametrize('kind', ['approval', 'manual_action', 'question'])
async def test_timeout_late_answer_and_cleanup(monkeypatch, kind):
    from codex_hitl.mcp_server import lifecycle
    from codex_hitl.telegram_bot import render_message
    from codex_hitl.contracts import Message
    from codex_hitl.telegram_bot.service import EXPIRY_NOTICE
    async def expired(future, timeout):
        assert timeout == 850
        raise TimeoutError
    monkeypatch.setattr(lifecycle, 'wait_for', expired)
    async with integrated() as (session, apps, tg, answers):
        result = await asyncio.wait_for(call(session, kind), 3)
        assert result.structuredContent == {'status': 'timeout', 'error_code': 'HITL_TIMEOUT'}
        msg = await next_message(tg)
        original = render_message(Message(request_id=msg['text'].split()[1], type=kind,
                                          title='QA title', description='QA description'), 42)['text']
        assert msg['text'] == original + '\n\n' + EXPIRY_NOTICE
        assert msg['reply_markup'] == {'inline_keyboard': []}
        assert sum(m == 'sendMessage' for m, _ in tg.calls) == 1
        await apps['bot'].state.bot.handle_update(tg.update(msg, {'approval': 'approved', 'manual_action': 'completed', 'question': 'answered'}[kind]))
        assert answers == [{'accepted': False}]
        assert not apps['mcp'].state.service.pending


async def test_telegram_send_failure_cleans_original_sdk_call():
    async with integrated() as (session, apps, tg, answers):
        tg.fail_send = True
        result = await asyncio.wait_for(call(session, 'approval'), 3)
        assert result.isError
        assert not apps['mcp'].state.service.pending and not answers


async def test_competing_button_answers_accept_exactly_one():
    async with integrated() as (session, apps, tg, answers):
        task = call(session, 'approval')
        msg = await next_message(tg)
        bot = apps['bot'].state.bot
        await asyncio.gather(bot.handle_update(tg.update(msg, 'approved')), bot.handle_update(tg.update(msg, 'rejected')))
        assert sorted(a['accepted'] for a in answers) == [False, True]
        assert (await asyncio.wait_for(task, 3)).structuredContent['status'] in {'approved', 'rejected'}


async def test_concurrent_expirations_edit_only_their_original_messages(monkeypatch):
    from codex_hitl.mcp_server import lifecycle
    from codex_hitl.telegram_bot.service import EXPIRY_NOTICE
    gate = asyncio.Event()
    async def expired(future, seconds):
        assert seconds == 850
        await gate.wait()
        raise TimeoutError
    monkeypatch.setattr(lifecycle, 'wait_for', expired)
    async with integrated() as (session, apps, tg, answers):
        tasks = [call(session, kind) for kind in ['approval', 'manual_action', 'question']]
        messages = [await next_message(tg) for _ in tasks]
        originals = {m['message_id']: m['text'] for m in messages}
        gate.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), 3)
        assert all(r.structuredContent == {'status': 'timeout', 'error_code': 'HITL_TIMEOUT'} for r in results)
        edits = [body for method, body in tg.calls if method == 'editMessageText']
        assert {e['message_id'] for e in edits} == set(originals) and len(edits) == 3
        for edit in edits:
            assert edit['text'] == originals[edit['message_id']] + '\n\n' + EXPIRY_NOTICE
            assert edit['reply_markup'] == {'inline_keyboard': []}
        assert not answers and not apps['mcp'].state.service.pending


async def test_telegram_expiry_failure_preserves_original_timeout(monkeypatch, caplog):
    from codex_hitl.mcp_server import lifecycle
    async def expired(future, seconds):
        assert seconds == 850
        raise TimeoutError
    monkeypatch.setattr(lifecycle, 'wait_for', expired)
    async with integrated() as (session, apps, tg, answers):
        tg.fail_edit = True
        result = await asyncio.wait_for(call(session, 'approval'), 3)
        assert not result.isError
        assert result.structuredContent == {'status': 'timeout', 'error_code': 'HITL_TIMEOUT'}
        message = await next_message(tg)
        assert not apps['mcp'].state.service.pending
        await apps['bot'].state.bot.handle_update(tg.update(message))
        assert answers == [{'accepted': False}]
        assert sum(m == 'editMessageText' for m, _ in tg.calls) == 1
        assert 'Telegram expiry edit failed' in caplog.text
        assert 'HITL expiry notification failed' in caplog.text
        assert 'qa-bot' not in caplog.text
