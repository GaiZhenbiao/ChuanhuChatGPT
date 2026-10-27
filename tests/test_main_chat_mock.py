"""The browser QA fixture itself must implement the contracts being exercised."""
import json
from main_chat_mock import MainChatMock
from modules.agent.tools import validate_settings


def run(service,prompt='hello',session=None):
    return service.worker({'action':'run','prompt':prompt,'session_id':session,'model':'gpt-6-astra','reasoning':None,'instructions':'','tool_settings':validate_settings({})})


def test_mock_followup_settings_and_separate_new_session():
    service=MainChatMock();first=list(run(service))[-1];sid=first['session_id']
    updated=list(service.worker({'action':'update','session_id':sid,'model':'gpt-6-sol','reasoning':'high'}))[-1]
    assert updated['settings']=={'model':'gpt-6-sol','reasoning':'high'}
    second=list(run(service,'continue',sid))[-1]
    third=list(run(service,'new chat'))[-1]
    assert second['session_id']==sid and len(second['items'])==4
    assert third['session_id']!=sid


def test_mock_browser_permission_and_login_continue_same_turn_without_values():
    service=MainChatMock();observer=run(service,'login')
    message=next(observer);sid=message['session_id'];turn=message['turn_id']
    while not message['required_actions']:message=next(observer)
    card=message['required_actions'][0]
    assert card['request']['type']=='browser_origin_access'
    response=list(service.worker({'action':'browser_response','session_id':sid,'turn_id':turn,'request_id':card['request_id'],'response':{'type':'browser_origin_access','decision':'approve'}}))[-1]
    assert response['accepted']
    message=next(observer)
    while not message['required_actions'] or message['required_actions'][0]['request']['type']!='browser_authentication':message=next(observer)
    card=message['required_actions'][0]
    list(service.worker({'action':'browser_response','session_id':sid,'turn_id':turn,'request_id':card['request_id'],'response':{'type':'browser_authentication','action':'submit','selected_option':'password','fields':[{'field_id':'email','value':'fixture-only@example.invalid'},{'field_id':'password','value':'fixture-only-password'}]}}))
    final=list(observer)[-1]
    assert final['outcome']=='completed' and final['turn_id']==turn
    assert 'fixture-only-password' not in json.dumps(final) and 'fixture-only@example.invalid' not in json.dumps(final)


def test_mock_stop_long_task_and_recover_terminal_state():
    service=MainChatMock();observer=run(service,'slow');initial=next(observer)
    list(service.worker({'action':'cancel','session_id':initial['session_id'],'turn_id':initial['turn_id']}))
    assert list(observer)[-1]['outcome']=='cancelled'
    restored=list(service.worker({'action':'recover','session_id':initial['session_id']}))[-1]
    assert restored['outcome']=='cancelled' and restored['sync_complete']


def test_mock_files_preparing_duplicate_names_failure_and_retry():
    service=MainChatMock();final=list(run(service,'files-only'))[-1];sid=final['session_id']
    assert final['text']==''
    updates=list(service.worker({'action':'download','session_id':sid}))
    assert all(item['status']=='preparing' for item in updates[0]['artifacts'])
    files=updates[-1]['artifacts'];assert len(files)==3 and files[0]['name']==files[1]['name']
    assert files[-1]['status']=='failed'
    retried=list(service.worker({'action':'download','session_id':sid,'artifact_ids':[files[-1]['id']]}))[-1]
    assert retried['artifacts'][0]['status']=='ready'
