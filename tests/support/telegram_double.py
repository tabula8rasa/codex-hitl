"""Network Telegram API double used only by container QA."""
import asyncio
from fastapi import FastAPI

app = FastAPI()
messages = []
calls = []
updates = asyncio.Queue()

@app.post('/bot{token}/{method}')
async def telegram(token: str, method: str, payload: dict):
    calls.append({'method': method, 'payload': payload})
    if method == 'getMe':
        result = {'id': 777, 'is_bot': True}
    elif method == 'getUpdates':
        try:
            result = [await asyncio.wait_for(updates.get(), .2)]
        except TimeoutError:
            result = []
    elif method == 'sendMessage':
        result = {'message_id': len(messages) + 1, 'from': {'id': 777, 'is_bot': True},
                  'chat': {'id': 42}, **payload}
        messages.append(result)
    elif method == 'editMessageText':
        result = next(m for m in messages if m['message_id'] == payload['message_id'])
        assert result['chat']['id'] == payload['chat_id']
        result.update(text=payload['text'], reply_markup=payload['reply_markup'])
    else:
        result = True
    return {'ok': True, 'result': result}

@app.get('/messages')
async def get_messages():
    return messages

@app.get('/calls')
async def get_calls():
    return calls

@app.post('/updates')
async def put_update(payload: dict):
    await updates.put(payload)
    return {'queued': True}
