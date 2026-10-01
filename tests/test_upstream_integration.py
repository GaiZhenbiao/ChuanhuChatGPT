"""Exercise the merged real predict method without importing paid providers."""
import ast
import logging
from pathlib import Path
from types import SimpleNamespace
import time
import traceback
import pytest
from modules import plugin_callbacks as callbacks
from modules.plugin_context import ChatContext, ChatErrorContext


@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('failure', [False, True])
def test_merged_predict_lifecycle(stream, failure):
    source = Path(__file__).resolve().parents[1] / 'modules/models/base_model.py'
    tree = ast.parse(source.read_text())
    model_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and any(
        isinstance(method, ast.FunctionDef) and method.name == 'predict' for method in node.body))
    method = next(node for node in model_class.body if isinstance(node, ast.FunctionDef) and node.name == 'predict')
    construct = lambda role, content: {'role': role, 'content': content}
    scope = dict(ChatContext=ChatContext, ChatErrorContext=ChatErrorContext,
                 plugin_callbacks=callbacks, logging=logging, time=time, traceback=traceback,
                 i18n=lambda key: key, colorama=SimpleNamespace(Fore=SimpleNamespace(BLUE=''), Style=SimpleNamespace(RESET_ALL='')),
                 construct_user=lambda text: construct('user', text),
                 construct_assistant=lambda text: construct('assistant', text),
                 STANDARD_ERROR_MSG='Error: ', NO_APIKEY_MSG='Missing key', NO_INPUT_MSG='Missing input',
                 TOKEN_OFFSET=1000, REDUCE_TOKEN_FACTOR=.5, beautify_err_msg=lambda text: text)
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), scope)

    class SyntheticModel:
        predict = scope['predict']
        def __init__(self):
            self.user_name = 'synthetic'
            self.need_api_key = False
            self.single_turn = False
            self.stream = stream
            self.history = []
            self.all_token_counts = [1]
            self.token_upper_limit = 10000
            self.history_file_path = 'synthetic-history.json'
            self.saved = None
        def prepare_inputs(self, *, real_inputs, chatbot, **kwargs):
            return False, real_inputs, '', real_inputs, chatbot
        def next_chatbot_at_once(self, inputs, chatbot, **kwargs):
            assert inputs == 'question before prepared model'
            assert self.history[-1]['content'] == inputs
            if failure:
                raise RuntimeError('synthetic provider failure')
            self.history.append(construct('assistant', 'answer'))
            return chatbot + [(kwargs['fake_input'], 'answer')], 'done'
        def stream_next_chatbot(self, inputs, chatbot, **kwargs):
            yield self.next_chatbot_at_once(inputs, chatbot, **kwargs)
        def auto_save(self, chatbot):
            self.saved = list(chatbot)

    calls = []
    callbacks.clear_callbacks()
    @callbacks.on_before_chat
    def before(context):
        calls.append('before'); context.user_input += ' before'
    @callbacks.on_after_prepare
    def prepare(context):
        calls.append('prepare'); context.prepared_input += ' prepared'
    @callbacks.on_before_model_call
    def model(context):
        calls.append('model'); context.prepared_input += ' model'
    @callbacks.on_after_chat
    def after(context):
        calls.append('after'); context.assistant_reply = 'plugin answer'
    @callbacks.on_chat_error
    def error(context):
        calls.append('error'); assert isinstance(context.error, RuntimeError)
    @callbacks.on_after_history_saved
    def saved(context):
        calls.append('saved'); assert context.history_file_path == 'synthetic-history.json'
    try:
        instance = SyntheticModel()
        outputs = list(instance.predict('question', []))
        assert calls == ['before', 'prepare', 'model', 'error' if failure else 'after', 'saved']
        assert instance.saved is not None
        if failure:
            assert outputs[-1][1] == 'Error: synthetic provider failure'
        else:
            assert instance.history[-1] == construct('assistant', 'plugin answer')
            assert instance.saved[-1][1] == 'plugin answer'
        assert callbacks.get_errors() == []
    finally:
        callbacks.clear_callbacks()
