"""验证 Agent 会话的模型锁定与历史切换边界。"""
import pytest
import json

from agent_fixtures import complete, env, request, select, send


@pytest.mark.parametrize('name', ['GPT3.5 Turbo', 'OpenAI Agent'])
@pytest.mark.parametrize('identifier', [None, ''])
def test_current_unsaved_draft_preserves_model_and_ui(env, monkeypatch, name, identifier):
    from copy import deepcopy
    from modules.history_selection import load_history_model
    monkeypatch.setattr(env.presets, 'HISTORY_DIR', str(env.history_dir), raising=False)
    model = select(env, name=name)
    model.reset()
    model.system_prompt = 'Synthetic draft prompt'
    model.temperature = 0.37
    model._pending_input_text = 'Synthetic unsent input'
    filename = model.history_file_path
    target = identifier
    before = deepcopy({key: getattr(model, key, None) for key in (
        'history_file_path', 'history', 'chatbot', 'system_prompt', 'temperature',
        '_state', '_tool_settings', '_pending_input_text', '_conversation_id')})
    def forbidden(*args, **kwargs):
        raise AssertionError('A current draft must not reset, reload or create a model')
    monkeypatch.setattr(model, 'reset', forbidden)
    monkeypatch.setattr(model, 'load_chat_history', forbidden)
    monkeypatch.setattr(env.factory, 'get_model', forbidden)
    result = load_history_model(model, target, request())
    assert result[0] is model and len(result) == 24
    assert all(value == {'__type__': 'update'} for value in result[1:])
    assert {key: getattr(model, key, None) for key in before} == before
    assert not list(env.history_dir.glob('*.json'))


@pytest.mark.parametrize('case', ['other', 'populated', 'chatbot', 'bound', 'outside', 'symlink', 'owner', 'corrupt', 'busy'])
def test_draft_exception_does_not_hide_invalid_history(env, monkeypatch, tmp_path, case):
    from modules.history_selection import load_history_model
    monkeypatch.setattr(env.presets, 'HISTORY_DIR', str(env.history_dir), raising=False)
    model = select(env)
    model.reset()
    target = model.history_file_path
    expected = '历史文件不存在'
    incoming = request()
    if case == 'other':
        target = 'New synthetic missing draft.json'
    elif case == 'populated':
        model.history = [{'role': 'user', 'content': 'Synthetic content'}]
    elif case == 'chatbot':
        model.chatbot = [['Synthetic question', None]]
    elif case == 'bound':
        model._state['session_id'] = 'synthetic_existing_session'
    elif case == 'outside':
        target = str(tmp_path / 'outside.json')
        model.history_file_path = target
        expected = '当前登录用户'
    elif case == 'symlink':
        (env.history_dir / target).symlink_to(tmp_path / 'missing.json')
        expected = '当前登录用户'
    elif case == 'owner':
        incoming = request(username='someone-else')
        expected = '当前登录用户'
    elif case == 'corrupt':
        (env.history_dir / target).write_text('{invalid')
        expected = '历史记录无法读取或格式无效'
    elif case == 'busy':
        model._pending_send = 'synthetic_pending_send'
        expected = '正在提交或生成'
    with pytest.raises(Exception, match=expected):
        load_history_model(model, target, incoming)


def test_started_agent_rejects_manual_provider_change(env, monkeypatch):
    complete(env, monkeypatch)
    model = select(env)
    send(env, model)
    before = (model.history_file_path, list(model.history), model._state.copy())
    result = env.factory.change_model('GPT3.5 Turbo', None, None, None, None,
                                     None, '', model, request())
    assert result[0] is model
    assert result[8]['value'] == 'OpenAI Agent'
    assert not model._retired
    assert (model.history_file_path, model.history, model._state) == before


def test_new_chat_unlocks_manual_provider_change(env, monkeypatch):
    complete(env, monkeypatch)
    model = select(env)
    send(env, model)
    model.reset()
    result = env.factory.change_model('GPT3.5 Turbo', None, None, None, None,
                                     None, '', model, request())
    assert result[0] is not model
    assert not getattr(result[0], 'is_hosted_agent', False)


def test_agent_internal_model_settings_remain_changeable(env, monkeypatch):
    calls, _ = complete(env, monkeypatch)
    model = select(env)
    send(env, model)
    model.set_agent_model(model.model_name, 'low')
    send(env, model, '继续')
    assert model._reasoning == 'low'
    assert any(call['action'] == 'update' for call in calls)


