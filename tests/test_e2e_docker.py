"""Opt-in isolated Docker network E2E using the built production images."""
import asyncio
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from test_integration_services import TelegramDouble

pytestmark = pytest.mark.skipif(os.environ.get('RUN_DOCKER_E2E') != '1', reason='Set RUN_DOCKER_E2E=1 with built Docker images')


def docker(*args):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def port(name, container_port):
    return 'http://' + docker('port', name, str(container_port)).splitlines()[0]


async def wait_ready(client, url):
    async with asyncio.timeout(20):
        while True:
            try:
                response = await client.get(url)
                if response.status_code < 500:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(.1)


async def test_built_containers_sdk_telegram_polling_and_auth():
    prefix = 'hitl-qa-' + uuid4().hex[:10]
    network = prefix + '-network'
    names = []
    support = str(Path(__file__).parent.joinpath('support').resolve())
    environment = ['-e','INTERNAL_API_TOKEN=qa-internal']
    try:
        docker('network', 'create', network)
        def run(role, alias, image, extra, command=()):
            name = prefix + '-' + role
            names.append(name)
            return docker('run', '-d', '--name', name, '--network', network, '--network-alias', alias,
                          *environment, *extra, image, *command)
        run('double', 'telegram-double', 'codex-hitl-bot:latest', ['-p','127.0.0.1::9000','-v',support+':/qa:ro'],
            ['uvicorn','telegram_double:app','--app-dir','/qa','--host','0.0.0.0','--port','9000'])
        run('mcp', 'mcp', 'codex-hitl-mcp:latest', ['-p','127.0.0.1::8100','-e','BOT_API_URL=http://bot:8101', '-v',support+':/qa:ro'],
            ['uvicorn','mcp_entrypoint:factory','--factory','--app-dir','/qa','--host','0.0.0.0','--port','8100','--workers','1'])
        async with httpx.AsyncClient(timeout=10) as client:
            double_url = port(prefix+'-double', 9000)
            mcp_url = port(prefix+'-mcp', 8100)
            await wait_ready(client, double_url+'/messages')
            run('bot', 'bot', 'codex-hitl-bot:latest', ['-p','127.0.0.1::8101','-v',support+':/qa:ro',
                '-e','TELEGRAM_BOT_TOKEN=qa-bot','-e','TELEGRAM_CHAT_ID=42','-e','TELEGRAM_ALLOWED_USER_ID=99','-e','HITL_API_URL=http://mcp:8100'],
                ['uvicorn','bot_entrypoint:factory','--factory','--app-dir','/qa','--host','0.0.0.0','--port','8101','--workers','1'])
            bot_url = port(prefix+'-bot', 8101)
            await wait_ready(client, bot_url+'/openapi.json')
            await wait_ready(client, mcp_url+'/openapi.json')
            assert (await client.post(bot_url+'/internal/messages', json={})).status_code == 401
            assert (await client.post(bot_url+'/internal/expire', json={})).status_code == 401
            assert (await client.post(mcp_url+'/internal/answer', json={})).status_code == 401
            assert (await client.post(mcp_url+'/qa/expire')).status_code == 401
            attack = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                      'params': {'name': 'hitl.request', 'arguments': {'type': 'approval', 'title': 'attack', 'description': 'attack'}}}
            for headers, expected in (
                ({'Host': 'attacker.invalid:8100'}, 421),
                ({'Origin': 'http://attacker.invalid:8100'}, 403),
                ({'Origin': 'http://127.0.0.1.attacker.invalid:8100'}, 403),
            ):
                response = await client.post(mcp_url+'/mcp', json=attack,
                    headers={'Accept': 'application/json, text/event-stream', **headers})
                assert response.status_code == expected
            assert (await client.get(double_url+'/messages')).json() == []
            async with streamable_http_client(mcp_url+'/mcp') as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert [t.name for t in tools.tools] == ['hitl.request']
                    cases = [('approval','approved'),('approval','rejected'),('question','answered'),('manual_action','completed'),('manual_action','unable')]
                    tasks = [asyncio.create_task(session.call_tool('hitl.request', {'type': kind,'title': status,'description':'Container E2E'})) for kind, status in cases]
                    async with asyncio.timeout(10):
                        while True:
                            messages = (await client.get(double_url+'/messages')).json()
                            if len(messages) == 5:
                                break
                            await asyncio.sleep(.05)
                    helper = TelegramDouble()
                    for message in reversed(messages):
                        status = message['text'].split('\n\n')[1]
                        assert (await client.post(double_url+'/updates', json=helper.update(message, status))).status_code == 200
                    results = await asyncio.wait_for(asyncio.gather(*tasks), 10)
                    for (_, status), result in zip(cases, results):
                        assert not result.isError
                        assert result.structuredContent == {'status': status, **({'answer':'QA text'} if status == 'answered' else {})}
                    # Repeated old message is rejected across the real bot->MCP HTTP path.
                    await client.post(double_url+'/updates', json=helper.update(messages[0], messages[0]['text'].split('\n\n')[1]))
                    async with asyncio.timeout(5):
                        while True:
                            calls = (await client.get(double_url+'/calls')).json()
                            if any(c['method']=='sendMessage' and 'no longer active' in c['payload']['text'] for c in calls):
                                break
                            await asyncio.sleep(.05)
                    assert sum(c['method']=='editMessageReplyMarkup' for c in calls) == 4
                    # Only the mounted QA adapter controls timing; production
                    # still supplies its fixed 850-second wait to that adapter.
                    from codex_hitl.telegram_bot.service import EXPIRY_NOTICE
                    sends_before_expiry = sum(c['method'] == 'sendMessage' for c in calls)
                    kinds = ['approval', 'manual_action', 'question']
                    expiry_tasks = [asyncio.create_task(session.call_tool('hitl.request',
                        {'type': kind, 'title': 'Expire '+kind, 'description': 'Container expiry'})) for kind in kinds]
                    async with asyncio.timeout(10):
                        while True:
                            expired_messages = [m for m in (await client.get(double_url+'/messages')).json()
                                                if '\n\nExpire ' in m['text']]
                            if len(expired_messages) == 3:
                                break
                            await asyncio.sleep(.05)
                    originals = {m['message_id']: m['text'] for m in expired_messages}
                    response = await client.post(mcp_url+'/qa/expire', headers={'Authorization': 'Bearer qa-internal'})
                    assert response.status_code == 200
                    expiry_results = await asyncio.wait_for(asyncio.gather(*expiry_tasks), 10)
                    assert all(not r.isError and r.structuredContent == {'status': 'timeout', 'error_code': 'HITL_TIMEOUT'}
                               for r in expiry_results)
                    edited = [m for m in (await client.get(double_url+'/messages')).json() if m['message_id'] in originals]
                    assert len(edited) == 3
                    for message in edited:
                        assert message['text'] == originals[message['message_id']] + '\n\n' + EXPIRY_NOTICE
                        assert message['reply_markup'] == {'inline_keyboard': []}
                        payload = {'request_id': message['text'].split()[1],
                                   'answer': {'status': 'answered', 'answer': 'late'} if ' question\n' in message['text']
                                   else {'status': 'completed'} if ' manual_action\n' in message['text'] else {'status': 'approved'}}
                        response = await client.post(mcp_url+'/internal/answer', json=payload,
                                                     headers={'Authorization': 'Bearer qa-internal'})
                        assert response.json() == {'accepted': False}
                    calls = (await client.get(double_url+'/calls')).json()
                    assert sum(c['method']=='editMessageText' for c in calls) == 3
                    assert sum(c['method']=='sendMessage' for c in calls) == sends_before_expiry + 3
            for name in names:
                assert docker('inspect','-f','{{.State.Running}}',name) == 'true'
                assert docker('inspect','-f','{{.Config.User}}',name) == 'hitl'
    finally:
        for name in reversed(names):
            subprocess.run(['docker','rm','-f',name], capture_output=True)
        subprocess.run(['docker','network','rm',network], capture_output=True)
