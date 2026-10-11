from uuid import uuid4

import pytest
from pydantic import ValidationError

from codex_hitl.contracts import AnswerRequest, Message, Request, answer_matches


@pytest.mark.parametrize('kind', ['approval', 'question', 'manual_action'])
def test_request_types(kind):
    payload = dict(type=kind, title='', description='')
    assert Request.model_validate(payload).model_dump() == payload
    assert Message.model_validate(dict(payload, request_id=str(uuid4()))).type == kind


@pytest.mark.parametrize('status,kind', [('approved','approval'), ('rejected','approval'), ('answered','question'), ('completed','manual_action'), ('unable','manual_action')])
def test_answer_shapes_and_compatibility(status, kind):
    answer = dict(status=status)
    if status == 'answered':
        answer['answer'] = 'human answer'
    parsed = AnswerRequest.model_validate(dict(request_id=str(uuid4()), answer=answer))
    assert parsed.answer.model_dump() == answer
    for other in ['approval', 'question', 'manual_action']:
        assert answer_matches(other, parsed.answer) == (other == kind)


@pytest.mark.parametrize('patch', [dict(type='other'), dict(title=3), dict(description=False), dict(extra='x')])
def test_invalid_public_fields(patch):
    with pytest.raises(ValidationError):
        Request.model_validate(dict(type='approval', title='a', description='b') | patch)


@pytest.mark.parametrize('missing', ['type', 'title', 'description'])
def test_missing_public_fields(missing):
    payload = dict(type='approval', title='a', description='b')
    del payload[missing]
    with pytest.raises(ValidationError):
        Request.model_validate(payload)


@pytest.mark.parametrize('answer', [{}, {'status':'timeout'}, {'status':'answered'}, {'status':'answered','answer':1}, {'status':'approved','answer':'no'}, {'status':'approved','extra':True}])
def test_invalid_answers(answer):
    with pytest.raises(ValidationError):
        AnswerRequest.model_validate(dict(request_id=str(uuid4()), answer=answer))


@pytest.mark.parametrize('request_id', ['bogus', '00000000-0000-0000-0000-000000000000', str(uuid4()).upper(), 42])
def test_invalid_ids(request_id):
    with pytest.raises(ValidationError):
        AnswerRequest.model_validate(dict(request_id=request_id, answer={'status':'approved'}))


@pytest.mark.parametrize('model,payload', [
    (Request, {'type':'question','title':'t','description':'d'}),
    (Message, {'request_id':str(uuid4()),'type':'question','title':'t','description':'d'}),
    (AnswerRequest, {'request_id':str(uuid4()),'answer':{'status':'answered','answer':'text'}}),
])
def test_all_boundary_models_reject_extra_and_missing_fields(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload | {'extra':'forbidden'})
    for key in payload:
        with pytest.raises(ValidationError):
            model.model_validate({name:value for name,value in payload.items() if name != key})
