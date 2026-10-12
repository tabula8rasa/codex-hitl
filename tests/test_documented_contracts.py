"""Keep the documented internal wire examples aligned with actual models."""
import json
import re
import tomllib
from pathlib import Path

from codex_hitl.contracts import AnswerRequest, Message
from codex_hitl.mcp_server.lifecycle import DELIVERY_BUDGET_SECONDS, EXPIRY_BUDGET_SECONDS, RESPONSE_WAIT_SECONDS


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


def test_documented_client_budget_allows_delivery_and_response_wait():
    documentation = Path('README.md').read_text()
    examples = [tomllib.loads(block) for block in re.findall(
        r'```toml\n(.*?)\n```', documentation, re.S)]
    hitl = next(example['mcp_servers']['hitl'] for example in examples
                if 'hitl' in example.get('mcp_servers', {}))
    assert hitl['tool_timeout_sec'] == 900
    assert RESPONSE_WAIT_SECONDS + DELIVERY_BUDGET_SECONDS + EXPIRY_BUDGET_SECONDS < hitl['tool_timeout_sec']
    cli_instructions = next(line for line in documentation.splitlines()
                            if line.startswith('Alternatively, `codex mcp add hitl'))
    assert '`tool_timeout_sec = 900`' in cli_instructions
