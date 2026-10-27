"""Official hosted provisioning status, distinct from actual terminal failure."""
import pytest
from test_inputs_runtime import stage,FakeClient,RUN_ID
from modules.agent import inputs

@pytest.mark.parametrize('statuses',[['provisioning','connected'],['pending','provisioning','connected']])
def test_hosted_provisioning_waits_and_prepares_without_duplicate_session(stage,monkeypatch,statuses):
    make,root=stage;client=FakeClient();client.environment_statuses=statuses
    waits=[];monkeypatch.setattr(inputs.time,'sleep',waits.append)
    result=inputs.prepare_inputs(client,[make()],'test-model',staging_root=root,run_id=RUN_ID)
    assert result['outcome']=='ready' and len(waits)==len(statuses)-1
    assert [operation for operation,args in client.writes].count('session_create')==1
    assert result['submission_started'] is False


def test_provisioning_followed_by_failed_preserves_actual_status_and_never_writes_file(stage,monkeypatch):
    make,root=stage;client=FakeClient();client.environment_statuses=['provisioning','failed']
    original=client.retrieve_environment
    def environment(identifier):
        value=original(identifier)
        if value['status']=='failed':
            value['error']={'code':'environment_connection_failed','type':'environment_error'}
        return value
    client.beta.agents.environments.retrieve=environment
    monkeypatch.setattr(inputs.time,'sleep',lambda _:None)
    with pytest.raises(inputs.InputPreparationError) as caught:
        inputs.prepare_inputs(client,[make()],'test-model',staging_root=root,run_id=RUN_ID)
    state=caught.value.state
    assert state['environment_status']=='failed' and state['last_request_phase']=='preparation.environment_retrieve'
    assert state['submission_started'] is False
    assert state['environment_error']=={'code':'environment_connection_failed','type':'environment_error'}
    assert 'code=environment_connection_failed' in str(caught.value)
    assert [operation for operation,args in client.writes]==['session_create']
