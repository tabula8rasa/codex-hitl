"""Keep the documented internal wire examples aligned with actual models."""
import json
import re
from pathlib import Path

from codex_hitl.contracts import AnswerRequest, Message


def test_documented_wire_examples_validate():
    documentation = Path('docs/MCP_SERVER.md').read_text()
    examples = [json.loads(block) for block in re.findall(r'```json\n(.*?)\n```', documentation, re.S)]
    message = next(example for example in examples if 'type' in example)
    answer = next(example for example in examples if 'answer' in example)
    parsed_message = Message.model_validate(message)
    parsed_answer = AnswerRequest.model_validate(answer)
    assert parsed_message.request_id == parsed_answer.request_id
    assert parsed_message.type == 'approval'
    assert parsed_answer.answer.status == 'approved'