def test_history_restores_provider_parameters_and_prompt_without_saved_key(env, monkeypatch):
    from modules.history_selection import load_history_model
    monkeypatch.setattr(env.presets, 'HISTORY_DIR', str(env.history_dir), raising=False)
    ordinary = select(env, name='GPT3.5 Turbo')
    ordinary.system_prompt = '恢复的系统提示'
    ordinary.temperature = 0.37
    ordinary.top_p = 0.81
    send(env, ordinary)
    filename = ordinary.history_file_path
    document = env.history_dir / (filename.removesuffix('.json') + '.json')
    saved = json.loads(document.read_text())
    assert saved['model_selection'] == 'GPT3.5 Turbo'
    assert 'api_key' not in saved
    saved['api_key'] = '不得加载的历史密钥'
    document.write_text(json.dumps(saved))
    complete(env, monkeypatch)
    agent = select(env)
    send(env, agent)
    result = load_history_model(agent, filename, request())
    restored = result[0]
    assert not getattr(restored, 'is_hosted_agent', False)
    assert result[1]['value'] == 'GPT3.5 Turbo'
    assert restored.system_prompt == '恢复的系统提示'
    assert restored.temperature == 0.37 and restored.top_p == 0.81
    assert restored.api_key != saved['api_key']
    assert agent._retired


def test_history_restores_agent_session_and_last_internal_model(env, monkeypatch):
    from modules.history_selection import load_history_model
    monkeypatch.setattr(env.presets, 'HISTORY_DIR', str(env.history_dir), raising=False)
    complete(env, monkeypatch)
    agent = select(env)
    send(env, agent)
    agent.set_agent_model('gpt-6-sol', 'low')
    send(env, agent, '继续')
    filename = agent.history_file_path
    ordinary = select(env, name='GPT3.5 Turbo')
    result = load_history_model(ordinary, filename, request())
    restored = result[0]
    assert restored.is_hosted_agent
    assert restored.model_name == 'gpt-6-sol' and restored._reasoning == 'low'
    assert restored._state['session_id'] == agent._state['session_id']
    assert result[1]['value'] == 'OpenAI Agent'


def test_history_selection_rejects_foreign_paths_and_owner(env, tmp_path, monkeypatch):
    from modules.history_selection import load_history_model
    monkeypatch.setattr(env.presets, 'HISTORY_DIR', str(env.history_dir), raising=False)
    model = select(env)
    with pytest.raises(Exception, match='当前登录用户'):
        load_history_model(model, str(tmp_path / 'outside.json'), request())
    with pytest.raises(Exception, match='当前登录用户'):
        load_history_model(model, 'anything', request(username='someone-else'))


def test_worker_identity_cannot_be_overridden_by_tool_configuration(env, monkeypatch):
    model = select(env, username='alice')
    frames = []
    monkeypatch.setattr(env.agents, 'worker_messages', lambda command: frames.append(command.copy()) or iter([]))
    list(model._worker({'action': 'capabilities', 'owner': 'bob'}))
    assert frames[0]['owner'] == 'alice'


def test_terminal_navigation_preserves_completed_reply_before_release(env, monkeypatch):
    model=select(env); saved=[]
    monkeypatch.setattr(model,'auto_save',lambda chat=None:saved.append((model.history_file_path,list(model.history))))
    def worker(command):
        if command['action']=='run':
            yield dict(type='progress',session_id='sess_test',turn_id='turn',outcome='completed',text='Completed answer')
            yield dict(type='result',session_id='sess_test',turn_id='turn',outcome='completed',text='Completed answer')
        elif command['action']=='download':yield dict(type='result',artifacts=[])
        else:raise AssertionError(command['action'])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    iterator=model.predict('Task',[])
    next(iterator); next(iterator)
    assert model._running is False and model._display==[['Task','Completed answer']]
    model.reset()
    list(iterator)
    assert any(any(item.get('content')=='Completed answer' for item in history) for _,history in saved), saved


def test_terminal_history_navigation_saves_and_preserves_old_reply(env, monkeypatch):
    from modules.history_selection import load_history_model
    monkeypatch.setattr(env.presets,'HISTORY_DIR',str(env.history_dir),raising=False)
    ordinary=select(env,name='GPT3.5 Turbo'); send(env,ordinary,'Other task')
    other=ordinary.history_file_path
    model=select(env)
    def worker(command):
        if command['action']=='run':
            yield dict(type='progress',session_id='sess_test',turn_id='turn',outcome='completed',text='Completed answer')
            yield dict(type='result',session_id='sess_test',turn_id='turn',outcome='completed',text='Completed answer')
        elif command['action']=='download':yield dict(type='result',artifacts=[])
        else:raise AssertionError(command['action'])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    iterator=model.predict('Task',[]);next(iterator);next(iterator)
    name=model.history_file_path
    path=env.history_dir/(name.removesuffix('.json')+'.json')
    assert any(item.get('content')=='Completed answer' for item in json.loads(path.read_text())['history'])
    restored=load_history_model(model,other,request())[0]
    assert restored is not model and model._retired
    before=list(restored.history)
    list(iterator)
    assert restored.history==before
    assert any(item.get('content')=='Completed answer' for item in json.loads(path.read_text())['history'])


