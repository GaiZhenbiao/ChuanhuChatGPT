"""Reply ownership across user-only snapshots; no API calls or row guessing."""
from copy import deepcopy
import html
import pytest
from agent_fixtures import env, select
from test_runtime import message
from modules.agent.ui import AgentPanel, message_file_projection
from modules.agent.message_files import decode_rows
from modules.agent import transcript


def model(env):
    result=select(env)
    result._state.update(generation='g',session_id='sess_test',turn_id='t1',outcome='in_progress')
    result.history=[{'role':'user','content':'question'},{'role':'assistant','content':''}]
    result._display=result.chatbot=[['question','']]
    result._answer_index=1;result._answer_row=0;result._running=True
    result._transcript_preview=[dict(id='local-g-'+role,type='message',role=role,turn_id='local-g',content=[dict(type='input_text' if role=='user' else 'output_text',text='question' if role=='user' else '')]) for role in ('user','assistant')]
    return result


def command(key='cmd',turn='t1',status='in_progress'):
    return dict(id=key,type='command_execution',turn_id=turn,status=status,command='pwd')


def update(model,items,**extra):
    assert model._accept(dict(type='progress',items=items,session_id='sess_test',turn_id='t1',outcome='in_progress',**extra),'g')


def render(model):
    def formatter(value):
        return '<div class="raw-message hideM">'+html.escape(value)+'</div><div class="md-message">'+html.escape(value)+'</div>'
    return AgentPanel(format_assistant=formatter).render_chat(model,model._display)


def assert_single(model,tool=False,waiting=True):
    projection=message_file_projection(model,model._display)
    rows=render(model)
    assert len(rows)==1 and not projection.view_only_rows
    assert projection.row_anchors.get(0)
    assert decode_rows(rows,model._conversation_id)==model._display
    assert ('agent-history-activity' in rows[0][1])==tool
    assert 'data-turn-id="t1"' in rows[0][1]
    assert ('data-waiting="true"' in rows[0][1])==waiting
    return rows[0][1]


def test_waiting_authoritative_first_tool_append_body_and_terminal_stay_one_reply(env):
    m=model(env)
    # Initial preview has its own explicit local generation identity.
    m._state['turn_id']=None
    assert len(render(m))==1 and 'data-turn-id="local-g"' in render(m)[0][1]
    m._state['turn_id']='t1'
    assert 'data-turn-id="t1"' in render(m)[0][1]
    user=message('u','question',role='user')
    update(m,[user],history_authoritative=True)
    assert m._display==[['question',None]] and m._answer_index==1 and m._answer_row==0
    assert_single(m)
    update(m,[user,command()],history_authoritative=True)
    assert_single(m,tool=True,waiting=False)
    update(m,[user,command(),command('cmd2')],history_authoritative=True)
    assert_single(m,tool=True,waiting=False)
    # A text-only event after the authoritative user-only snapshot is retained.
    assert m._accept(dict(type='progress',session_id='sess_test',turn_id='t1',text='Body',outcome='in_progress'),'g')
    assert m._display==[['question','Body']]
    assert_single(m,tool=True,waiting=False)
    answer=message('a','Body')
    assert m._accept(dict(type='result',session_id='sess_test',turn_id='t1',items=[user,command(status='completed'),command('cmd2',status='completed'),answer],sync_complete=True,outcome='completed'),'g')
    text=assert_single(m,tool=True,waiting=False)
    assert text.index('agent-history-activity')<text.index('<div class="md-message">Body')


def test_partial_current_user_replaces_preview_without_splitting_tools(env):
    m=model(env)
    update(m,[message('u','question',role='user'),command()])
    assert not m._transcript_preview
    assert_single(m,tool=True,waiting=False)


@pytest.mark.parametrize('outcome',['completed','cancelled','failed'])
def test_terminal_user_only_history_tools_have_same_reply_without_fake_message(env,outcome):
    m=model(env)
    update(m,[message('u','question',role='user'),command()],history_authoritative=True)
    m._state['outcome']=outcome;m._running=False
    m._sync_items(m._cloud_items)
    assert m.history==[{'role':'user','content':'question'}]
    assert_single(m,tool=True,waiting=False)
    assert len([x for x in m.history_document({})['agent_transcript']['timeline'] if x['kind']=='message'])==1


