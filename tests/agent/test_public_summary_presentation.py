"""Public summary presentation never invents content or removes tool boundaries."""
from copy import deepcopy
import pytest
from modules.agent import transcript
from modules.agent.transcript_view import _activity, _tool_runs, i18n


def summary(text='', status='in_progress'):
    return transcript.normalize([dict(id='r',type='reasoning',turn_id='t1',status=status,
        summary=[dict(type='summary_text',text=text)],encrypted_content='HIDDEN',
        content='PRIVATE',title='UNVERIFIED')],scope_id='scope')['timeline'][0]


@pytest.fixture(autouse=True)
def language():
    previous=i18n.language;i18n.change_language('zh_CN')
    yield
    i18n.change_language(previous)


@pytest.mark.parametrize('text',['',' \n\t'])
def test_empty_active_summary_is_plain_nonexpandable_state(text):
    entry=summary(text);saved=deepcopy(entry)
    markup=_activity([entry],active=True)
    assert '正在思考' in markup and 'agent-thinking-state' in markup
    assert '<details' not in markup and '<summary' not in markup
    assert 'chevron' not in markup and 'agent-activity-elapsed' not in markup
    assert 'HIDDEN' not in markup and 'PRIVATE' not in markup and 'UNVERIFIED' not in markup
    assert entry==saved


@pytest.mark.parametrize('phase',['completed','failed','cancelled','incomplete','turn_failed','turn_cancelled','unknown'])
def test_empty_terminal_or_unknown_summary_has_no_placeholder(phase):
    entry=summary();entry['capture']={};saved=deepcopy(entry)
    assert _activity([entry],active=True,clock={'r':dict(phase=phase)})==''
    assert entry==saved


def test_empty_summary_preserves_capture_notice_and_canonical_boundary():
    entry=summary('', 'completed');entry['capture']=dict(omitted=True,truncated=True)
    markup=_activity([entry])
    assert '部分内容未保存' in markup and '内容已截断' in markup
    assert '<details' not in markup and 'agent-thinking-state' not in markup
    tools=transcript.normalize([dict(id=key,type='command_execution',turn_id='t1',status='completed',command='pwd')
        for key in ('before','after')],scope_id='scope')['timeline']
    timeline=[tools[0],entry,tools[1]];saved=deepcopy(timeline)
    groups=_tool_runs(timeline,'scope')
    assert [item['kind'] for item in groups]==['tool_group','summary','tool_group']
    assert groups[0]['id']!=groups[-1]['id'] and timeline==saved


@pytest.mark.parametrize('phase,title',[('running','正在思考'),('waiting','正在思考'),
    ('completed','已思考'),('failed','思考'),('cancelled','思考'),('unknown','思考')])
def test_nonempty_public_summary_has_truthful_title_and_escaped_content(phase,title):
    entry=summary('<script>public</script>\n公开摘要');saved=deepcopy(entry)
    markup=_activity([entry],active=True,clock={'r':dict(phase=phase,running=phase in ('running','waiting'))})
    assert f'>{title}</span>' in markup and '<details' in markup
    assert '&lt;script&gt;public&lt;/script&gt;<br>公开摘要' in markup
    assert '公开思考摘要' not in markup and 'UNVERIFIED' not in markup
    assert 'agent-activity-elapsed' not in markup and entry==saved


def test_live_empty_to_public_to_terminal_keeps_same_canonical_occurrence():
    current=summary();identifier=current['id']
    assert 'agent-thinking-state' in _activity([current],active=True)
    completed=summary('公开文本','completed')
    merged=transcript.merge(transcript.normalize([],scope_id='scope'),
        transcript.normalize([dict(id='r',type='reasoning',turn_id='t1',status='completed',summary=[dict(type='summary_text',text='公开文本')])],scope_id='scope'))
    assert merged['timeline'][0]['id']==identifier==completed['id']
    assert '已思考' in _activity([completed])
    assert len(merged['timeline'])==1