@pytest.mark.parametrize('name', ['GPT3.5 Turbo', 'OpenAI Agent'])
def test_new_chat_lists_saved_history_only_and_first_send_saves_reserved_path(env, monkeypatch, name):
    from modules.history_selection import load_history_model
    monkeypatch.setattr(env.presets, 'HISTORY_DIR', str(env.history_dir), raising=False)
    complete(env, monkeypatch)
    model = select(env, name=name)
    send(env, model, 'Saved conversation')
    saved = model.history_file_path
    old_chat = [list(row) for row in model.chatbot]
    reset = model.reset()
    reserved = model.history_file_path
    selector = reset[2]
    assert selector.value is None
    choices = [choice[0] for choice in selector.choices]
    assert saved.removesuffix('.json') in choices
    assert reserved.removesuffix('.json') not in choices
    assert not (env.history_dir / reserved).exists()
    send(env, model, 'First new message')
    assert model.history_file_path == reserved
    assert (env.history_dir / reserved).is_file()
    from modules.models import base_model
    assert reserved.removesuffix('.json') in base_model.get_history_names(model.user_name)
    restored = load_history_model(model, saved, request())[0]
    assert restored.chatbot == old_chat


@pytest.mark.parametrize('contents', ['{broken json', '{}', '{"history": [], "chatbot": "invalid"}'])
def test_invalid_saved_history_remains_an_error_after_reset(env, monkeypatch, contents):
    from modules.history_selection import load_history_model
    monkeypatch.setattr(env.presets, 'HISTORY_DIR', str(env.history_dir), raising=False)
    model = select(env, name='GPT3.5 Turbo')
    model.reset()
    (env.history_dir / 'broken.json').write_text(contents)
    with pytest.raises(Exception, match='历史记录无法读取或格式无效'):
        load_history_model(model, 'broken', request())
    with pytest.raises(Exception, match='历史文件不存在'):
        load_history_model(model, 'missing', request())


@pytest.mark.parametrize('name', ['GPT3.5 Turbo', 'OpenAI Agent'])
@pytest.mark.parametrize('with_suffix', [False, True])
def test_history_route_and_direct_load_use_real_gradio_cache_without_reset(env, monkeypatch, name, with_suffix):
    from gradio.processing_utils import save_file_to_cache
    from modules.history_selection import load_history_model
    from modules.models import base_model
    from pathlib import Path
    monkeypatch.setattr(env.presets, 'HISTORY_DIR', str(env.history_dir), raising=False)
    monkeypatch.setattr(base_model, 'save_file_to_cache', save_file_to_cache)
    complete(env, monkeypatch)
    model = select(env, name=name)
    send(env, model, 'Saved ordinary or Agent conversation')
    saved = model.history_file_path
    json_path = env.history_dir / saved
    md_path = json_path.with_suffix('.md')
    expected_json, expected_md = json_path.read_bytes(), md_path.read_bytes()
    expected_chat = [list(row) for row in model.chatbot]
    identifier = saved if with_suffix else saved.removesuffix('.json')
    direct = model.load_chat_history(identifier)
    assert model.chatbot == expected_chat and model.history
    assert direct[2]['value'] == expected_chat
    for button, content, original in zip(direct[-2:], (expected_json, expected_md), (json_path, md_path)):
        cached = Path(button.value['path'] if isinstance(button.value, dict) else button.value)
        assert cached.is_file() and cached != original
        assert cached.read_bytes() == content
    routed = load_history_model(model, identifier, request())
    restored = routed[0]
    assert restored.history and restored.chatbot == expected_chat
    assert routed[4]['value'] == expected_chat
    for button, content, original in zip(routed[17:19], (expected_json, expected_md), (json_path, md_path)):
        cached = Path(button.value['path'] if isinstance(button.value, dict) else button.value)
        assert cached.is_file() and cached != original
        assert cached.read_bytes() == content


def test_ordinary_reset_then_agent_switch_cannot_restore_old_bubbles(env):
    ordinary = select(env, name='GPT3.5 Turbo')
    send(env, ordinary, 'Old synthetic question')
    assert ordinary.chatbot
    ordinary.reset()
    agent = select(env, ordinary)
    assert ordinary.chatbot == []
    assert agent.history == [] and agent.chatbot == [] and agent._display == []
