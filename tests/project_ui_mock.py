"""Render the actual ChuanhuChatbot.py layout/theme/assets with synthetic data.

This does NOT import provider/config/train modules or read config/.env files.
It executes the unmodified component layout AST from the real entry file,
then binds real plugins and synthetic chat/Agent handlers. Core history,
training, model billing and update/reboot actions are intentionally unwired.
"""
import argparse
import ast
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import time

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0,str(ROOT))
for name in ('ALL_PROXY','all_proxy','HTTP_PROXY','http_proxy','HTTPS_PROXY','https_proxy'):
    os.environ.pop(name,None)
os.environ['GRADIO_ANALYTICS_ENABLED']='False'
os.environ['MPLCONFIGDIR']=tempfile.mkdtemp(prefix='chuanhu-mpl-')
import gradio as gr


def build(language='zh_CN'):
    # Only the locale initializer is replaced so it never reads config.json;
    # locale JSON and theme constants are the real project implementation.
    import json
    class OfflineLocale:
        def __init__(self):
            self.language=language
            self.mapping=self.flatten(json.loads((ROOT/'locale'/(language+'.json')).read_text()))
            self.fallback=self.flatten(json.loads((ROOT/'locale/en_US.json').read_text()))
        @staticmethod
        def flatten(tree, prefix=''):
            result={}
            for key,value in tree.items():
                dotted=f'{prefix}.{key}' if prefix else key
                if isinstance(value,dict): result.update(OfflineLocale.flatten(value,dotted))
                else: result[dotted]=value
            return result
        def __call__(self,key):
            return self.mapping.get(key,self.fallback.get(key,key))
    locale_module=ModuleType('modules.webui_locale');locale_module.I18nAuto=OfflineLocale
    sys.modules['modules.webui_locale']=locale_module
    import modules.presets as presets
    shared=ModuleType('modules.shared');shared.chuanhu_path=str(ROOT);shared.assets_path=str(ROOT/'web_assets');shared.API_HOST='api.openai.com'
    sys.modules['modules.shared']=shared
    from modules import extensions,plugin_callbacks,webui
    from modules.plugin_context import AppContext
    temporary=Path(tempfile.mkdtemp(prefix='chuanhu-project-ui-'))
    extensions.STATE_FILE=temporary/'extension_state.json'
    extensions.STATE_FILE.write_text('{"version":1,"enabled":{"openai_agents":true}}')
    loaded=extensions.load_extensions(force=True)
    if any(item.error for item in loaded): raise RuntimeError('Plugin failed during mock layout construction')
    entry=next(item for item in loaded if item.id=='openai_agents')
    agents=next(sys.modules[name] for name in entry.module_names if name.endswith('.scripts.main'))
    agents.JOURNAL_DIR=temporary/'journals'
    from fake_agent import FakeAgentBackend
    backend=FakeAgentBackend(temporary);agents.worker_messages=backend.messages
    source=ast.parse((ROOT/'ChuanhuChatbot.py').read_text())
    block=next(node for node in source.body if isinstance(node,ast.With))
    layout=[]
    for node in block.body:
        if isinstance(node,ast.FunctionDef): break
        layout.append(node)
    tree=ast.fix_missing_locations(ast.Module(body=layout,type_ignores=[]))
    namespace={name:getattr(presets,name) for name in dir(presets) if not name.startswith('__')}
    namespace.update(gr=gr,extensions=extensions,shared=shared,
        config=SimpleNamespace(user_avatar=str(ROOT/'web_assets/icon/user.png') if (ROOT/'web_assets/icon/user.png').exists() else None,bot_avatar=None,http_proxy='',api_host='api.openai.com'),
        my_api_key='',HIDE_MY_KEY=True,multi_api_key=False,check_update=False,show_api_billing=False,
        hide_history_when_not_logged_in=False,advance_docs={'pdf':{}},chat_name_method_index=0,latex_delimiters_set=[],
        get_html=webui.get_html,get_history_names=lambda:[],get_first_history_name=lambda:None,
        get_template_names=lambda:['Offline examples'],load_template=lambda *a,**k:[],hide_middle_chars=lambda value:'',
        repo_tag_html=lambda:'Offline mock',version_time=lambda:'2026-10-01',versions_html=lambda:'Synthetic providers; no API requests',
        setPlaceholder=lambda **kw:'Offline preview: chat and Agent responses are synthetic.',
        get_geoip=lambda:'离线界面验收：所有 Agent / 模型事件均为模拟，不读取任何密钥。')
    # Apply the real project's component class wrapper without importing its
    # provider-dependent modules or altering multipart handling.
    overwrite_source=ast.parse((ROOT/'modules/overwrites.py').read_text())
    wrapper=next(node for node in overwrite_source.body if isinstance(node,ast.FunctionDef) and node.name=='init_with_class_name_as_elem_classes')
    scope={};exec(compile(ast.Module(body=[wrapper],type_ignores=[]),str(ROOT/'modules/overwrites.py'),'exec'),scope)
    gr.components.Component.__init__=scope[wrapper.name](gr.components.Component.__init__)
    gr.blocks.BlockContext.__init__=scope[wrapper.name](gr.blocks.BlockContext.__init__)
    with gr.Blocks(theme=presets.small_and_beautiful_theme,analytics_enabled=False,title='ChuanhuChat — OFFLINE MOCK') as demo:
        exec(compile(tree,str(ROOT/'ChuanhuChatbot.py'),'exec'),namespace)
        demo.load(lambda:SimpleNamespace(),outputs=namespace['current_model'])
        def chat(text,history,model):
            history=list(history or [])+[[text,'Offline synthetic response: '+text]]
            # Existing lifecycle hooks participate in this synthetic turn.
            from modules.plugin_context import ChatContext
            context=ChatContext(model,text,history,assistant_reply=history[-1][1])
            plugin_callbacks.invoke('after_chat',context)
            return history,'Offline mock response; no API called.'
        namespace['submitBtn'].click(chat,inputs=[namespace['user_input'],namespace['chatbot'],namespace['current_model']],outputs=[namespace['chatbot'],namespace['status_display']],api_name='offline_chat')
        plugin_callbacks.invoke('app_ready',AppContext(namespace['chatbot'],namespace['current_model'],namespace['user_input']))
    webui.reload_javascript()
    if plugin_callbacks.get_errors(): raise RuntimeError('Plugin UI error in project layout')
    return demo


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8773);parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--language',choices=['zh_CN','en_US'],default='zh_CN');parser.add_argument('--build-only',action='store_true');args=parser.parse_args()
    demo=build(args.language)
    if args.build_only:
        config=demo.get_config_file()
        labels=[component.get('props',{}).get(key,'') for component in config['components'] for key in ('label','placeholder')]
        unresolved=[label for label in labels if isinstance(label,str) and label.startswith(('ui.','msg.','app.'))]
        if unresolved: raise RuntimeError('Unresolved project locale labels: '+str(unresolved))
        print('Actual project component layout built:',len(config['components']),'components. All project locale labels resolved. No providers or credentials loaded.')
        demo.close();return
    demo.queue().launch(server_name=args.host,server_port=args.port,share=False,prevent_thread_lock=True,
       allowed_paths=[str(ROOT/'web_assets'),str(ROOT/'extensions')],
       blocked_paths=[str(ROOT/'config.json'),str(ROOT/'.env.agents'),str(ROOT/'plugin_data'),str(ROOT/'extension_state.json'),str(ROOT/'.agents-runtime')])
    print('OFFLINE MOCK: actual project layout, synthetic providers. No API requests.',flush=True)
    try:
        while True: time.sleep(1)
    finally: demo.close()

if __name__=='__main__':main()
