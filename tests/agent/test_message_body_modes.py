"""Interleaved raw/render and exact copy from the actual projection and JS."""
from dataclasses import asdict
import json,re,subprocess
import pytest
from pathlib import Path
from agent_fixtures import env
from test_runtime import message
from test_single_reply_bubble import model,update,command
from test_postprocess_roundtrip import converters,postprocess
from modules.agent.ui import AgentPanel
from modules.agent.message_files import decode_rows
from modules.model_capabilities import AGENT_CAPABILITIES,ModelCapabilities
ROOT=Path(__file__).resolve().parents[2]

def test_all_bodies_switch_in_place_and_copy_preserves_markdown_without_activity(env):
 ns=converters();m=model(env)
 texts=['# Commentary\n    indented &amp; &lt; 中文 😀\n','**Middle**\n- item\n','## Final\n```python\nprint("agent-history-detail is literal body")\n```\n']
 summary=dict(id='reason',type='reasoning',turn_id='t1',status='completed',summary=[dict(type='summary_text',text='SUMMARY_MUST_NOT_COPY')])
 tools=[]
 for key in ('tool','tool2'):
  item=command(key,'t1','completed');item.update(output='TOOL_MUST_NOT_COPY',elapsed_ms=1234,activity_phase='completed',activity_interval=dict(clock_id='a'*32,started_ms=0,ended_ms=1234,sampled_ms=1234));tools.append(item)
 items=[message('u','question',role='user'),summary,dict(message('a',texts[0]),phase='commentary'),tools[0],dict(message('b',texts[1]),phase='commentary'),tools[1],dict(message('c',texts[2]),phase='final_answer')]
 def snapshot(items):
  update(m,items,history_authoritative=True);m._state['outcome']='completed';m._running=False
  rows=AgentPanel(ns['convert_user_before_marked'],ns['convert_bot_before_marked']).render_chat(m,m._display)
  for _ in range(4):
   rows=postprocess(rows,ns);assert decode_rows(rows,m._conversation_id)==m._display
  return dict(conversation=m._conversation_id,rows=rows,cards='',nativeIds=[])
 initial=snapshot(items)
 assert initial['rows'][0][1].count('class="agent-body-segment"')==3
 expected='\n\n'.join(texts);assert m._display[0][1]==expected
 streamed_text='Fourth streamed **body**\n    &amp; exact spaces\n'
 appended=snapshot(items+[message('d',streamed_text)])
 payload=dict(raw=expected,appendedRaw=expected+'\n\n'+streamed_text,agentCaps=asdict(AGENT_CAPABILITIES),normalCaps=asdict(ModelCapabilities()),initial=initial,appended=appended,
  legacyCompound=ns['convert_bot_before_marked']('Legacy first')+'<div class="agent-history-activity"><details><summary>Tool stays</summary></details></div>'+ns['convert_bot_before_marked']('Legacy final'),legacyExpected='Legacy first\n\nLegacy final')
 result=subprocess.run(['node','tests/javascript/message-body-modes.test.cjs'],cwd=ROOT,input=json.dumps(payload),capture_output=True,text=True,timeout=30)
 assert result.returncode==0,result.stdout+result.stderr
 assert 'body modes and exact copy passed' in result.stdout


@pytest.mark.parametrize('texts',[
 ['First\n',' \n\t','Last\n'],
 [' \n\t','First\n',' \n\t'],
 ['First\n',' \n\t',' \n ','Last\n'],
 [' \n\t'],
 ['First\n','','Last\n'],
 ['','',''],
 [' \n\t','',' \n '],
])
def test_missing_or_bad_full_marker_keeps_all_whitespace_body_sources(env,texts):
 ns=converters();m=model(env)
 items=[message('u','question',role='user')]
 for index,text in enumerate(texts):
  items.append(dict(message('body-'+str(index),text),phase='commentary' if index<len(texts)-1 else 'final_answer'))
  if index<len(texts)-1:items.append(command('tool-'+str(index),'t1','completed'))
 update(m,items,history_authoritative=True);m._state['outcome']='completed';m._running=False
 expected='\n\n'.join(text for text in texts if text)
 assert m._display[0][1]==expected
 rows=AgentPanel(ns['convert_user_before_marked'],ns['convert_bot_before_marked']).render_chat(m,m._display)
 for _ in range(4):
  rows=postprocess(rows,ns);assert decode_rows(rows,m._conversation_id)==m._display
 payload=dict(raw=expected,initial=dict(conversation=m._conversation_id,rows=rows,cards='',nativeIds=[]),
  agentCaps=asdict(AGENT_CAPABILITIES),normalCaps=asdict(ModelCapabilities()),
  sourceCount=sum(bool(text) for text in texts),visibleCount=sum(bool(text.strip()) for text in texts),
  whitespaceCount=sum(bool(text) and not text.strip() for text in texts))
 result=subprocess.run(['node','tests/javascript/message-whitespace-copy.test.cjs'],cwd=ROOT,input=json.dumps(payload),capture_output=True,text=True,timeout=30)
 assert result.returncode==0,result.stdout+result.stderr
 assert 'exact whitespace copy passed' in result.stdout
