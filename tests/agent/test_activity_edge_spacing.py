"""Real formatter/projection boundaries, with copy metadata kept out of layout."""
import ast
from copy import deepcopy
from pathlib import Path
import re
import pytest
from modules.agent.message_files import MessageFileProjection, render_projection, decode_rows
from modules.agent.transcript_view import _tool_group


def actual_formatter():
    # Execute the repository's unchanged pure formatter functions without
    # importing unrelated model providers from modules.utils.
    root=Path(__file__).resolve().parents[2]
    tree=ast.parse((root/'modules/utils.py').read_text())
    names={'escape_markdown','clip_rawtext','convert_bot_before_marked'}
    selected=ast.Module(body=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names],type_ignores=[])
    namespace={'re':re};exec(compile(selected,str(root/'modules/utils.py'),'exec'),namespace)
    return namespace['convert_bot_before_marked']


def tool(key='a'):
    entry=dict(id=key,source_id=key,identity='api_id',turn_ref='turn',status='in_progress',kind='tool',source_type='command_execution',details={'command':'pwd'},capture={})
    return {'markup':_tool_group(dict(entries=[entry],id='group-'+key,turn_ref='turn',persist_open=True),scope='synthetic',conversation='edge-spacing')}


def render(segments):
    raw='\n\n'.join(segment['text'] for segment in segments if 'text' in segment)
    rows=[[None,raw]]
    projection=MessageFileProjection(rows=deepcopy(rows),row_anchors={0:'am-'+'1'*64},artifact_anchors={},view_only_rows=set(),conversation_id='edge-spacing',_original_rows=deepcopy(rows))
    projection.cell_segments={(0,1):segments}
    output=render_projection(projection,lambda value:value,actual_formatter())
    assert decode_rows(output,'edge-spacing')==rows
    return output[0][1]


@pytest.mark.parametrize('segments,before,after',[
    ([tool()],False,False),
    ([tool(),{'text':'Body after'}],False,True),
    ([{'text':'Body before'},tool()],True,False),
    ([{'text':'Body before'},tool(),{'text':'Body after'}],True,True),
    ([{'text':' \n'},tool(),{'text':'\n '}],False,False),
])
def test_only_nonempty_body_segments_mark_activity_boundaries(segments,before,after):
    output=render(segments)
    assert ('data-body-before="true"' in output)==before
    assert ('data-body-after="true"' in output)==after
    assert 'raw-message hideM' in output and 'agent-message-anchor' in output


def test_blank_wrappers_do_not_break_contiguous_activity_and_raw_copy_stays_complete():
    output=render([tool('a'),{'text':'\n '},tool('b')])
    assert '<div class="md-message">' not in re.sub(r'<div class="agent-format-receipt hideM" hidden>.*?<div class="md-message"></div></div>', '', output, flags=re.S)
    assert re.search(r'</details></div><div class="agent-history-activity">',output)
    assert 'data-body-before' not in output and 'data-body-after' not in output


def test_formatter_body_can_be_direct_text_without_element_children():
    output=actual_formatter()('Plain body')
    body=output.split('<div class="md-message">',1)[1].split('</div>',1)[0]
    assert body.strip()=='Plain body' and '<' not in body
    assert 'data-body-before="true"' in render([{'text':'Plain body'},tool()])


def test_markup_only_and_hidden_metadata_never_establish_body_gap():
    output=render([{'markup':'<span hidden class="unrelated-anchor">hidden</span>'},tool()])
    assert 'data-body-before' not in output and 'data-body-after' not in output


@pytest.mark.parametrize('before,after',[(False,True),(True,False),(True,True)])
def test_combined_activity_markup_marks_only_actual_first_and_last_body_boundaries(before,after):
    segments=([{'text':'Body before'}] if before else [])+[{'markup':tool('a')['markup']+tool('b')['markup']}]+([{'text':'Body after'}] if after else [])
    output=render(segments)
    tags=re.findall(r'<div class="agent-history-activity"[^>]*>',output)
    assert len(tags)==2
    assert ('data-body-before="true"' in tags[0])==before
    assert 'data-body-after' not in tags[0]
    assert ('data-body-after="true"' in tags[1])==after
    assert 'data-body-before' not in tags[1]
