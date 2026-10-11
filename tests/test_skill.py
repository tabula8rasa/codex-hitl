from pathlib import Path
import yaml


def test_skill_contract():
    text = Path('skills/hitl/SKILL.md').read_text()
    _, frontmatter, body = text.split('---', 2)
    metadata = yaml.safe_load(frontmatter)
    assert metadata['name'] == 'hitl'
    assert metadata['description']
    # Artifact checks only; scenario review is recorded in docs/VERIFICATION.md.
    for required in ['hitl.request', 'exactly three fields', 'approval', 'question', 'manual_action', 'independently', 'rejection', 'unconfirmed manual action', 'HITL_TIMEOUT', 'unavailable', 'parent agent', 'no parent agent', 'Do not automatically retry']:
        assert required in body
