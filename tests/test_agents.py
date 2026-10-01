import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('agent_runtime', ROOT/'optional/agents/runtime.py')
import sys
runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime
spec.loader.exec_module(runtime)


def event(kind, turn_id='t1', session='sess_test', **kw):
    return {'type': 'agent.session.turn.'+kind, 'session_id':session, 'turn_id':turn_id, **kw}


def turn(kind, turn='t1', subagent=None):
    return event(kind, turn, turn={'id':turn, 'subagent_id':subagent})


def text(kind, value, turn_id='t1', item='msg1', **kw):
    return event('output_text.'+kind, turn_id, item_id=item, output_index=0, content_index=0,
                 **{('delta' if kind == 'delta' else 'text'):value}, **kw)


class Stream:
    def __init__(self, events, trace): self.events, self.trace = events, trace
    def __enter__(self): self.trace.append('stream_open'); return iter(self.events)
    def __exit__(self,*args): self.trace.append('stream_close')

class FakeClient:
    def __init__(self, events, session_status='idle', saved_turn='completed'):
        self.trace=[]; self.payloads=[]; self.submitted=[]
        self.events=events; self.session_status=session_status; self.saved_turn=saved_turn
        operations=SimpleNamespace(create=self.send, stream=self.stream)
        self.required_actions=[]
        sessions=SimpleNamespace(create=self.create, events=operations,
           retrieve=lambda id: {'status': self.session_status, 'required_actions':self.required_actions},
           turns=SimpleNamespace(retrieve=lambda id,**kw:{'id':id,'status':self.saved_turn}, list=lambda *a,**kw:[]),
           items=SimpleNamespace(list=lambda *a,**k:[{'type':'message','role':'assistant','turn_id':'t1','content':[{'type':'output_text','text':'saved'}]}]),
           artifacts=SimpleNamespace(list=lambda *a,**k:[]))
        self.beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions))
    def create(self, **kw): self.payloads.append(kw); return Stream(self.events,self.trace)
    def stream(self,*a,**kw): return Stream(self.events,self.trace)
    def send(self,*a,**kw): self.trace.append('submit'); self.submitted.append(kw)


def test_delta_done_replacement_dedupe_and_other_turns():
    state=runtime.TurnState()
    state.accept(turn('created'))
    state.accept(text('delta','he',event_id='e1'))
    state.accept(text('delta','he',event_id='e1'))
    state.accept(text('delta','llo'))
    state.accept(text('done','hello'))
    state.accept(text('done','wrong turn',turn_id='other'))
    state.accept(turn('completed', turn='child', subagent='sub1'))
    assert state.outcome=='incomplete'
    state.accept(turn('completed'))
    assert state.text=='hello' and state.outcome=='completed'


def test_only_done_and_session_isolation():
    a,b=runtime.TurnState(),runtime.TurnState()
    a.accept(turn('created')); b.accept(turn('created'))
    a.accept(text('done','one')); b.accept(text('done','two'))
    a.accept({'type':'agent.session.turn.output_text.done','session_id':'other','turn_id':'t1','item_id':'msg1','output_index':0,'content_index':0,'text':'alien'})
    assert a.text=='one' and b.text=='two'

@pytest.mark.parametrize('kind', ['failed','cancelled'])
def test_terminal_failure(kind):
    client=FakeClient([turn('created'),turn(kind)])
    with pytest.raises(runtime.AgentError, match=kind) as error: runtime.run_task(client,'test','model')
    assert error.value.state.outcome==kind
    assert len(client.payloads)==1

@pytest.mark.parametrize('events', [[], [turn('created'), {'type':'agent.session.idle'}], [turn('created'),turn('completed',turn='child',subagent='sub')]])
def test_eof_idle_and_subagent_completion_do_not_mean_success(events):
    client=FakeClient(events)
    with pytest.raises(runtime.AgentError, match='without target turn completion'): runtime.run_task(client,'test','model')
    assert len(client.payloads)==1


def test_payload_isolated_hosted_no_network_no_subagents_no_legacy_tools():
    client=FakeClient([turn('created'),text('done','result'),turn('completed')])
    result=runtime.run_task(client,'test','explicit-model')
    assert result.text=='result'
    payload=client.payloads[0]
    assert payload['environment']=={'type':'openai_hosted','network':{'mode':'disabled'}}
    assert payload['agent']['tools']==[]
    assert payload['agent']['multi_agent']=={'enabled':False}
    assert payload['agent']['model']=='explicit-model'


