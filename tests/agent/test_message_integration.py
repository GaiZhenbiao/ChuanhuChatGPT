import asyncio
from copy import deepcopy
import json
from pathlib import Path
import re
import gradio as gr
from gradio.state_holder import SessionState
from modules.agent.ui import AgentPanel, ArtifactPanel, message_file_projection
from modules.agent.message_files import decode_rows
from modules.model_capabilities import CapabilityUI
from main_chat_mock import MainChatMock
from agent_fixtures import env,select,request


def test_real_rendered_roundtrip_keeps_files_with_their_turn_after_restore(env,monkeypatch):
    model=select(env);service=MainChatMock();monkeypatch.setattr(env.agents,'worker_messages',service.worker)
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();text=gr.Textbox();chat=gr.Chatbot();status=gr.Markdown();button=gr.Button();selector=gr.Dropdown();marker=gr.HTML()
        caps=CapabilityUI([],selector,marker);caps.wire(current,chat)
        panel=AgentPanel(env.wrappers['convert_user_before_marked'],env.wrappers['convert_bot_before_marked'])
        panel.selectors();panel.settings_components();panel.output_components()
        button.click(panel.wrap_predict(env.wrappers['predict'],caps),[current,text,chat],[chat,status,*panel.outputs,*caps.outputs])
    state=SessionState(app);state[current._id]=model
    index=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='predict_with_ui')
    async def send_view(prompt,visible):
        result=await app.process_api(index,[None,prompt,visible],state=state,request=request())
        while True:
            chat_frame=result['data'][0]
            if isinstance(chat_frame,list): visible=chat_frame
            elif isinstance(chat_frame,dict) and 'value' in chat_frame: visible=chat_frame['value']
            if not result['is_generating']: break
            result=await app.process_api(index,[None,prompt,visible],state=state,request=request(),iterator=result['iterator'])
        assert decode_rows(visible,model._conversation_id)==model.chatbot
        assert all('agent-message' not in item['content'] for item in model.history)
        return visible
    async def exercise():
        first=await send_view('files',[])
        original=message_file_projection(model).artifact_anchors.copy()
        assert len(original)==3 and len(set(original.values()))==1
        second=await send_view('another files',first)
        combined=message_file_projection(model).artifact_anchors
        assert all(combined[identifier]==key for identifier,key in original.items())
        assert len(set(combined.values()))==2
        third=await send_view('files-only',second)
        assert model.chatbot[-1][1] is None
        assert len(set(message_file_projection(model).artifact_anchors.values()))==3
        assert 'agent-message-anchor' in third[-1][1]
        markup=ArtifactPanel.values(model)[1]['value']
        assert '可下载' not in markup
        assert {m for m in re.findall(r'data-message-key="([^"]+)"',markup)}==set(message_file_projection(model).artifact_anchors.values())
        await send_view('followup after files only',third)
        saved=json.loads((env.history_dir/model.history_file_path).read_text())
        assert saved['chatbot']==model.chatbot and 'data-agent-message' not in json.dumps(saved)
        original_ids=message_file_projection(model).artifact_anchors
        restored=select(env,browser='restored');restored.load_chat_history(model.history_file_path)
        assert message_file_projection(restored).artifact_anchors==original_ids
        ordinary=select(env,model,name='GPT3.5 Turbo')
        assert ordinary.chatbot==model.chatbot and 'agent-message-anchor' not in json.dumps(ordinary.history)
    try:asyncio.run(exercise())
    finally:app.close()


def test_agent_export_of_adopted_image_history_does_not_drop_user_turn_on_reload(env, tmp_path):
    ordinary = select(env, name='GPT3.5 Turbo')
    image_messages = []
    for i in range(3):
        path = tmp_path / ('photo' + str(i) + '.png')
        path.write_bytes(b'synthetic image')
        image_messages.append({'role': 'image', 'content': str(path)})
    ordinary.history = image_messages + [
        {'role': 'user', 'content': 'Compare these three images'},
        {'role': 'assistant', 'content': 'They differ'},
    ]
    ordinary.auto_save([])
    ordinary.load_chat_history(ordinary.history_file_path)
    agent = select(env, ordinary)
    agent.export_markdown('exported', agent.chatbot)
    exported = json.loads((env.history_dir / 'exported.json').read_text())
    assert exported['history'] == [item for item in ordinary.history if item['role'] != 'image']
    assert [file['name'] for file in exported['agent_transcript']['files']] == ['photo0.png', 'photo1.png', 'photo2.png']
    assert all(message['content'] not in json.dumps(exported) for message in image_messages)
    restored = select(env, browser='restored')
    restored.load_chat_history('exported')
    assert restored.history == [
        {'role': 'user', 'content': 'Compare these three images'},
        {'role': 'assistant', 'content': 'They differ'},
    ]