def test_two_turns_keep_distinct_rows(env):
    m=model(env)
    items=[message('u0','old','t0',role='user'),command('oldcmd','t0','completed'),message('a0','old reply','t0'),message('u','question',role='user'),command()]
    update(m,items,history_authoritative=True)
    rows=render(m)
    assert len(rows)==2 and 'old reply' in rows[0][1] and 'data-turn-id="t1"' not in rows[0][1]
    assert 'data-turn-id="t1"' in rows[1][1] and 'old reply' not in rows[1][1]
    assert decode_rows(rows,m._conversation_id)==m._display


def test_unassigned_tool_and_different_turn_user_never_merge(env):
    m=model(env)
    update(m,[message('u','question',role='user'),command(turn='other')],history_authoritative=True)
    projection=message_file_projection(m,m._display)
    assert len(projection.rows)==2 and projection.view_only_rows=={1}
    assert not projection.cell_segments.get((0,1))


def test_ambiguous_repeated_users_in_one_turn_do_not_claim_empty_reply(env):
    m=model(env)
    m._state['outcome']='completed';m._running=False
    update(m,[message('u','question',role='user'),message('u2','question',role='user'),command()],history_authoritative=True)
    assert m._answer_row is None
    projection=message_file_projection(m,m._display)
    assert len(projection.rows)==3 and projection.view_only_rows=={2}


def test_stale_generation_cannot_change_current_reply(env):
    m=model(env)
    update(m,[message('u','question',role='user'),command()],history_authoritative=True)
    before=deepcopy(m._display)
    assert not m._accept(dict(type='progress',items=[message('other','wrong',role='user')],turn_id='other',session_id='sess_test'),'stale')
    assert m._display==before
    assert_single(m,tool=True,waiting=False)


def test_turn_files_remain_explicit_separate_section(env):
    m=model(env)
    update(m,[message('u','question',role='user'),command()],history_authoritative=True,
           transcript_artifacts=[dict(id='file',session_id='sess_test',turn_id='t1',name='report.txt',size=7,status='ready')])
    projection=message_file_projection(m,m._display)
    assert len(projection.rows)==2 and projection.view_only_rows=={1}
    assert 'agent-history-activity' in render(m)[0][1]
    assert '本轮文件' in render(m)[1][1] and 'report.txt' in render(m)[1][1]
    assert decode_rows(render(m),m._conversation_id)==m._display


def test_real_assistant_messages_preserve_ids_and_event_order(env):
    m=model(env)
    update(m,[message('u','question',role='user'),message('comment','Before'),command(),message('answer','After')],history_authoritative=True)
    rows=render(m)
    assert len(rows)==1 and rows[0][1].index('md-message">Before')<rows[0][1].index('agent-history-activity')<rows[0][1].index('md-message">After')
    messages=[x['source_id'] for x in m._transcript['timeline'] if x['kind']=='message']
    assert messages==['u','comment','answer']


def test_different_turn_assistant_messages_keep_individual_rows(env):
    m=model(env)
    update(m,[message('u','question',role='user'),message('answer','Current'),message('other','Other','t2'),command('othercmd','t2')],history_authoritative=True)
    assert len(render(m))==2
    assert 'Other' not in render(m)[0][1] and 'Other' in render(m)[1][1]
    assert 'othercmd' not in render(m)[0][1]


def test_other_turn_empty_assistant_is_not_current_turn_placeholder(env):
    m=model(env)
    update(m,[message('u','question',role='user'),message('other','',turn_id='t2'),command()],history_authoritative=True)
    assert m._answer_index is None and m._answer_row is None
    projection=message_file_projection(m,m._display)
    assert len(projection.rows)==2 and projection.view_only_rows=={1}
    assert 'agent-history-activity' not in render(m)[0][1]
    assert 'agent-history-activity' in render(m)[1][1]