def test_followup_stream_open_before_submit_and_no_new_session():
    client=FakeClient([turn('created'),turn('completed')])
    runtime.run_task(client,'follow up','model',session_id='sess_test')
    assert client.trace[:2]==['stream_open','submit']
    assert not client.payloads
    assert client.submitted[0]['events'][0]['type']=='agent.session.input.message'


def test_followup_busy_does_not_send():
    client=FakeClient([],session_status='in_progress')
    with pytest.raises(runtime.AgentError,match='not ready'): runtime.run_task(client,'follow up','model',session_id='sess_test')
    assert not client.submitted and not client.payloads


def test_function_allowlist_validates_parameters_and_submits_result():
    client=FakeClient([]); state=runtime.TurnState('sess_test','t1'); handled=set()
    action={'type':'function_call','turn_id':'t1','call_id':'call1','name':'text_statistics','arguments':{'text':'hello world'}}
    runtime.handle_function_actions(client,state,{'required_actions':[action]},True,handled)
    result=client.submitted[0]['events'][0]
    assert result['success'] and '"words": 2' in result['output']
    runtime.handle_function_actions(client,state,{'required_actions':[action]},True,handled)
    assert len(client.submitted)==1
    action=dict(action,call_id='call2',arguments={'text':'hello','path':'/private'})
    runtime.handle_function_actions(client,state,{'required_actions':[action]},True,handled)
    assert not client.submitted[1]['events'][0]['success']
    with pytest.raises(runtime.AgentError,match='not explicitly allowed'):
        runtime.handle_function_actions(client,state,{'required_actions':[dict(action,name='shell',call_id='call3')]},True,handled)


def test_recovery_reads_authoritative_turn_without_resubmitting():
    client=FakeClient([],saved_turn='cancelled')
    result=runtime.inspect_saved(client,'sess_test','t1')
    assert result['outcome']=='cancelled' and result['text']=='saved'
    assert not client.submitted and not client.payloads


def test_cancel_is_real_remote_event():
    client=FakeClient([])
    runtime.cancel_session(client,'sess_test')
    assert client.submitted[0]['events']==[{'type':'agent.session.input.cancel'}]

@pytest.mark.parametrize('status',[401,403,429,500])
def test_errors_do_not_expose_body_or_secret(status):
    error=SimpleNamespace(status_code=status)
    assert str(status) in str(runtime.safe_request_error(error))
    class Failure(Exception):
        status_code=status
    client=FakeClient([])
    def fail(**kw): raise Failure('private prompt fake-secret-value')
    client.beta.agents.sessions.create=fail
    with pytest.raises(runtime.AgentError) as caught: runtime.run_task(client,'private prompt','model')
    assert 'private prompt' not in str(caught.value) and 'fake-secret-value' not in str(caught.value)


def test_key_is_dedicated_no_core_fallback(tmp_path,monkeypatch):
    monkeypatch.delenv(runtime.KEY_NAME,raising=False)
    monkeypatch.setenv('OPENAI_API_KEY','wrong-provider-key')
    path=tmp_path/'.env.agents';path.write_text('CHUANHU_AGENT_API_KEY=\n')
    with pytest.raises(runtime.AgentError): runtime.read_dedicated_key(path)
    path.write_text('CHUANHU_AGENT_API_KEY="dedicated-test-key"\n')
    assert runtime.read_dedicated_key(path)=='dedicated-test-key'


def test_followup_ignores_replayed_prior_root_turn():
    client=FakeClient([turn('created',turn='old'),text('done','OLD',turn_id='old'),turn('completed',turn='old'),turn('created',turn='new'),text('done','NEW',turn_id='new'),turn('completed',turn='new')])
    client.beta.agents.sessions.turns.list=lambda *a,**kw:[{'id':'old'}]
    result=runtime.run_task(client,'follow up','model',session_id='sess_test')
    assert result.turn_id=='new' and result.text=='NEW'
    assert len(client.submitted)==1


def test_uncertain_creation_lookup_uses_exact_run_id_and_does_not_resubmit():
    client=FakeClient([])
    run_id='a'*32
    client.beta.agents.sessions.list=lambda **kw:[{'id':'sess_other','metadata':{}},{'id':'sess_match','metadata':{'chuanhu_run_id':run_id}}]
    client.beta.agents.sessions.turns.list=lambda *a,**kw:[{'id':'t1','subagent_id':None}]
    assert runtime.find_uncertain_session(client,run_id)==('sess_match','t1')
    assert not client.submitted and not client.payloads
