"""Exercise the actual custom model-list branch without private configuration."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('custom', [
    ['GPT4', 'OpenAI Agent', '川虎助理', '川虎助理 Pro'],
    ['川虎助理 Pro', 'GPT4', 'OpenAI Agent', '川虎助理'],
    ['川虎助理', 'OpenAI Agent', 'GPT4'],
])
def test_custom_available_models_preserve_exact_user_order(custom):
    tree = ast.parse((ROOT / 'modules/config.py').read_text())
    branch = next(n for n in tree.body if isinstance(n, ast.If) and ast.unparse(n.test) == "'available_models' in config")
    presets = SimpleNamespace(MODELS=['default'])
    scope = dict(config={'available_models': custom}, presets=presets,
                 logging=SimpleNamespace(info=lambda value: None), i18n=lambda key: '{available_models}')
    exec(compile(ast.Module(body=[branch], type_ignores=[]), 'modules/config.py', 'exec'), scope)
    assert presets.MODELS == custom
    assert presets.MODELS is not custom


def test_default_online_order_places_agent_before_assistants():
    tree = ast.parse((ROOT / 'modules/presets.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'ONLINE_MODELS' for t in n.targets))
    names = ast.literal_eval(node.value)
    assert names.index('OpenAI Agent') < names.index('川虎助理') < names.index('川虎助理 Pro')
