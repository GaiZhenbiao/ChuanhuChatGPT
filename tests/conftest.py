"""Use real Gradio; isolate app configuration/model imports to avoid API calls."""
import sys
import os
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
for name in ('ALL_PROXY', 'all_proxy', 'HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy'):
    os.environ.pop(name, None)
os.environ['GRADIO_ANALYTICS_ENABLED'] = 'False'
os.environ['MPLCONFIGDIR'] = '/tmp/chuanhu-test-matplotlib'
sys.path.insert(0, str(ROOT))
shared = ModuleType('modules.shared')
shared.chuanhu_path = str(ROOT)
sys.modules['modules.shared'] = shared
presets = ModuleType('modules.presets')
import json
def flatten(tree,prefix=''):
    result={}
    for key,value in tree.items():
        dotted=f'{prefix}.{key}' if prefix else key
        if isinstance(value,dict): result.update(flatten(value,dotted))
        else: result[dotted]=value
    return result
locale=flatten(json.loads((ROOT/'locale/zh_CN.json').read_text()))
presets.i18n = lambda key: locale.get(key,key)
sys.modules['modules.presets'] = presets
