"""Run real history upload/delete dependency chains with Gradio session state."""
from pathlib import Path
import subprocess
import sys


def test_history_upload_delete_refresh_send_boundaries():
    result = subprocess.run([sys.executable, __file__, '--exercise'],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


async def exercise():
    import html
    import json
    import re
    import tempfile
    import gradio as gr
    from gradio.state_holder import SessionState
    from main_chat_preview import build

    app = build()
    state = SessionState(app)
    request = gr.Request(session_hash='history-event-boundary')
    dependencies = app.get_config_file()['dependencies']
    names = {fn.fn.__name__: index for index, fn in enumerate(app.fns) if fn.fn}
    current_id = app.fns[names['initial']].outputs[0]._id
    wire = {key: component.value for key, component in app.blocks.items()
            if hasattr(component, 'value')}

    async def call(index, inputs=None):
        fn = app.fns[index]
        if inputs is None:
            inputs = [None if isinstance(component, gr.State) else wire[component._id]
                      for component in fn.inputs]
        result = await app.process_api(index, inputs, state=state, request=request)
        while True:
            for component, value in zip(fn.outputs, result['data']):
                if isinstance(component, gr.State):
                    continue
                if isinstance(value, dict) and value.get('__type__') == 'update':
                    if 'value' in value:
                        wire[component._id] = value['value']
                elif value is not None:
                    wire[component._id] = value
            if not result['is_generating']:
                return result
            result = await app.process_api(index, inputs, state=state, request=request,
                                           iterator=result['iterator'])

    async def chain(index, inputs=None):
        await call(index, inputs)
        pending = [index]
        executed = []
        while pending:
            parent = pending.pop(0)
            for child, dependency in enumerate(dependencies):
                if dependency['trigger_after'] == parent:
                    await call(child)
                    executed.append(child)
                    pending.append(child)
        return executed

    def marker():
        component = next(c for c in app.blocks.values()
                         if getattr(c, 'elem_id', None) == 'model-capability-state')
        payload = re.search(r'data-model-capabilities="([^"]+)"', wire[component._id])
        assert payload, wire[component._id]
        return json.loads(html.unescape(payload.group(1)))

    def assert_boundary(agent, steps):
        model = state[current_id]
        caps = marker()
        assert caps['agent_tools'] is agent
        assert caps['regenerate'] is (not agent)
        assert caps['history_delete'] is (not agent)
        if agent:
            panel = next(fn.fn.__self__ for fn in app.fns
                         if fn.fn and hasattr(getattr(fn.fn, '__self__', None), 'config_target'))
            assert wire[panel.input_target._id] == model._conversation_id
            assert wire[panel.config_target._id] == model._conversation_id
            assert caps['input_target'] == model._conversation_id
        return model

    async def send(text):
        # Read the exact updated browser inputs, including the opaque target.
        transfer = names['transfer_input']
        wire[app.fns[transfer].inputs[0]._id] = text
        await chain(transfer)
        model = state[current_id]
        assert model.chatbot[-1][0].endswith(text), model.chatbot
        assert model.chatbot[-1][1], model.chatbot
        assert not getattr(model, '_pending_send', None)

    try:
        await call(names['initial'], [])
        await chain(names['change_model'],
                    ['GPT3.5 Turbo', None, '', 1, 1, 'QA', '', None])
        for agent in (False, True):
            if agent:
                await chain(names['change_model'],
                            ['OpenAI Agent', None, '', 1, 1, 'QA', '', None])
            model = state[current_id]
            # Keep the system prompt equal: a .change callback must not be
            # relied on to incidentally refresh the stale conversation targets.
            prompt = model.system_prompt
            data = {'history': [{'role': 'user', 'content': 'Imported question'}, {'role': 'assistant', 'content': 'Imported answer'}],
                    'chatbot': [['Imported question', 'Imported answer']],
                    'system': prompt}
            folder = Path(tempfile.mkdtemp(prefix='history-event-', dir=gr.utils.get_upload_folder()))
            upload = folder / 'synthetic-history.json'
            upload.write_text(json.dumps(data), encoding='utf-8')
            before = getattr(model, '_conversation_id', None)
            uploaded = await chain(names['upload_chat_history'], [None, {
                'path': str(upload), 'orig_name': upload.name,
                'meta': {'_type': 'gradio.FileData'}}])
            model = assert_boundary(agent, uploaded)
            assert model.system_prompt == prompt
            assert model.chatbot[0] == ['Imported question', 'Imported answer']
            if agent:
                assert model._conversation_id != before
            await send('after import')
            saved = model.history_file_path
            before = getattr(model, '_conversation_id', None)
            deleted = await chain(names['delete_chat_history'], [None, saved.removesuffix('.json')])
            model = assert_boundary(agent, deleted)
            assert model.chatbot == []
            if agent:
                assert model._conversation_id != before
            await send('after delete')
    finally:
        app.close()


if __name__ == '__main__':
    import asyncio
    asyncio.run(exercise())
