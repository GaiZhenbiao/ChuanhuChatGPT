"""Immutable upload receipts reconcile only proven orphan duplicates."""
from copy import deepcopy
from modules.agent import transcript as t
from agent_fixtures import env

def message(id,text):return {'id':id,'type':'message','role':'user','turn_id':None,'content':[{'type':'input_text','text':text}]}
def document(items,mapping,occurrences=None):
 return t.normalize(items,scope_id='scope',input_mappings=mapping,capture={'items':'complete'},occurrence_ids=occurrences or {})
def mapping(item,source='same-upload',name='notes.txt',size=12):return {'item_id':item,'files':[{'id':source,'name':name,'size':size}]}

def test_nullable_application_occurrence_to_api_id_coalesces_one_upload():
 import hashlib
 m={'wire_sha256':hashlib.sha256(b'wire').hexdigest(),'files':[{'id':'same-upload','name':'notes.txt','size':12}]}
 before=document([message(None,'wire')],[m],{0:'explicit-occurrence'})
 after=document([message('api-user','wire')],[mapping('api-user')])
 merged=t.merge(before,after,authoritative=True)
 assert len(merged['files'])==1 and merged['files'][0]['attachment']['message_ref']==merged['timeline'][0]['id']
 assert t.render_input({'agent_transcript':merged})['turn_files']==[]
 # Repair already-persisted duplicate metadata in memory without losing the
 # original canonical association or inventing a message for an unknown file.
 old=deepcopy(before['files'][0]);old['attachment']={'message_ref':None,'basis':'unresolved'}
 damaged=deepcopy(after);damaged['files'].append(old)
 repaired=t.migrate({'agent_transcript':damaged},scope_id='scope')['agent_transcript']
 assert repaired['files']==merged['files']
 assert len(damaged['files'])==2

def test_distinct_uploads_and_conflicting_receipts_keep_real_unassociated_cards():
 before=document([],[mapping(None,'other-upload')])
 after=document([message('api-user','wire')],[mapping('api-user')])
 assert len(t.merge(before,after,authoritative=True)['files'])==2
 conflict=document([],[mapping(None,name='different.txt')])
 assert len(t.merge(conflict,after,authoritative=True)['files'])==2

def test_same_upload_attached_to_two_existing_messages_stays_ambiguous():
 before=document([message('a','one'),message('b','two')],[mapping('a'),mapping('b'),mapping(None)])
 assert len(t.migrate({'agent_transcript':before},scope_id='scope')['agent_transcript']['files'])==3


def test_same_message_null_turn_receipt_promotes_without_duplicate():
 before=document([message('api-user','wire')],[mapping('api-user')])
 item=message('api-user','wire');item['turn_id']='known-turn'
 after=document([item],[mapping('api-user')])
 merged=t.merge(before,after,authoritative=True)
 assert len(merged['files'])==1 and merged['files'][0]['turn_ref']==merged['timeline'][0]['turn_ref']


def test_later_partial_snapshot_retains_original_user_card_without_orphan(env):
 from agent_fixtures import select
 from test_runtime import message as runtime_message
 m=select(env);m._state.update(session_id='sess_test',turn_id='t3',outcome='completed')
 wire='Synthetic attached input'
 m._remember_input_message(wire,'Clean synthetic question',[dict(input_id='input_shared',name='synthetic.csv',size=17)])
 current=runtime_message('current-user',wire,role='user',turn_id='t3')
 later=runtime_message('later-user','Later plain question',role='user',turn_id='t4')
 m._capture_transcript(dict(items=[current],sync_complete=True))
 original=deepcopy(m._transcript['files'][0])
 m._capture_transcript(dict(items=[later],sync_complete=False))
 assert m._transcript['files']==[original]
 m._capture_transcript(dict(items=[current,later],sync_complete=True))
 assert m._transcript['files']==[original]
 view=t.render_input(m.history_document({}))
 assert sum(len(e['files']) for e in view['timeline'])==1
 assert view['turn_files']==[]


def test_unassociated_input_with_distinct_known_turn_is_preserved():
 item=message('api-user','wire');item['turn_id']='bound-turn'
 bound=document([item],[mapping('api-user')])
 orphan=t.normalize([],scope_id='scope',input_mappings=[{'turn_id':'other-turn','files':[{'id':'same-upload','name':'notes.txt','size':12}]}])
 merged=t.merge(bound,orphan)
 assert len(merged['files'])==2
 assert len(t.render_input({'agent_transcript':merged})['turn_files'])==1
