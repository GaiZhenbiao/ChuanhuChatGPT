"""Production runtime/model/writer/first-frame wiring; synthetic SDK snapshots."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import gradio as gr
import pytest
from agent_fixtures import env, select, send, request
from test_runtime import FakeClient, FakePages, message
from test_ui import panel_app
from modules.agent import runtime, transcript
from modules.agent.message_files import decode_rows


def snapshots(env, monkeypatch):
    folder=Path(tempfile.mkdtemp(prefix='chuanhu-agent-artifacts-'))
    file=folder/'report.txt';file.write_text('offline')
    artifact=dict(id='file',session_id='sess_test',turn_id='t1',name='report.txt',size=7,path=str(file),status='ready')
    items=[message('u','wire-input',role='user'),message('comment','Working',status='completed'),
           dict(id='search',type='web_search_call',turn_id='t1',status='completed',action={'type':'open_page','url':'https://example.com/docs?token=SECRET&q=visible'}),
           dict(id='fn',type='function_call',turn_id='t1',status='completed',call_id='call',name='count_words',arguments={'text':'hello'}),
           dict(id='out',type='function_call_output',turn_id='t1',status='completed',call_id='call',output='words=1'),
           message(None,'No ID answer'),message('final','Done')]
    payload=dict(type='result',session_id='sess_test',turn_id='t1',outcome='completed',sync_complete=True,
                 items=items,item_occurrences={5:'snapshot-receipt-5'},turns=[dict(id='t1',status='completed')],
                 transcript_artifacts=[artifact],capture={'items':'complete','turns':'partial','artifacts':'complete'})
    calls=[]
    def worker(command):
        calls.append(command['action'])
        yield deepcopy(dict(type='result',artifacts=[artifact]) if command['action']=='download' else payload)
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    model=select(env)
    model._remember_input_message('wire-input','question',[dict(input_id='upload',name='input.csv',size=12)])
    send(env,model,'question')
    return model,payload,artifact,calls


def test_paginated_runtime_preserves_nullable_ids_and_occurrence_receipts():
    client=FakeClient();client.saved_items=FakePages([[message(None,'same')],[message(None,'same'),message('a','answer')]])
    saved=runtime.inspect_saved(client,'sess_test','t1')
    assert len(saved['items'])==3 and client.saved_items.visited==[0,1]
    assert saved['capture']['items']=='complete' and 'item_occurrences' not in saved
    # Only explicit application receipts can survive a later partial snapshot.
    saved['item_occurrences']={0:'submission-receipt-A',1:'submission-receipt-B'}
    state=runtime.TurnState(session_id='sess_test');runtime._seed(state,saved)
    first=state.snapshot();state.sync_complete=None;second=state.snapshot()
    assert first['item_occurrences']==second['item_occurrences']
    assert second['capture']['items']=='partial'
    assert saved['items'][0]['id'] is None


def test_export_load_and_first_render_rebuild_tools_inputs_and_turn_files(env,monkeypatch):
    model,payload,artifact,calls=snapshots(env,monkeypatch)
    saved=json.loads((env.history_dir/model.history_file_path).read_text())
    assert saved['history_format']=={'name':'chuanhu','version':2}
    assert len(saved['agent_transcript']['timeline'])==7
    assert 'No ID answer' in str(saved['history'])
    wire=json.dumps(saved);assert str(artifact['path']) not in wire and 'SECRET' not in wire
    assert 'log_reconciled' not in wire and 'state' not in saved
    fresh=select(env,browser='fresh');fresh.load_chat_history(model.history_file_path)
    before=list(calls);app,panel,state=panel_app(fresh)
    try:
        rendered=panel.render_chat(fresh,fresh.chatbot);html=''.join(str(cell or '') for row in rendered for cell in row)
        assert 'agent-history-detail' in html and 'words=1' in html and 'count_words' in html
        assert 'href="https://example.com/docs?' in html and 'q=visible' in html and 'No ID answer' in html
        assert 'input.csv' in html and '本轮文件' in html
        assert decode_rows(rendered,fresh._conversation_id)==fresh.chatbot
        anchors=__import__('modules.agent.ui',fromlist=['message_file_projection']).message_file_projection(fresh).artifact_anchors
        assert 'file' in anchors
        assert calls==before
    finally:app.close()


def test_import_is_inert_rebased_and_cannot_reuse_private_download(env,monkeypatch):
    model,payload,artifact,calls=snapshots(env,monkeypatch)
    saved=json.loads((env.history_dir/model.history_file_path).read_text())
    saved['state']={'session_id':'sess_test'};saved['api_key']='SECRET'
    for file in saved['agent_transcript']['files']:
        file.update(path=str(artifact['path']),availability='ready')
    imported=select(env,browser='imported');before=list(calls)
    imported.upload_chat_history(json.dumps(saved).encode())
    assert not imported._state.get('session_id') and not imported._artifacts and not imported._needs_sync
    assert imported._transcript['scope_id']==imported._conversation_id!=model._conversation_id
    app,panel,state=panel_app(imported)
    try:
        html=''.join(str(cell or '') for row in panel.render_chat(imported,imported.chatbot) for cell in row)
        assert 'report.txt' in html and '仅文件信息' in html and 'agent-history-detail' in html
        assert 'data-file-action="download"' not in html and str(artifact['path']) not in html
        assert calls==before
    finally:app.close()


def test_unknown_format_refuses_load_and_atomic_overwrite(env,monkeypatch):
    model,payload,artifact,calls=snapshots(env,monkeypatch)
    path=env.history_dir/model.history_file_path
    saved=json.loads(path.read_text());saved['history_format']['version']=999
    path.write_text(json.dumps(saved));original=path.read_bytes()
    fresh=select(env,browser='future')
    with pytest.raises(gr.Error):fresh.load_chat_history(model.history_file_path)
    with pytest.raises(transcript.UnsupportedVersion):model.auto_save(model.chatbot)
    assert path.read_bytes()==original


def test_task_projection_keeps_normalized_display_records(env,monkeypatch):
    from modules.agent.tasks import BackgroundTask,TaskRegistry
    model,payload,artifact,calls=snapshots(env,monkeypatch)
    view=model.new_view();task=BackgroundTask(TaskRegistry(),model,lambda:iter(()));model._background_task=task
    task.publish();task.project(view)
    assert view._transcript==model._transcript and view._transcript is not model._transcript


def test_identity_unknown_partial_preserves_canonical_and_requires_recovery(env,monkeypatch):
    model,payload,artifact,calls=snapshots(env,monkeypatch)
    canonical=deepcopy(model._transcript);body=deepcopy(model.chatbot)
    original=(env.history_dir/model.history_file_path).read_bytes()
    with pytest.raises(gr.Error,match='已有记录已保留'):
        model._accept(dict(type='progress',session_id='sess_test',turn_id='t1',outcome='in_progress',
                           items=[message(None,'different unknown message')],capture={'items':'partial'}),model._state['generation'])
    assert model._transcript==canonical and model.chatbot==body and model._needs_sync
    assert (env.history_dir/model.history_file_path).read_bytes()==original
    assert model._state['session_id']=='sess_test'


def test_same_application_receipt_keeps_identity_when_api_id_arrives(env):
    model=select(env);model._state.update(generation='g',session_id='sess_test',turn_id='t1',outcome='in_progress')
    first=dict(type='progress',session_id='sess_test',turn_id='t1',items=[message(None,'partial')],
               capture={'items':'partial'},item_occurrences={0:'exact-message-receipt'})
    model._accept(first,'g');identity=model._transcript['timeline'][0]['id']
    later=deepcopy(first);later['items']=[message('api-message','complete')]
    model._accept(later,'g')
    assert len(model._transcript['timeline'])==1
    assert model._transcript['timeline'][0]['id']==identity and model._transcript['timeline'][0]['source_id']=='api-message'
    fresh=model.new_view();fresh.history_file_path=model.history_file_path;fresh._restore_binding()
    assert fresh._item_receipts==[{'receipt':'exact-message-receipt','source_id':'api-message'}]
    later.pop('item_occurrences');fresh._accept(later,'g')
    assert fresh._transcript['timeline'][0]['id']==identity


def test_pending_intent_save_keeps_first_input_card_without_api_or_path(env):
    model=select(env);model.history=[{'role':'user','content':'question'},{'role':'assistant','content':''}]
    model._display=model.chatbot=[['question','']];model._answer_index=1
    model._active_input_cards=[dict(id='input-receipt',name='upload.csv',size=12)]
    model._transcript_preview=[dict(id='local-receipt-'+role,type='message',role=role,turn_id='local-generation',
        content=[dict(type='input_text' if role=='user' else 'output_text',text='question' if role=='user' else '')]) for role in ('user','assistant')]
    document=model.history_document({'history':model.history,'chatbot':model.chatbot})
    assert document['agent_transcript']['files'][0]['name']=='upload.csv'
    assert document['agent_transcript']['files'][0]['attachment']['basis']=='application_mapping'
    assert all(entry['source_id'] is None and entry['identity']=='application_occurrence' for entry in document['agent_transcript']['timeline'])

@pytest.mark.parametrize('with_tools',[False,True])
def test_turn_file_gap_marker_requires_own_visible_answer(env,monkeypatch,with_tools):
    from modules.agent.transcript_view import project_transcript
    model,payload,artifact,calls=snapshots(env,monkeypatch)
    if not with_tools:
        model._transcript['timeline']=[entry for entry in model._transcript['timeline'] if entry['kind']!='tool']
    projection=project_transcript(model,model.chatbot)
    assert any('class="agent-turn-files-after-answer"' in markup for markup in projection.cell_details.values())
    rendered=__import__('modules.agent.message_files',fromlist=['render_projection']).render_projection(projection,lambda text:text,lambda text:text)
    assert decode_rows(rendered,model._conversation_id)==model.chatbot
    # A file-only response has no preceding answer to cancel its inter-turn gap.
    rows=[[row[0],''] for row in model.chatbot]
    projection=project_transcript(model,rows)
    assert not any('class="agent-turn-files-after-answer"' in markup for markup in projection.cell_details.values())


def test_first_pending_projection_contains_input_card_without_canonical_capture(env):
    from modules.agent.transcript_view import project_transcript
    model=select(env);model.history=[{'role':'user','content':'question'},{'role':'assistant','content':''}]
    model._display=model.chatbot=[['question','']];model._answer_index=1
    model._active_input_cards=[dict(id='input-receipt',name='upload.csv',size=12)]
    model._transcript_preview=[dict(id='local-receipt-'+role,type='message',role=role,turn_id='local-generation',
        content=[dict(type='input_text' if role=='user' else 'output_text',text='question' if role=='user' else '')]) for role in ('user','assistant')]
    assert model._transcript is None
    projection=project_transcript(model,model.chatbot)
    assert projection.user_files[0][0]['name']=='upload.csv'

@pytest.mark.parametrize('file_only',[False,True])
@pytest.mark.parametrize('with_tools',[False,True])
def test_two_turn_file_sections_follow_own_turn_and_preserve_decode(env,file_only,with_tools):
    from modules.agent.transcript_view import project_transcript
    from modules.agent.message_files import render_projection
    model=select(env);model._state.update(session_id='sess_test')
    items=[message('u1','question one','t1',role='user')]
    if not file_only: items.append(message('a1','answer one','t1'))
    if with_tools: items.append(dict(id='tool1',type='function_call',turn_id='t1',call_id='call1',name='first_tool',arguments={}))
    items.extend([message('u2','question two','t2',role='user'),message('a2','answer two','t2')])
    files=[dict(id='f1',turn_id='t1',name='one.txt',session_id='sess_test',status='preparing'),
           dict(id='f2',turn_id='t2',name='two.txt',session_id='sess_test',status='preparing')]
    model._artifacts=files
    import hashlib
    inputs=[{'wire_sha256':hashlib.sha256(text.encode()).hexdigest(),'files':[dict(id=key,name=name,size=12)]}
            for text,key,name in [('question one','in1','input-one.csv'),('question two','in2','input-two.csv')]]
    model._transcript=transcript.normalize(items,scope_id=model._conversation_id,artifacts=files,input_mappings=inputs)
    model.history=[dict(role=item['role'],content=item['content']) for item in items if item['type']=='message']
    rows=[['question one',None if file_only else 'answer one'],['question two','answer two']]
    model.chatbot=model._display=rows
    projection=project_transcript(model,rows)
    first=next(index for index,key in projection.row_anchors.items() if key==projection.artifact_anchors['f1'])
    second=next(index for index,key in projection.row_anchors.items() if key==projection.artifact_anchors['f2'])
    question_two=next(index for index,row in enumerate(projection.rows) if row[0]=='question two')
    assert first<question_two<second
    assert projection.user_files[0][0]['name']=='input-one.csv'
    assert projection.user_files[question_two][0]['name']=='input-two.csv'
    assert ('agent-turn-files-after-answer' in projection.cell_details[(first,1)]) is (not file_only)
    assert 'agent-turn-files-after-answer' in projection.cell_details[(second,1)]
    if with_tools:
        display=render_projection(projection,lambda text:text,lambda text:text)
        tool_row=next(index for index,row in enumerate(display) if 'first_tool' in str(row[1]))
        assert tool_row<first
    rendered=render_projection(projection,lambda text:text,lambda text:text)
    assert decode_rows(rendered,model._conversation_id)==rows
