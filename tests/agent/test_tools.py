"""Tool configuration, permissions and transient authentication, all offline."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from modules.agent import tools
from modules.agent.settings import load_settings, save_settings
from modules.agent.store import BindingStore, owner_identity

@pytest.fixture(autouse=True)
def control_dir(tmp_path, monkeypatch): monkeypatch.setattr(tools,'CONTROL_ROOT',tmp_path/'control')


def client_for(action, status='requires_action'):
    calls=[]
    client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(
        retrieve=lambda session:{'id':session,'status':status,'required_actions':[action]},
        events=SimpleNamespace(create=lambda *a,**k:calls.append((a,k)))))))
    return client,calls


def origin_action(request_id='req_one',turn_id='turn_one'):
    return {'type':'computer_use_approval_request','turn_id':turn_id,'request_id':request_id,
            'request':{'type':'browser_origin_access','origin':'https://example.com','reason':'Read page'}}


def login_action(options=False):
    value=origin_action();value['request']={'type':'browser_authentication','credential_origin':'https://example.com',
        'fields':[{'id':'email','label':'Email','type':'text','required':True},{'id':'password','label':'Password','type':'password','required':True}], 'options':[]}
    if options:value['request']['options']=[{'id':'email_method','label':'Email only','field_ids':['email']}]
    return value


def test_default_builtins_and_distinct_network_search():
    config=tools.build_tool_config({})
    assert config['environment']=={'type':'openai_hosted','network':{'access':'enabled'},'desktop':{'enabled':True}}
    assert {x['type'] for x in config['tools']}=={'web_search','computer_use'}
    assert not config['snapshot']['functions'] and not config['snapshot']['mcp_servers']
    config=tools.build_tool_config({'network':False})
    assert config['environment']['network']['access']=='disabled'
    assert next(x for x in config['tools'] if x['type']=='web_search')['mode']=='live'
    config=tools.build_tool_config({'web_search':False})
    assert config['environment']['network']['access']=='enabled' and 'web_search' not in {x['type'] for x in config['tools']}


def test_disabled_tools_not_discoverable_or_programmatically_exposed():
    config=tools.build_tool_config({'web_search':False,'computer_use':False,'programmatic_tool_calling':False,'functions':[]})
    assert config['tools']==[]
    config=tools.build_tool_config({'functions':['text_statistics'],'tool_search':True})
    assert next(x for x in config['tools'] if x['type']=='function')['defer_loading']
    assert {'tool_search','function'}<={x['type'] for x in config['tools']}


@pytest.mark.parametrize('settings',[{'code_execution':False},{'network':'true'},{'search_mode':'broken'},{'search_domains':['https://example.com/a']},{'functions':['unregistered']},{'unexpected':True}])
def test_invalid_settings_are_actionable(settings):
    with pytest.raises(tools.ToolConfigurationError):tools.validate_settings(settings)


def test_defaults_persist_disabled_across_instances(tmp_path):
    owner=owner_identity('alice');settings=tools.validate_settings({'network':False,'web_search':False})
    save_settings(tmp_path,owner,settings)
    assert load_settings(tmp_path,owner)==settings and load_settings(tmp_path,owner_identity('bob'))['network']
    assert (tmp_path/'agent_data'/owner/'settings.json').stat().st_mode & 0o777==0o600


@pytest.mark.parametrize('decision',['approve','deny','cancel'])
def test_origin_response_exact_request_and_same_session(decision):
    client,calls=client_for(origin_action())
    result=tools.submit_browser_response(client,'sess_one','turn_one','req_one',{'type':'browser_origin_access','decision':decision})
    assert result['accepted'] and len(calls)==1
    assert calls[0][0]==('sess_one',)
    event=calls[0][1]['events'][0]
    assert event=={'type':'agent.session.input.computer_use_approval_request_result','request_id':'req_one','response':{'type':'browser_origin_access','decision':decision}}


@pytest.mark.parametrize('change',[{'turn':'other'},{'request':'old'},{'status':'idle'},{'response':{'type':'browser_origin_access','decision':'approve','origin':'https://evil.example'}},{'response':{'type':'browser_authentication','action':'cancel'}}])
def test_stale_or_widened_approval_rejected(change):
    client,calls=client_for(origin_action(),change.get('status','requires_action'))
    with pytest.raises(tools.ToolConfigurationError):tools.submit_browser_response(client,'sess_one',change.get('turn','turn_one'),change.get('request','req_one'),change.get('response',{'type':'browser_origin_access','decision':'approve'}))
    assert not calls


def test_login_has_only_chosen_fields_and_never_chat_message():
    client,calls=client_for(login_action(True))
    response={'type':'browser_authentication','action':'submit','selected_option':'email_method','fields':[{'field_id':'email','value':'private@example.com'}]}
    tools.submit_browser_response(client,'sess_one','turn_one','req_one',response)
    event=calls[0][1]['events'][0]
    assert 'turn_id' not in event and event['type'].endswith('computer_use_approval_request_result')
    assert event['response']==response
    assert 'private@example.com' not in json.dumps(tools.pending_action_cards({'required_actions':[login_action(True)]},'turn_one'))


@pytest.mark.parametrize('response',[
    {'type':'browser_authentication','action':'submit','fields':[]},
    {'type':'browser_authentication','action':'submit','selected_option':'missing','fields':[]},
    {'type':'browser_authentication','action':'submit','selected_option':'email_method','fields':[{'field_id':'password','value':'secret'}]},
    {'type':'browser_authentication','action':'submit','selected_option':'email_method','fields':[{'field_id':'email','value':''}]},
    {'type':'browser_authentication','action':'cancel','fields':[{'field_id':'email','value':'secret'}]},
])
def test_invalid_login_payloads_do_not_submit(response):
    client,calls=client_for(login_action(True))
    with pytest.raises(tools.ToolConfigurationError):tools.submit_browser_response(client,'sess_one','turn_one','req_one',response)
    assert not calls


def test_login_cancellation_is_not_task_cancellation():
    client,calls=client_for(login_action())
    tools.submit_browser_response(client,'sess_one','turn_one','req_one',{'type':'browser_authentication','action':'cancel'})
    assert calls[0][1]['events'][0]['response']=={'type':'browser_authentication','action':'cancel'}


def test_mcp_requires_explicit_config_auth_tool_scope(monkeypatch):
    server={'server_label':'known','server_url':'https://mcp.example.com/tools','allowed_tools':['read_issue'],'authorization_env':'TEST_MCP'}
    with pytest.raises(tools.ToolConfigurationError):tools.build_tool_config({'mcp_servers':[server]},verify_connections=False,environ={})
    monkeypatch.setattr(tools,'probe_mcp',lambda *a,**k:True)
    config=tools.build_tool_config({'mcp_servers':[server]},environ={'TEST_MCP':'Bearer synthetic','CHUANHU_AGENT_MCP_AUTHORIZATION':json.dumps({'known':{'server_url':server['server_url'],'authorization_env':'TEST_MCP','shared':True,'allowed_tools':['read_issue']}})})
    mcp=next(x for x in config['tools'] if x['type']=='mcp')
    assert mcp['allowed_tools']==['read_issue'] and mcp['transport']['authorization']=='Bearer synthetic'
    assert 'Bearer synthetic' not in json.dumps(config['snapshot'])
    closed=dict(server,enabled=False)
    assert 'mcp' not in {x['type'] for x in tools.build_tool_config({'mcp_servers':[closed]},environ={})['tools']}
    for malformed in [dict(server,allowed_tools=[]),dict(server,allowed_tools=['*']),dict(server,server_url='https://secret:password@example.com'),dict(server,authorization='secret')]:
        with pytest.raises(tools.ToolConfigurationError):tools.validate_settings({'mcp_servers':[malformed]})


def test_mcp_probe_pages_and_rejects_missing_scope(monkeypatch):
    monkeypatch.setattr(tools.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    class Response:
        headers={'content-type':'application/json'};content=b'body'
        def __init__(self,result):self.result=result
        def raise_for_status(self):pass
        def json(self):return {'result':self.result}
    calls=[]
    def post(url,json,headers,follow_redirects=False,extensions=None):
        calls.append(deepcopy(json))
        if json['method']=='initialize':return Response({'protocolVersion':'2025-03-26'})
        if json['method']=='notifications/initialized':return Response({})
        if json['params'].get('cursor'):return Response({'tools':[{'name':'read_issue'}]})
        return Response({'tools':[{'name':'first'}],'nextCursor':'page2'})
    server={'server_label':'known','server_url':'https://mcp.example.com','allowed_tools':['read_issue']}
    assert tools.probe_mcp(server,http_client=SimpleNamespace(post=post),environ={})
    assert len(calls)==4
    with pytest.raises(tools.ToolConfigurationError):tools.probe_mcp(dict(server,allowed_tools=['missing']),http_client=SimpleNamespace(post=post),environ={})


def test_registered_function_parameters_revocation_and_replay():
    action={'type':'function_call','turn_id':'turn_one','call_id':'call_one','name':'text_statistics','arguments':{'text':'hello world'}}
    client,calls=client_for(action);state=SimpleNamespace(session_id='sess_one',turn_id='turn_one');handled=set()
    tools.handle_function_actions(client,state,{'required_actions':[action]},{'functions':['text_statistics']},handled)
    tools.handle_function_actions(client,state,{'required_actions':[action]},{'functions':['text_statistics']},handled)
    assert len(calls)==1 and json.loads(calls[0][1]['events'][0]['output'])['words']==2
    with pytest.raises(tools.ToolConfigurationError):tools.handle_function_actions(client,state,{'required_actions':[dict(action,call_id='call_two')]},{'functions':[]},set())
    invalid=dict(action,call_id='call_three',arguments={'text':17})
    tools.handle_function_actions(client,state,{'required_actions':[invalid]},{'functions':['text_statistics']},set())
    assert calls[-1][1]['events'][0]['success'] is False


def test_control_marker_never_claims_unobserved_cancel_confirmed():
    folder=tools._control_folder('sess_one','turn_one');tools._write_control(folder/'job.json',{'call_id':'known','status':'running'})
    results=tools.cancel_application_tasks('sess_one','turn_one')
    assert results==[{'call_id':'known','status':'running','confirmed':False}]
    assert (folder/'cancel').exists()
    assert not (tools._control_folder('sess_one','turn_other')/'cancel').exists()


def test_binding_rejects_secret_material(tmp_path):
    store=BindingStore(tmp_path)
    with pytest.raises(ValueError):store.put(owner_identity('alice'),'file',{'settings':{'authorization':'secret'}})
    assert store.get(owner_identity('alice'),'file') is None


def test_function_result_submission_disconnect_never_executes_twice(monkeypatch):
    count=[]
    tools.register_function('once_only','Known side effect',{'type':'object'},lambda args,stop:count.append('executed') or {'ok':True})
    action={'type':'function_call','turn_id':'turn_one','call_id':'once','name':'once_only','arguments':{}}
    client,calls=client_for(action)
    def fail(*a,**k):raise OSError('lost acknowledgement')
    client.beta.agents.sessions.events.create=fail
    state=SimpleNamespace(session_id='sess_one',turn_id='turn_one')
    with pytest.raises(OSError):tools.handle_function_actions(client,state,{'required_actions':[action]},{'functions':['once_only']},set())
    client,calls=client_for(action)
    tools.handle_function_actions(client,state,{'required_actions':[action]},{'functions':['once_only']},set())
    assert count==['executed'] and len(calls)==1
    tools.handle_function_actions(client,state,{'required_actions':[action]},{'functions':['once_only']},set())
    assert count==['executed'] and len(calls)==1


def test_concurrent_function_recovery_atomic_claim():
    import threading
    started=threading.Event();finish=threading.Event();count=[];failures=[]
    def execute(args,stop):
        count.append('execute');started.set();assert finish.wait(3);return {'ok':True}
    tools.register_function('claim_once','Known effect',{'type':'object'},execute)
    action={'type':'function_call','turn_id':'turn_one','call_id':'concurrent','name':'claim_once','arguments':{}}
    client,calls=client_for(action);state=SimpleNamespace(session_id='sess_one',turn_id='turn_one')
    def run():
        try:tools.handle_function_actions(client,state,{'required_actions':[action]},{'functions':['claim_once']},set())
        except Exception as error:failures.append(error)
    one=threading.Thread(target=run);one.start();assert started.wait(3)
    two=threading.Thread(target=run);two.start();two.join(3);finish.set();one.join(3)
    assert count==['execute'] and len(calls)==1
    assert len(failures)==1 and isinstance(failures[0],tools.ToolConfigurationError)


def test_binding_survives_new_python_process_and_is_owner_scoped(tmp_path):
    import subprocess,sys
    owner=owner_identity('alice');store=BindingStore(tmp_path)
    store.put(owner,'saved.json',{'state':{'session_id':'sess_persisted','turn_id':'turn_saved'},'settings':{'model':'model'}})
    script="from modules.agent.store import BindingStore,owner_identity; import json,sys; s=BindingStore(sys.argv[1]); print(json.dumps([s.get(owner_identity('alice'),'saved.json'),s.get(owner_identity('bob'),'saved.json')]))"
    output=subprocess.check_output([sys.executable,'-c',script,str(tmp_path)],cwd=Path(__file__).resolve().parents[2],text=True)
    alice,bob=json.loads(output)
    assert alice['state']['session_id']=='sess_persisted' and bob is None


@pytest.fixture
def mcp_server():
    return {'server_label':'known','server_url':'https://mcp.example.com/tools',
            'allowed_tools':['read_issue'],'authorization_env':'SYNTHETIC_MCP_TOKEN'}


def mcp_registry(server, **extra):
    binding = {'server_url':server['server_url'], 'authorization_env':server.get('authorization_env'),
               'allowed_tools':['read_issue'], 'owners':['alice'], **extra}
    return {'CHUANHU_AGENT_MCP_AUTHORIZATION':json.dumps({server['server_label']:binding}),
            'SYNTHETIC_MCP_TOKEN':'Bearer synthetic-only'}


def test_mcp_registry_requires_exact_destination_owner_and_tools(mcp_server):
    environment=mcp_registry(mcp_server)
    assert tools.mcp_authorization(mcp_server,environment,owner='alice')=='Bearer synthetic-only'
    for owner in ('bob','',None):
        with pytest.raises(tools.ToolConfigurationError):
            tools.mcp_authorization(mcp_server,environment,owner=owner)
    for change in ({'server_url':'https://attacker.invalid/tools'}, {'server_url':'https://mcp.example.com/other'},
                   {'authorization_env':'OTHER_SECRET'}, {'allowed_tools':['delete_issue']}):
        with pytest.raises(tools.ToolConfigurationError):
            tools.mcp_authorization(dict(mcp_server,**change),environment,owner='alice')
    assert tools.mcp_authorization(mcp_server,mcp_registry(mcp_server,shared=True),owner='')
    with pytest.raises(tools.ToolConfigurationError):
        tools.mcp_authorization(mcp_server,mcp_registry(mcp_server,shared='true'),owner='')
    with pytest.raises(tools.ToolConfigurationError):
        tools.build_tool_config({'mcp_servers':[mcp_server]},verify_connections=False,environ=environment,owner='bob')


def test_mcp_old_credential_binding_fails_closed(mcp_server):
    environment={'SYNTHETIC_MCP_TOKEN':'Bearer synthetic-only',
                 'CHUANHU_AGENT_MCP_AUTHORIZATION':json.dumps({'known':{
                     'server_url':mcp_server['server_url'],'authorization_env':'SYNTHETIC_MCP_TOKEN'}})}
    with pytest.raises(tools.ToolConfigurationError):
        tools.mcp_authorization(mcp_server,environment,owner='alice')


@pytest.mark.parametrize('address',['127.0.0.1','10.0.0.1','169.254.169.254','::1','fc00::1','::ffff:127.0.0.1','0.0.0.0','224.0.0.1','ff02::1'])
def test_uncredentialed_mcp_cannot_probe_private_resolution(monkeypatch,address):
    monkeypatch.setattr(tools.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',(address,443))])
    client=SimpleNamespace(post=lambda *a,**k:pytest.fail('Private destination must not be contacted'))
    server={'server_label':'public','server_url':'https://example.test/mcp','allowed_tools':['read']}
    with pytest.raises(tools.ToolConfigurationError):
        tools.probe_mcp(server,http_client=client,environ={})


def test_mcp_pins_dns_and_preserves_host_tls_without_redirects(monkeypatch):
    import httpx
    resolved=[];requests=[]
    def resolve(*a,**k):
        resolved.append(a)
        return [(2,1,6,'',('93.184.216.34' if len(resolved)==1 else '127.0.0.1',443))]
    monkeypatch.setattr(tools.socket,'getaddrinfo',resolve)
    def route(request):
        requests.append(request)
        method=json.loads(request.content)['method']
        result={'protocolVersion':'2025-03-26'} if method=='initialize' else {'tools':[{'name':'read'}]}
        return httpx.Response(200,json={'result':result})
    server={'server_label':'public','server_url':'https://mcp.example.com:8443/tools','allowed_tools':['read']}
    with httpx.Client(transport=httpx.MockTransport(route),follow_redirects=True) as client:
        assert tools.probe_mcp(server,http_client=client,environ={})
    assert len(resolved)==1 and len(requests)==3
    assert all(str(request.url)=='https://93.184.216.34:8443/tools' for request in requests)
    assert all(request.headers['host']=='mcp.example.com:8443' for request in requests)
    assert all(request.extensions['sni_hostname']=='mcp.example.com' for request in requests)


def test_mcp_redirect_is_not_followed_even_with_custom_client(monkeypatch):
    import httpx
    monkeypatch.setattr(tools.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
    requests=[]
    def route(request):
        requests.append(request)
        return httpx.Response(307,headers={'Location':'http://127.0.0.1/private'})
    server={'server_label':'public','server_url':'https://example.test/mcp','allowed_tools':['read']}
    with httpx.Client(transport=httpx.MockTransport(route),follow_redirects=True) as client:
        with pytest.raises(tools.ToolConfigurationError):tools.probe_mcp(server,http_client=client,environ={})
    assert len(requests)==1


def test_private_mcp_requires_admin_exception_and_owner(monkeypatch,mcp_server):
    import httpx
    server=dict(mcp_server,server_url='http://127.0.0.1:8080/mcp')
    monkeypatch.setattr(tools.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',8080))])
    environment=mcp_registry(server,allow_private=True)
    requests=[]
    def route(request):
        requests.append(request)
        method=json.loads(request.content)['method']
        return httpx.Response(200,json={'result':{'protocolVersion':'2025-03-26'} if method=='initialize' else {'tools':[{'name':'read_issue'}]}})
    with httpx.Client(transport=httpx.MockTransport(route)) as client:
        for owner in ('bob','',None):
            with pytest.raises(tools.ToolConfigurationError):tools.probe_mcp(server,http_client=client,environ=environment,owner=owner)
        with pytest.raises(tools.ToolConfigurationError):tools.probe_mcp(server,http_client=client,environ=mcp_registry(server),owner='alice')
        assert not requests
        assert tools.probe_mcp(server,http_client=client,environ=environment,owner='alice')
    assert len(requests)==3 and all(r.headers['authorization']=='Bearer synthetic-only' for r in requests)


def test_mcp_rejects_mixed_public_private_dns_before_http(monkeypatch):
    monkeypatch.setattr(tools.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',(ip,443)) for ip in ['93.184.216.34','127.0.0.1']])
    server={'server_label':'public','server_url':'https://example.test/mcp','allowed_tools':['read']}
    with pytest.raises(tools.ToolConfigurationError):
        tools.probe_mcp(server,http_client=SimpleNamespace(post=lambda *a,**k:pytest.fail('Mixed DNS must be rejected')),environ={})


def test_mcp_owned_http_client_disables_environment_proxy(monkeypatch):
    import httpx
    monkeypatch.setattr(tools.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
    created=[]
    class Client:
        def __init__(self,**kwargs):created.append(kwargs)
        def post(self,url,**kwargs):
            request=httpx.Request('POST',url)
            return httpx.Response(307,headers={'Location':'http://127.0.0.1/private'},request=request)
        def close(self):pass
    monkeypatch.setattr(httpx,'Client',Client)
    server={'server_label':'public','server_url':'https://example.test/mcp','allowed_tools':['read']}
    with pytest.raises(tools.ToolConfigurationError):tools.probe_mcp(server,environ={})
    assert created==[{'timeout':30,'follow_redirects':False,'trust_env':False}]


@pytest.mark.parametrize('address', [
    '64:ff9b::7f00:1', '64:ff9b::a00:1', '64:ff9b:1::7f00:1',
    '2002:7f00:1::1', '2001:0:4136:e378:8000:63bf:80ff:fffe',
    '::127.0.0.1', '::ffff:0:127.0.0.1', '::ffff:127.0.0.1',
])
def test_mcp_rejects_embedded_private_ipv6_independent_of_stdlib_tables(monkeypatch,address):
    # 模拟旧版分类表将过渡 IPv6 判为公网；策略仍须明确拒绝。
    monkeypatch.setattr(tools.ipaddress.IPv6Address,'is_global',property(lambda self:True))
    monkeypatch.setattr(tools.ipaddress.IPv6Address,'is_reserved',property(lambda self:False))
    monkeypatch.setattr(tools.socket,'getaddrinfo',lambda *a,**k:[(10,1,6,'',(address,443,0,0))])
    server={'server_label':'public','server_url':'https://example.test/mcp','allowed_tools':['read']}
    with pytest.raises(tools.ToolConfigurationError):
        tools.probe_mcp(server,http_client=SimpleNamespace(post=lambda *a,**k:pytest.fail('Transition address must not be contacted')),environ={})


def test_mcp_preserves_public_ipv6_and_explicit_transition_exception(monkeypatch):
    server={'server_label':'public','server_url':'https://example.test:8443/mcp','allowed_tools':['read']}
    monkeypatch.setattr(tools.socket,'getaddrinfo',lambda *a,**k:[(10,1,6,'',('2606:4700:4700::1111',8443,0,0))])
    destination,host,sni=tools._mcp_probe_destination(server,None)
    assert destination=='https://[2606:4700:4700::1111]:8443/mcp'
    assert host=='example.test:8443' and sni=='example.test'
    monkeypatch.setattr(tools.socket,'getaddrinfo',lambda *a,**k:[(10,1,6,'',('64:ff9b::7f00:1',8443,0,0))])
    destination,_,_=tools._mcp_probe_destination(server,{'allow_private':True})
    assert destination=='https://[64:ff9b::7f00:1]:8443/mcp'
