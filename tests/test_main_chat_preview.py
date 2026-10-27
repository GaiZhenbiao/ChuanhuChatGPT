"""Exercise the actual main-page preview's wired history callbacks offline."""
from pathlib import Path
import json
import subprocess
import sys


def test_preview_send_title_reset_and_history_callbacks():
    result = subprocess.run([sys.executable, __file__, '--exercise'],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


async def exercise():
    import gradio as gr
    from gradio.state_holder import SessionState
    from main_chat_preview import build
    app = build()
    import inspect
    config=app.get_config_file()
    generators={i:fn.fn.__name__ for i,fn in enumerate(app.fns) if fn.fn and inspect.isgeneratorfunction(fn.fn)}
    for index,name in generators.items():
        assert config['dependencies'][index]['queue'] is not False, (index,name)
    for name in ('upload_files','remove_files','login','observe_history'):
        matches=[i for i,n in generators.items() if n==name]
        assert matches and all(config['dependencies'][i]['queue'] is True for i in matches)
        assert all(app.fns[i].concurrency_limit is None for i in matches)
    stop=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='interrupt')
    assert not inspect.isgeneratorfunction(app.fns[stop].fn) and config['dependencies'][stop]['queue'] is False
    follow_index,follow=next((i,dep) for i,dep in enumerate(config['dependencies']) if dep['trigger_after']==stop)
    assert follow['queue'] is False and app.fns[follow_index].fn.__name__=='emit_stop_error'
    from modules.presets import i18n
    state = SessionState(app)
    functions = {fn.fn.__name__: i for i, fn in enumerate(app.fns) if fn.fn}
    request = gr.Request(session_hash='preview-history')
    chat_frames = []

    async def call(name, inputs, expected_error=None):
        nonlocal model
        index = functions[name]
        if 'current_id' in locals(): model = state[current_id]
        if name=='transfer_input' and len(inputs)==2:
            current=state[app.fns[functions['initial']].outputs[0]._id]
            choice=getattr(current,'agent_model_choice',('gpt-6-astra',None))
            file_values=[{'path':path,'orig_name':Path(path).name,'meta':{'_type':'gradio.FileData'}} for path in getattr(current,'_pending_upload_paths',())]
            inputs=[*inputs,choice[0],choice[1] or 'default',getattr(current,'_choice_revision',0),file_values]
            if getattr(current,'is_hosted_agent',False):
                tools=current._current_settings()['tools']
                inputs.extend([tools['network'],tools['code_execution'],tools['web_search'],tools['search_mode'],'\n'.join(tools['search_domains']),
                    tools['computer_use'],tools['include_screenshots'],tools['tool_search'],tools['programmatic_tool_calling'],tools['functions'],
                    json.dumps(tools['mcp_servers']),current.system_prompt,current._conversation_id,current._tool_revision])
            else: inputs.extend(component.value for component in app.fns[index].inputs[6:])
        if name=='predict_with_ui' and len(inputs)==6: inputs=[*inputs,[]]
        result = await app.process_api(index, inputs, state=state, request=request)
        while True:
            current = state[app.fns[functions['initial']].outputs[0]._id]
            if getattr(current, 'is_hosted_agent', False):
                for component, value in zip(app.fns[index].outputs, result['data']):
                    if getattr(component, 'elem_id', None) == 'status-display':
                        assert value in ('', None) or value == {'__type__': 'update'}, (name, value)
            assert len({component._id for component in app.fns[index].outputs}) == len(app.fns[index].outputs)
            if name == 'predict_with_ui':
                frame = result['data'][0]
                if isinstance(frame, list) or (isinstance(frame, dict) and 'value' in frame):
                    chat_frames.append(frame)
            if not result['is_generating']: break
            result = await app.process_api(index, inputs, state=state, request=request,
                                           iterator=result['iterator'])
        model = state[app.fns[functions['initial']].outputs[0]._id]
        if name in ('predict_with_ui','observe_history','upload_files','remove_files','login','retry_file'):
            try:
                await app.process_api(functions['emit_ui_error'],[None],state=state,request=request)
            except gr.Error as error:
                assert expected_error and expected_error in str(error), str(error)
                assert not current._running and not getattr(current,'_pending_send',None)
        return result['data']

    try:
        await call('initial', [])
        current_id = app.fns[functions['initial']].outputs[0]._id
        model = state[current_id]
        # Ordinary automatic titles previously failed on a missing real helper.
        await call('transfer_input', ['Ordinary: title!', None])
        await call('predict_with_ui', [None, None, [], False, [], 'English'])
        ordinary_chat = chat_frames[-1]
        if isinstance(ordinary_chat, dict): ordinary_chat = ordinary_chat['value']
        assert 'class="raw-message hideM"' in ordinary_chat[0][1]
        assert 'class="md-message"' in ordinary_chat[0][1]
        assert 'Ordinary synthetic response' in ordinary_chat[0][1]
        title = await call('auto_name_chat_history', [None, i18n('naming.by_first_question'), None, False])
        saved = model.history_file_path
        assert saved == 'Ordinary  title.json'
        assert any(choice[0] == 'Ordinary  title' for choice in title[0]['choices'])
        reset = await call('reset', [None, False])
        chat_index = next(i for i, component in enumerate(app.fns[functions["reset"]].outputs) if isinstance(component, gr.Chatbot))
        assert reset[chat_index] == [] and model.history == []
        restored = await call('load_history_model', [None, saved[:-5]])
        assert model.chatbot[0][0] == 'Ordinary: title!'
        assert 'class="user-message"' in restored[4]['value'][0][0]
        assert 'class="raw-message hideM"' in restored[4]['value'][0][1]

        await call('change_model', ['OpenAI Agent', None, '', 1, 1, 'QA', '', None])
        model = state[current_id]
        index = functions['observe_history']
        inactive = await app.process_api(index, [None], state=state, request=request, session_hash='inactive-observer', event_id='inactive-observer')
        assert inactive['is_generating'] and all(value == gr.update() for value in inactive['data'])
        inactive = await app.process_api(index, [None], state=state, request=request, iterator=inactive['iterator'], session_hash='inactive-observer', event_id='inactive-observer')
        assert not inactive['is_generating'] and all(value == gr.update() for value in inactive['data'])
        await call('reset', [None, False])
        await call('transfer_input', ['files', None])
        await call('predict_with_ui', [None, None, model.chatbot, False, [], 'English'], expected_error='模拟单文件下载失败')
        await call('auto_name_chat_history', [None, i18n('naming.by_first_question'), None, False])
        saved = model.history_file_path
        session = model._state['session_id']
        assert len(model._artifacts) == 3
        await call('reset', [None, False])
        assert not model._state.get('session_id') and not model._artifacts
        await call('load_history_model', [None, saved.removesuffix('.json')])
        assert model._state['session_id'] == session
        assert model._needs_sync
        boundary=app.fns[functions['values_at_boundary']]
        choices=[component for component in boundary.outputs if isinstance(component,gr.Dropdown) and component.value in ('gpt-6.1-sol','default')]
        assert len(choices)==2
        await call('values_at_boundary',[None])
        assert all(state.blocks_config.blocks[component._id].interactive is False for component in choices)
        await call('observe_history', [None])
        assert not model._needs_sync
        await call('history_values_at_boundary',[None])
        assert all(state.blocks_config.blocks[component._id].interactive is True for component in choices)
        assert model.agent_model_choice[0]=='gpt-6.1-sol'
        # 三个真实历史进入链都仅在同步结束后更新一次完整控制边界。
        for observer_index in [i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='observe_history']:
            follow=next(i for i,dep in enumerate(config['dependencies']) if dep['trigger_after']==observer_index)
            assert app.fns[follow].fn.__name__=='history_values_at_boundary'
            assert config['dependencies'][follow]['show_progress']=='hidden'
        assert len(model._artifacts) == 3
        assert model.chatbot[-1][0] == 'files'
        # The browser's actual new-settings flow must reconcile the provisional
        # local row with the authoritative cloud message without a blank tail.
        await call('fork', [None])
        await call('choose_tools', [None, False, True, True, 'live', '', True, False,
                            True, True, ['text_statistics'], '[]', 1, model._conversation_id])
        await call('transfer_input', ['new-settings-followup', None])
        await call('predict_with_ui', [None, None, model.chatbot, False, [], 'English'])
        assert len(model.chatbot) == 1, model.chatbot
        assert model.chatbot[0][1] == '模拟 Agent 回答：new-settings-followup'
        assert len(model.history) == 2, model.history
        assert model._session_settings['tools']['network'] is False
        await call('change_model', ['GPT3.5 Turbo', None, '', 1, 1, 'QA', '', None])
        ordinary = state[current_id]
        assert ordinary.chatbot == model.chatbot
        assert len(ordinary.chatbot) == 1 and ordinary.chatbot[0][1]
        await call('change_model', ['OpenAI Agent', None, '', 1, 1, 'QA', '', None])
        await call('observe_history',[None])
        await call('reset',[None,False])
        from uuid import uuid4
        upload=Path(gr.utils.get_upload_folder())/('qa-'+uuid4().hex)
        upload.mkdir(parents=True);path=upload/'synthetic.csv';path.write_text('day,value\n1,10\n2,20')
        data=[{'path':str(path),'orig_name':path.name,'meta':{'_type':'gradio.FileData'}}]
        model=state[current_id]
        await call('upload_files',[None,data,model._conversation_id])
        assert model._pending_upload_paths
        await call('transfer_input',['',None])
        await call('predict_with_ui',[None,None,[],False,[],'English',data])
        from modules.agent.ui import message_file_projection
        assert message_file_projection(model).user_files[0][0]['name'] == 'synthetic.csv'
        assert '/workspace/inputs/' not in model.chatbot[0][0] and not model._pending_upload_paths

        # Empty native Files become read-only while the real main generator
        # waits for authorization. Exercise that state and concurrent deny,
        # rather than testing a substitute button or direct model response.
        await call('reset', [None, False])
        await call('transfer_input', ['permission', None])
        predict_index = functions['predict_with_ui']
        predict_inputs = [None, None, [], False, [], 'English', []]
        frame = await app.process_api(predict_index, predict_inputs, state=state, request=request)
        while not model._pending_actions and frame['is_generating']:
            frame = await app.process_api(predict_index, predict_inputs, state=state,
                                          request=request, iterator=frame['iterator'])
        assert model._state['outcome'] == 'requires_action' and model._pending_actions
        outputs = {getattr(component, 'elem_id', None): value
                   for component, value in zip(app.fns[predict_index].outputs, frame['data'])}
        assert outputs['status-display'] in ('', None)
        assert state.blocks_config.blocks[app.fns[predict_index].outputs[next(i for i,c in enumerate(app.fns[predict_index].outputs) if getattr(c,'elem_id',None)=='agent-upload-files')]._id].interactive is False
        assert state.blocks_config.blocks[app.fns[predict_index].outputs[next(i for i,c in enumerate(app.fns[predict_index].outputs) if getattr(c,'elem_id',None)=='agent-pending-files')]._id].interactive is False
        deny_index = [i for i, fn in enumerate(app.fns)
                      if fn.fn and fn.fn.__name__ == 'respond'][1]
        assert app.config['dependencies'][deny_index]['queue'] is False
        identifier = model._pending_actions[0]['request_id']
        denied = await app.process_api(deny_index, [None, identifier], state=state, request=request)
        assert not model._pending_actions
        while frame['is_generating']:
            frame = await app.process_api(predict_index, predict_inputs, state=state,
                                          request=request, iterator=frame['iterator'])
        assert model._state['outcome'] == 'completed'
        assert '未访问网站' in model.chatbot[-1][1]
        # The exhausted generator returns Gradio's FINISHED/None placeholders;
        # use the actual live projection to inspect the terminal component state.
        panel_values = next(i for i, fn in enumerate(app.fns) if fn.fn and fn.fn.__name__ == 'values' and any(getattr(c, 'elem_id', None) == 'agent-pending-files' for c in fn.outputs))
        completed = (await app.process_api(panel_values, [None], state=state, request=request))['data']
        outputs = {getattr(component, 'elem_id', None): value
                   for component, value in zip(app.fns[panel_values].outputs, completed)}
        assert outputs['agent-upload-files']['interactive'] is True
        assert outputs['agent-pending-files']['interactive'] is True
    finally:
        app.close()


if __name__ == '__main__':
    import asyncio
    asyncio.run(exercise())
