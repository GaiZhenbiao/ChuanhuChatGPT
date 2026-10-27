"""Real worker/SDK/IPC fixture. All HTTP is synthetic and sockets are forbidden."""
import json, os, socket, sys, threading, time
from pathlib import Path
root, case, trace_path, cache_root = sys.argv[1:]
sys.dont_write_bytecode = True
sys.path.insert(0, root)
os.environ['GRADIO_ANALYTICS_ENABLED'] = 'False'
socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(AssertionError('Real network forbidden'))
import httpx2
from modules.agent import worker
from modules.agent.connection import create_client
lock = threading.Lock()
def mark(event):
    with lock:
        with open(trace_path, 'a') as stream: stream.write(json.dumps(dict(event=event, time=time.monotonic())) + '\n')
def message(identifier, text, role='assistant'):
    return dict(id=identifier, type='message', turn_id='turn_complete', status='completed', role=role,
                content=[dict(type='input_text' if role=='user' else 'output_text', text=text)])
def event(kind, **fields):
    return dict(type='agent.session.turn.'+kind, event_id='evt_'+kind, session_id='sess_complete', turn_id='turn_complete', **fields)
class Events(httpx2.SyncByteStream):
    def __iter__(self):
        turn = dict(id='turn_complete', agent_id='agent_complete', session_id='sess_complete', status='in_progress', created_at=1, subagent_id=None)
        position = 1 if case=='normal_reasoning' else 0
        values = [event('created', turn=turn), event('output_text.delta', item_id='msg_complete', output_index=position, content_index=0, delta='Canonical answer')]
        if case in ('normal_multi','get_pending_reconnect','repaired_receipt','repaired_slow_close') or case.startswith('receipt_'):
            values.append(dict(event('output_text.delta',item_id='msg_complete',output_index=position,content_index=1,delta='Second canonical part'),event_id='evt_second_part'))
        if case=='normal_reasoning':
            values.append(dict(event('item.done',output_index=0,item=dict(id='reason_complete',type='reasoning',turn_id='turn_complete',status=None,summary=[dict(type='summary_text',text='Public summary')])),event_id='evt_reason_done'))
        answer=message('msg_complete','Canonical answer')
        if case=='normal_multi':answer['content'].append(dict(type='output_text',text='Second canonical part'))
        if case in ('cancelled_incomplete','failed_incomplete'):answer['status']='incomplete'
        if case not in ('incomplete', 'reconcile_slow_close'): values.append(event('item.done', output_index=position, item=answer))
        if case in ('repaired_receipt','repaired_slow_close'):
            answer = dict(answer, content=answer['content'] + [dict(type='output_text', text='Second canonical part')])
            values.append(dict(event('item.done', output_index=position, item=answer), event_id='evt_repaired_done'))
        ending='cancelled' if case=='cancelled_incomplete' else 'failed' if case=='failed_incomplete' else 'completed'
        values.append(event(ending, turn=dict(turn, status=ending, completed_at=2)))
        for value in values:
            if value['type'].rsplit('.',1)[-1] in ('completed','failed','cancelled'): mark('terminal')
            yield ('event: '+value['type']+'\ndata: '+json.dumps(value)+'\n\n').encode()
        mark('EOF_requested')
        time.sleep(2)
    def close(self):
        mark('close')
        if case in ('slow_close', 'repaired_slow_close', 'reconcile_slow_close'): time.sleep(2)
class IdleEvents(httpx2.SyncByteStream):
    def __iter__(self):
        yield b': offline keepalive\n\n'
        time.sleep(5)
    def close(self):
        mark('recovery_close')
        time.sleep(2)
        mark('recovery_close_done')
class Content(httpx2.SyncByteStream):
    def __iter__(self):
        mark('content_start'); time.sleep(2); yield b'synthetic'; mark('content_done')
def route(request):
    path=request.url.path
    if path.endswith('/agents/sessions/sess_complete/events'):
        if case == 'reconcile_slow_close':
            return httpx2.Response(200, headers={'Content-Type':'text/event-stream'}, stream=IdleEvents())
        return httpx2.Response(200,headers={'Content-Type':'text/event-stream'},content=b'')
    if request.method=='POST' and path.endswith('/agents/sessions'):
        return httpx2.Response(200, headers={'Content-Type':'text/event-stream'}, stream=Events())
    if path.endswith('/agents/sessions/sess_complete'):
        mark('GET_session')
        return httpx2.Response(200, json=dict(id='sess_complete', status='idle', agent=dict(model='gpt-6.1-sol'), required_actions=[]))
    if path.endswith('/turns/turn_complete'):
        agent='agent_other' if case=='receipt_wrong_agent' and (Path(cache_root)/'ready-get').exists() and not (Path(cache_root)/'repaired-get').exists() else 'agent_complete'
        return httpx2.Response(200, json=dict(id='turn_complete', agent_id=agent, session_id='sess_complete', status='completed', created_at=1))
    if path.endswith('/items'):
        mark('GET_items')
        if case=='incomplete': time.sleep(2)
        answer=message('msg_complete','Canonical answer')
        if case.startswith('receipt_'):
            ready=(Path(cache_root)/'ready-get').exists();repaired=(Path(cache_root)/'repaired-get').exists()
            if not ready or case!='receipt_truncated' or repaired:answer['content'].append(dict(type='output_text',text='Second canonical part'))
            if not ready:answer['status']='in_progress'
            if repaired or ready and case=='receipt_rewritten':
                answer['content']=[dict(type='output_text',text='Canonical rewrite first'),dict(type='output_text',text='Canonical rewrite second')]
        if case=='get_pending_reconnect':
            answer['content'].append(dict(type='output_text',text='Second canonical part'))
            if not (Path(cache_root)/'ready-get').exists():answer['status']='in_progress'
        return httpx2.Response(200, json=dict(object='list', data=[message('user_complete','Synthetic prompt','user'),answer],has_more=False))
    if path.endswith('/artifacts'):
        mark('file_list')
        if case=='slow_list': time.sleep(2)
        data=[dict(id='art_complete', session_id='sess_complete', turn_id='turn_complete', filename='synthetic.txt',path='/workspace/synthetic.txt',size_bytes=9)] if case=='slow_content' else []
        return httpx2.Response(200,json=dict(object='list',data=data,has_more=False))
    if path.endswith('/artifacts/art_complete/content'): return httpx2.Response(200,stream=Content())
    raise AssertionError('Unexpected offline HTTP route')
worker.__file__=str(Path(cache_root)/'modules/agent/worker.py')
worker.create_client=lambda connection:create_client(dict(api_key='offline-only',base_url='https://offline.invalid/v1',organization='',project=''),http_client=httpx2.Client(transport=httpx2.MockTransport(route)))
emit=worker.emit
def traced_emit(kind, **fields):
    if kind=='result' and fields.get('outcome'): mark('result')
    emit(kind,**fields)
worker.emit=traced_emit
worker.main()
