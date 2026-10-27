"""Build the unmodified production entry point with all provider imports offline.

Run with the project's installed requirements. This is a production-module and
Gradio routing check, not a browser or a paid provider end-to-end test.
"""
import os
from pathlib import Path
import runpy
import socket
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0,str(ROOT))
os.environ['OPENAI_API_KEY']=''
os.environ['GRADIO_ANALYTICS_ENABLED']='False'
os.environ['HF_HUB_OFFLINE']='1'
os.environ['MPLCONFIGDIR']=tempfile.mkdtemp(prefix='chuanhu-smoke-mpl-')

def no_network(*args,**kwargs):
    raise AssertionError('The production build smoke test forbids network connections')

socket.socket.connect=no_network
scope=runpy.run_path(str(ROOT/'ChuanhuChatbot.py'),run_name='chuanhu_production_smoke')
config=scope['demo'].get_config_file()
assert any(component.get('props',{}).get('elem_id')=='agent-model-options' for component in config['components'])
assert any(component.get('props',{}).get('elem_id')=='model-output-files' for component in config['components'])
assert any(component.get('props',{}).get('elem_id')=='model-capability-state' for component in config['components'])
ids={component['id']:component.get('props',{}).get('elem_id') for component in config['components']}
def component_path(node, wanted, parents=()):
    here=parents+(ids.get(node['id']),)
    if ids.get(node['id'])==wanted:return here
    return next((path for child in node.get('children',[]) if (path:=component_path(child,wanted,here))),None)
selection_path=component_path(config['layout'],'agent-model-options')
assert 'chuanhu-toolbox' in selection_path and 'chatbot-footer' not in selection_path
assert not any(component.get('props',{}).get('value')=='应用到下一轮' for component in config['components'])
print(f"Production imports and Gradio layout built: {len(config['components'])} components, {len(scope['demo'].fns)} callbacks; no credentials or network")
scope['demo'].close()
