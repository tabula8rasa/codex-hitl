from pathlib import Path
import yaml


def test_two_services_and_internal_connectivity():
    config = yaml.safe_load(Path('compose.yaml').read_text())
    assert set(config['services']) == {'mcp', 'bot'}
    mcp = config['services']['mcp']
    bot = config['services']['bot']
    assert mcp['environment']['BOT_API_URL'] == 'http://bot:8101'
    assert bot['environment']['HITL_API_URL'] == 'http://mcp:8100'
    assert mcp['environment']['INTERNAL_API_TOKEN'] == bot['environment']['INTERNAL_API_TOKEN']
    assert mcp['ports'] == ['127.0.0.1:8100:8100']
    assert 'ports' not in bot
    assert mcp['build']['target'] == 'mcp'
    assert bot['build']['target'] == 'bot'
    dockerfile = Path('Dockerfile').read_text()
    assert dockerfile.count('"--workers", "1"') == 2
    assert 'USER hitl' in dockerfile


def test_secret_template_and_required_variables():
    template = Path('.env.example').read_text()
    services = yaml.safe_load(Path('compose.yaml').read_text())['services']
    for name in ['INTERNAL_API_TOKEN', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'TELEGRAM_ALLOWED_USER_ID']:
        assert f'{name}=\n' in template
        assert services['bot']['environment'][name].startswith('${' + name + ':?')
