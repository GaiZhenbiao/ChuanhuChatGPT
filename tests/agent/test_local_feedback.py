"""UI-only feedback routing; task state and persisted messages stay unchanged."""
from copy import deepcopy
from types import SimpleNamespace
import gradio as gr
from modules.agent.ui import AgentPanel


def model(outcome='in_progress', agent=True):
    current = SimpleNamespace(is_hosted_agent=agent, chatbot=[['hi', 'answer']],
                              history=['hi', 'answer'], _state={'outcome': outcome}, _notice='')
    current._status = lambda: {'in_progress':'正在运行', 'completed':'已完成',
                              'not_started':'准备就绪', 'requires_action':'等待授权或登录',
                              'failed':'执行失败', 'cancelled':'已停止'}[current._state['outcome']]
    return current


def test_agent_stream_is_local_and_completed_hides_without_changing_history():
    panel = AgentPanel(); current = model(); before = deepcopy((current.chatbot, current.history))
    def predict(current):
        yield current.chatbot, current._status()
        current._state['outcome'] = 'requires_action'
        yield current.chatbot, current._status()
        current._state['outcome'] = 'completed'
        yield current.chatbot, current._status()
    frames = list(panel.status_callback(predict, 1, header=True)(current))
    assert [frame[1] for frame in frames] == ['', '', '']
    assert frames[0][-1]['value'] == '' and not frames[0][-1]['visible']
    assert frames[1][-1]['value'] == '' and not frames[1][-1]['visible']
    assert frames[2][-1]['value'] == '' and not frames[2][-1]['visible']
    assert (current.chatbot, current.history) == before


def test_shared_stop_prompt_and_model_change_route_only_agent_branch():
    panel = AgentPanel(); agent = model(); ordinary = model(agent=False)
    callback = panel.status_callback(lambda current: 'callback feedback', header=True)
    assert callback(agent)[0] == '' and not callback(agent)[1]['visible']
    assert callback(current=ordinary)[0] == 'callback feedback'
    assert not callback(ordinary)[1]['visible']
    change = panel.status_callback(lambda previous, replacement: (replacement, 'selected'),
                                   1, header=True, returned_model=0)
    assert change(agent, ordinary)[1] == 'selected'
    assert change(ordinary, agent)[1] == ''


def test_local_stale_noop_and_input_failure_are_not_lost():
    panel = AgentPanel(); current = model('completed')
    noop = panel.status_callback(lambda current: gr.update())(current)
    assert 'value' not in noop
    upload = panel.status_callback(lambda current: '附件未添加：上传失败', input_feedback=True)(current)
    assert not upload['visible'] and upload['value']==''
    current._state['outcome'] = 'failed'
    failed = panel.activity_value(current)
    assert not failed['visible'] and failed['value']==''


def test_completed_authorization_notice_hides_but_recovery_notice_stays_local():
    panel = AgentPanel(); current = model('completed')
    current._notice = '已提交网站请求，等待继续；登录结果尚未确认'
    current._status = lambda: '已完成 · ' + current._notice
    assert not panel.activity_value(current)['visible']
    assert current._notice  # UI projection does not mutate task state.
    current._notice = '当前轮已结束，但云端历史尚未完整同步；回答已保留，请重新连接后继续'
    assert not panel.activity_value(current)['visible']
