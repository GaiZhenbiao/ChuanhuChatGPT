"""Render inert transcript activity and files using existing chat/card markup."""
from copy import deepcopy
import html
import json
import math
from modules.agent import transcript
from modules.agent.activity import contiguous_tool_runs, group_span, visible_activity_boundary
from modules.agent.file_icons import file_icon, file_size_label, file_type_label
from modules.agent.message_files import project_message_files, _cloud_rows, _align_rows, _anchor
from modules.presets import i18n


_LABELS = {'function_call': '函数调用', 'function_call_output': '函数结果', 'mcp_call': 'MCP 工具',
           'command_execution': '命令执行', 'web_search_call': '网页工具',
           'computer_use_call': '计算机操作', 'computer_use_approval_request': '网站授权请求',
           'computer_use_approval_request_result': '网站授权结果', 'create_subagent_call': '创建子任务',
           'send_subagent_input_call': '发送子任务输入', 'resume_subagent_call': '继续子任务',
           'wait_for_subagents_call': '等待子任务', 'interrupt_subagent_call': '停止子任务',
           'close_subagent_call': '关闭子任务', 'agent_message': '任务间消息'}


def _links(value):
    urls = []
    def visit(node, key=''):
        if isinstance(node, dict):
            for name, item in node.items(): visit(item, name)
        elif isinstance(node, list):
            for item in node: visit(item, key)
        elif key in ('url', 'urls'):
            url = transcript.safe_url(node)
            if url and url not in urls: urls.append(url)
    visit(value)
    return ''.join('<a href="' + html.escape(url, quote=True) + '" target="_blank" rel="noopener noreferrer">'
                   + html.escape(url) + '</a><br>' for url in urls)


def _mcp_collisions(entries):
    servers={}
    for entry in entries:
        details=entry.get('details',{})
        if entry.get('source_type')=='mcp_call' and isinstance(details.get('name'),str) and isinstance(details.get('server_label'),str):
            servers.setdefault((entry.get('turn_ref'),details['name']),set()).add(details['server_label'])
    return {key for key,labels in servers.items() if len(labels)>1}


_CHEVRON = '<svg class="agent-activity-chevron" aria-hidden="true" focusable="false" width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M4 2 L8 6 L4 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'


def _tool_runs(timeline, scope, *, active_turn=None, clock=None):
    """Contiguous display runs, anchored to canonical non-tool occurrences."""
    result = contiguous_tool_runs(timeline, is_boundary=lambda entry: visible_activity_boundary(
        entry, active=bool(active_turn and entry.get('turn_ref') == active_turn), clock=clock))
    for group in result:
        if group['kind'] == 'tool_group':
            group['id'] = _anchor(['scope',scope,'turn',group['turn_ref'],'layer','group'],'activity-group',group['boundary']) if group['boundary_stable'] else ''
    return result


def _detail_identity(key, turn, scope, layer, conversation, persistent=True):
    return (' data-activity-key="'+html.escape(key,quote=True)+'" data-conversation-id="'+html.escape(conversation,quote=True)
            +'" data-scope-id="'+html.escape(scope,quote=True)+'" data-turn-id="'+html.escape(turn or '',quote=True)
            +'" data-layer="'+layer+'" data-persist-open="'+('true' if persistent else 'false')+'"')


def _confirmed_execution(entry, clock, outputs):
    """Conservative wording evidence, independent of the enclosing turn."""
    kind=entry['source_type'];details=entry.get('details',{})
    phase=(clock or {}).get(entry.get('source_id'),{}).get('phase') or entry.get('activity_phase') or entry.get('status')
    # Native execution items require an explicit completed status. Function
    # outputs have no required status in the SDK; only that result type may
    # omit it when its observed execution phase is explicitly completed.
    valid_status=entry.get('status')=='completed' or kind=='function_call_output' and entry.get('status') is None
    if phase!='completed' or not valid_status or details.get('error'):
        return False
    if kind=='function_call':
        result=(outputs or {}).get((entry.get('turn_ref'),details.get('call_id')))
        return bool(result and result.get('details',{}).get('output') is not None and not result['details'].get('error')
                    and result.get('status') in (None,'completed')
                    and result.get('activity_phase') in (None,'completed'))
    if kind in ('mcp_call','function_call_output'):
        return details.get('output') is not None
    if kind=='command_execution':
        return type(details.get('exit_code')) is int and details['exit_code']==0
    return kind in ('web_search_call','computer_use_call') and entry.get('status')=='completed'


def _group_action(entry):
    kind=entry['source_type']
    if kind=='web_search_call':
        action=entry.get('details',{}).get('action')
        return {'search':'web_search','open_page':'web_search','find_in_page':'web_search'}.get(
            action.get('type') if isinstance(action,dict) else None,'web_search_call')
    return kind if kind in _LABELS else 'other'


def _group_neutral(entry, clock, outputs):
    """Explicit failure, user action or an unsuccessful finished execution."""
    kind=entry['source_type'];details=entry.get('details',{})
    phase=(clock or {}).get(entry.get('source_id'),{}).get('phase') or entry.get('activity_phase') or entry.get('status')
    if details.get('error') or entry.get('status') in ('failed','cancelled','incomplete','requires_action'):
        return True
    if phase in ('failed','cancelled','turn_failed','turn_cancelled','requires_action') or kind=='computer_use_approval_request':
        return True
    if kind=='function_call':
        # Call completion may only finish argument generation. A missing
        # function result still warrants the progressive group title.
        result=(outputs or {}).get((entry.get('turn_ref'),details.get('call_id')))
        return bool(result and (result.get('details',{}).get('error') or result.get('status') in ('failed','cancelled','incomplete')
                    or result.get('activity_phase') in ('failed','cancelled','turn_failed','turn_cancelled')
                    or result.get('details',{}).get('output') is not None and result.get('status') in (None,'completed')
                    and result.get('activity_phase') in (None,'completed')))
    return entry.get('status')=='completed' and not _confirmed_execution(entry,clock,outputs)


def _group_title(entries, clock=None, outputs=None):
    actions=list(dict.fromkeys(_group_action(entry) for entry in entries))
    mode=('past' if all(_confirmed_execution(entry,clock,outputs) for entry in entries) else
          'neutral' if any(_group_neutral(entry,clock,outputs) for entry in entries) else 'progressive')
    if all(action in ('web_search_call','computer_use_approval_request','computer_use_approval_request_result','agent_message','other') for action in actions):
        mode='neutral'  # Preserve truthful type names when no action verb is known.
    prefix='ui.agent_activity.'
    labels=[i18n(prefix+'actions.'+action+'.'+mode) for action in actions]
    if len(labels)==1:joined=labels[0]
    elif len(labels)==2:joined=i18n(prefix+'list_two').format(first=labels[0],last=labels[1])
    else:joined=i18n(prefix+'list_many').format(items=i18n(prefix+'list_separator').join(labels[:-1]),last=labels[-1])
    title=i18n(prefix+mode+'_template').format(actions=joined)
    return title[:1].upper()+title[1:]


def _tool_group(group, *, scope, conversation, **kwargs):
    entries=group['entries'];title=_group_title(entries,kwargs.get('clock'),kwargs.get('outputs'))
    identity=_detail_identity(group['id'],group['turn_ref'],scope,'group',conversation,group['persist_open'])
    children=_activity(entries,scope=scope,conversation=conversation,wrap=False,**kwargs)
    span = group_span(group, clock=kwargs.get('clock'), active=kwargs.get('active', False))
    timer = ''
    if span:
        elapsed = span['elapsed_ms']
        seconds = (('0.0' if elapsed == 0 else '0.1' if elapsed < 100 else f'{math.floor(elapsed / 100) / 10:.1f}')
                   if elapsed < 1000 else math.floor(elapsed / 1000))
        seconds_format = i18n('ui.agent_activity.elapsed_seconds')
        minutes_format = i18n('ui.agent_activity.elapsed_minutes_seconds')
        text = seconds_format.format(seconds=seconds) if elapsed < 60000 else minutes_format.format(minutes=seconds//60, seconds=seconds%60)
        timer = ('<span class="agent-activity-elapsed" data-elapsed-ms="'+str(span['elapsed_ms'])
                 +'" data-running="'+('true' if span['running'] else 'false')
                 +'" data-seconds-format="'+html.escape(seconds_format,quote=True)
                 +'" data-minutes-format="'+html.escape(minutes_format,quote=True)+'">'+html.escape(text)+'</span>')
    return ('<div class="agent-history-activity"><details class="agent-history-detail agent-history-group"'+identity
            +'><summary aria-label="'+html.escape(title,quote=True)+'"><span class="agent-tool-title">'+html.escape(title)
            +'</span>'+timer+_CHEVRON+'</summary><div class="agent-tool-list">'+children+'</div></details></div>')


def _activity_phase(entry, clock=None, outputs=None):
    kind=entry['source_type'];details=entry.get('details',{})
    observed=(clock or {}).get(entry.get('source_id'),{})
    phase=observed.get('phase') or entry.get('activity_phase') or entry.get('status') or 'incomplete'
    if kind=='function_call' and phase=='completed' and not observed and 'activity_phase' not in entry:
        result=(outputs or {}).get((entry.get('turn_ref'),details.get('call_id')))
        phase=('failed' if result.get('details',{}).get('error') else 'completed') if result else 'waiting'
    if kind=='function_call_output' and phase=='incomplete' and not observed:
        phase='failed' if details.get('error') else 'completed'
    phase={'in_progress':'running','requires_action':'waiting'}.get(phase,phase)
    if phase not in ('running','waiting','completed','failed','incomplete','cancelled','turn_cancelled','turn_failed','unknown'):phase='unknown'
    return phase


def _activity(entries, *, clock=None, conversation='', active=False, calls=None, outputs=None, mcp_ambiguous=None, scope='', wrap=True):
    out=[]
    if mcp_ambiguous is None:mcp_ambiguous=_mcp_collisions(entries)
    labels={'running':'进行中','waiting':'等待结果','completed':'已完成','failed':'失败',
            'incomplete':'结果未确认','cancelled':'已停止','turn_cancelled':'本轮已停止','turn_failed':'本轮失败','unknown':'状态未确认'}
    for entry in entries:
        kind=entry['source_type'];details=entry.get('details',{})
        name=details.get('name','')
        if kind=='function_call_output' and calls:
            name=calls.get((entry.get('turn_ref'),details.get('call_id')),'')
        title='公开思考摘要' if entry['kind']=='summary' else _LABELS.get(kind,'工具操作')
        if isinstance(name,str) and name:
            title=name
            if kind=='mcp_call' and (entry.get('turn_ref'),name) in mcp_ambiguous and isinstance(details.get('server_label'),str):
                title+=' · '+details['server_label']
        elif kind=='command_execution' and isinstance(details.get('command'),str) and details['command']:
            title=' '.join(details['command'].split())[:240]
        elif kind=='computer_use_call' and isinstance(details.get('title'),str) and details['title']:
            title=details['title']
        elif kind=='web_search_call':
            action=details.get('action')
            title={'search':'网页搜索','open_page':'打开网页','find_in_page':'页内查找'}.get(action.get('type') if isinstance(action,dict) else None,'网页工具')
        observed=(clock or {}).get(entry.get('source_id'),{})
        phase=_activity_phase(entry,clock,outputs)
        running=bool(active and observed.get('running') and phase in ('running','waiting'))
        status=labels[phase]
        flags=entry.get('capture',{})
        notice=('部分内容未保存' if flags.get('omitted') else '')+(' · 内容已截断' if flags.get('truncated') else '')
        if entry['kind']=='summary':
            public = '\n'.join(part['text'] for part in entry['content'] if part['type']=='summary_text')
            # AgentReasoningItem in the installed SDK exposes no title/name.
            # Preserve its canonical occurrence, but never invent public content.
            thinking = active and phase in ('running', 'waiting')
            title = i18n('ui.agent_activity.thinking_' + ('active' if thinking else 'completed' if phase == 'completed' else 'neutral'))
            if not public.strip():
                if thinking: out.append('<span class="agent-thinking-state">'+html.escape(title)+'</span>')
                if notice: out.append('<small class="agent-activity-notice">'+html.escape(notice)+'</small>')
                continue
            body='<div class="agent-summary-text">'+html.escape(public).replace('\n','<br>')+'</div>'
        else:
            body=(_links(details) if kind=='web_search_call' else '')+'<pre>'+html.escape(json.dumps(dict(type=kind,**details),ensure_ascii=False,indent=2))+'</pre>'
        persistent=entry.get('identity') in ('api_id','application_occurrence')
        identity=_detail_identity(entry['id'] if persistent else '',entry.get('turn_ref'),scope,'summary' if entry['kind']=='summary' else 'tool',conversation,persistent)
        title_class='agent-tool-title'+(' agent-command-preview' if kind=='command_execution' and details.get('command') else '')
        out.append('<details class="agent-history-detail"'+(' open' if running and entry['kind']=='summary' else '')+identity+' data-phase="'+phase+'"><summary aria-label="'+html.escape(title+' · '+status,quote=True)+'">'
                   +'<span class="'+title_class+'">'+html.escape(title)+'</span> '+_CHEVRON+'</summary>'+body
                   +('<small class="agent-activity-notice">'+html.escape(notice)+'</small>' if notice else '')+'</details>')
    body=''.join(out)
    return '<div class="agent-history-activity">'+body+'</div>' if wrap and body else body


def _file_card(file):
    name = file['name'];meta = file_type_label(name) + ' · ' + file_size_label(file['size_bytes']) + ' · 仅文件信息'
    return '<span class="agent-input-card agent-file-card agent-history-file">' + file_icon(name) + '<span class="agent-input-card-text"><span class="agent-input-name">' + html.escape(name) + '</span><span class="agent-input-meta">' + html.escape(meta) + '</span></span></span>'


def project_transcript(model, rows):
    if getattr(model, '_transcript', None) is None and not getattr(model, '_transcript_preview', None): return None
    document = model.history_document({'history': model.history, 'chatbot': rows})
    canonical = document['agent_transcript']
    turns = {turn['id']: turn.get('source_id') for turn in canonical['turns']}
    private = {record['id']: record for record in model._artifacts if isinstance(record.get('id'), str)
               and model._owner and model._state.get('session_id') and record.get('session_id') in (None, model._state['session_id'])}
    def receipt(file):
        record = private.get(file.get('source_id'))
        return record if record and record.get('turn_id') == turns.get(file.get('turn_ref')) else None
    by_id = {file['id']: file for file in canonical['files']}
    view = transcript.render_input(document, resolve_file=lambda key: (receipt(by_id[key]) or {}).get('id'))
    mcp_ambiguous=_mcp_collisions(view['timeline'])
    cloud = [dict(id=entry['id'], role=entry['role'], turn_id=entry.get('turn_ref'),
                  content='\n'.join(part['text'] for part in entry['content'] if part['type'] == 'text'))
             for entry in view['timeline'] if entry['kind'] == 'message']
    projection = project_message_files(rows, cloud, [], session_id=None, conversation_id=model._conversation_id,
                                      input_messages={}, pending_input_files=model._active_input_cards,
                                      current_turn_id=None, answer_row=None)
    source = _cloud_rows(cloud)
    aligned = _align_rows(source, rows, list(range(len(source))), list(range(len(rows))))
    message_rows, turn_rows, turn_last_rows = {}, {}, {}
    for index, row in aligned.items():
        for role in ('user', 'assistant'):
            item = source[index][role]
            if item:
                message_rows[item['id']] = (row, 0 if role == 'user' else 1)
                if item.get('turn_id'): turn_last_rows[item['turn_id']] = row
                if role == 'assistant' and item.get('turn_id'): turn_rows[item['turn_id']] = row
    # A user-only canonical turn owns its empty reply cell, even before the
    # first assistant item exists. Only unique, proven alignments may bind it.
    users_by_turn = {}
    assistant_turns = {item['turn_id'] for item in cloud if item['role'] == 'assistant'}
    for index, source_row in enumerate(source):
        user = source_row['user']
        if user and user.get('turn_id'):
            users_by_turn.setdefault(user['turn_id'], []).append(index)
    for turn, indices in users_by_turn.items():
        if turn in assistant_turns or len(indices) != 1 or source[indices[0]]['assistant'] is not None: continue
        row = aligned.get(indices[0])
        if row is not None and rows[row][1] in (None, ''):
            turn_rows[turn] = row
            turn_last_rows[turn] = row
            projection.row_anchors[row] = _anchor(['conversation', model._conversation_id], 'turn', turn)
    current_source_turn = model._state.get('turn_id') or ('local-' + str(model._state.get('generation')))
    current_ref=next((ref for ref,source_turn in turns.items() if source_turn==current_source_turn),None)
    if current_ref is None and getattr(model, '_transcript_preview', None):
        # The turn acknowledgement can precede its first canonical user item.
        # The generation-bound local preview remains this submission's target.
        preview_turn = 'local-' + str(model._state.get('generation'))
        current_ref = next((ref for ref, source_turn in turns.items() if source_turn == preview_turn), None)
    claimed_turns = {turn for turn, row in turn_rows.items() if row == model._answer_row}
    preview_refs = {ref for ref, source_turn in turns.items()
                    if getattr(model, '_transcript_preview', None) and source_turn == 'local-' + str(model._state.get('generation'))}
    if (current_ref and current_ref not in turn_rows and type(model._answer_row) is int and 0<=model._answer_row<len(rows)
            and claimed_turns.issubset(preview_refs)):
        turn_rows[current_ref]=model._answer_row
        turn_last_rows[current_ref]=model._answer_row
        projection.row_anchors.setdefault(model._answer_row, _anchor(['conversation', model._conversation_id], 'turn', current_ref))
    # The frontend uses this scoped reply receipt instead of selecting the
    # last/empty DOM bubble. It is view metadata and never a transcript item.
    waiting_row = turn_rows.get(current_ref)
    if waiting_row is not None:
        if projection.rows[waiting_row][1] is None: projection.rows[waiting_row][1] = ''
        projection.reply_state = (waiting_row, current_source_turn, False)
    clocks={record.get('item_id'):record for record in getattr(model,'_activity_records',[])
            if isinstance(record,dict) and record.get('turn_id')==model._state.get('turn_id')}
    active=bool((getattr(model,'_running',False) or getattr(model,'_background_busy',False))
                and model._state.get('outcome') not in ('completed','failed','cancelled','not_started'))
    calls={};outputs={};ambiguous_calls=set();ambiguous_outputs=set()
    for entry in view['timeline']:
        if entry['kind']!='tool' or entry['source_type'] not in ('function_call','function_call_output'):continue
        key=(entry.get('turn_ref'),entry.get('details',{}).get('call_id'))
        if not key[1]:continue
        mapping,ambiguous=(calls,ambiguous_calls) if entry['source_type']=='function_call' else (outputs,ambiguous_outputs)
        if key in mapping:ambiguous.add(key)
        else:mapping[key]=entry['details'].get('name','') if entry['source_type']=='function_call' else entry
    for key in ambiguous_calls:calls.pop(key,None);outputs.pop(key,None)
    for key in ambiguous_outputs:outputs.pop(key,None)
    if waiting_row is not None:
        # A sentence is not a turn completion signal. Dots indicate waiting,
        # while visible text streaming and active tools supply their own state.
        tool_active = any(entry['kind'] == 'tool' and entry.get('turn_ref') == current_ref
                          and _activity_phase(entry, clocks, outputs) in ('running', 'waiting')
                          for entry in view['timeline'])
        public_text_streaming = model._state.get('public_text_streaming')
        if type(public_text_streaming) is not bool:
            # Compatibility for saved/older snapshots without segment receipts.
            messages = [entry for entry in view['timeline'] if entry['kind'] == 'message'
                        and entry.get('role') == 'assistant' and entry.get('turn_ref') == current_ref]
            public_text_streaming = bool(messages and messages[-1].get('status') == 'in_progress'
                and any(part.get('text', '').strip() for part in messages[-1].get('content', [])))
        projection.reply_state = (waiting_row, current_source_turn, active and not tool_active and not public_text_streaming)
    projection.cell_details = {}
    projection.cell_segments = {}
    def append(row, column, markup):
        projection.cell_details[(row, column)] = projection.cell_details.get((row, column), '') + markup
    insert_after = {}
    def extra_row(key, after=None):
        index = len(projection.rows)
        projection.rows.append([None, '']);projection._original_rows.append([None, None])
        projection.view_only_rows.add(index);projection.row_anchors[index] = key
        if after is not None: insert_after[index] = after
        return index
    activity = {}
    ordered_segments={}
    for entry in _tool_runs(view['timeline'],view['scope_id'],active_turn=current_ref if active else None,clock=clocks):
        if entry['kind'] in ('tool_group','summary'):
            turn=entry.get('turn_ref')
            options=dict(clock=clocks if turn==current_ref else None,conversation=model._conversation_id,
                         active=active and turn==current_ref,calls=calls,outputs=outputs,mcp_ambiguous=mcp_ambiguous,scope=view['scope_id'])
            markup=_tool_group(entry,**options) if entry['kind']=='tool_group' else _activity([entry],**options)
            if not markup: continue
            row=turn_rows.get(turn)
            if row is None:activity.setdefault(turn,[]).append(markup)
            else:ordered_segments.setdefault(row,[]).append({'markup':markup})
        elif entry['kind'] == 'unsupported':
            row = extra_row(_anchor(['conversation', model._conversation_id], 'unsupported', entry['id']))
            append(row, 1, '<small>此历史包含未支持的内容类型，原始内容未保存。</small>')
        elif entry['kind'] == 'message':
            target = message_rows.get(entry['id'])
            if target is None and entry.get('role')=='assistant' and entry.get('turn_ref') in turn_rows:
                target=(turn_rows[entry['turn_ref']],1)
            if target:
                row, column = target
                if column == 1:
                    ordered_segments.setdefault(row,[]).append({'text':'\n'.join(part['text'] for part in entry['content'] if part['type']=='text')})
                if column == 0 and entry['files']:
                    projection.user_files[row] = [{'id':file['id'], 'name':file['name'], 'size':file['size_bytes']} for file in entry['files']]
                if any(part['type'] != 'text' for part in entry['content']):
                    append(row,column,'<small>图像或其他媒体未包含在此历史记录中。</small>')
    for row,segments in ordered_segments.items():
        if projection.rows[row][1] is None: projection.rows[row][1] = ''
        text='\n\n'.join(segment['text'] for segment in segments if 'text' in segment)
        compact='\n\n'.join(segment['text'] for segment in segments if segment.get('text'))
        if text==(rows[row][1] or ''):
            projection.cell_segments[(row,1)]=segments
        elif compact==(rows[row][1] or ''):
            # Saved grouped messages omit empty occurrences; streaming text may
            # retain their separators. Match either exactly, never reorder tools.
            projection.cell_segments[(row,1)]=[segment for segment in segments
                                              if 'text' not in segment or segment['text']]
        else:
            # Do not rewrite a raw body whose identity/alignment is ambiguous.
            markup=''.join(segment['markup'] for segment in segments if 'markup' in segment)
            if markup:projection.cell_segments[(row,1)]=[{'markup':markup},{'text':rows[row][1] or ''}]
    if waiting_row is not None and not (rows[waiting_row][1] or '').strip():
        # User-only snapshots have no assistant occurrence to create segments.
        # Use the same hidden formatter receipt as tool-only responses instead
        # of rendering an empty Markdown body beside the loader.
        projection.cell_segments.setdefault((waiting_row, 1), [] if not rows[waiting_row][1]
                                             else [{'text': rows[waiting_row][1]}])
    for turn, markup in activity.items():
        row = turn_rows.get(turn)
        if row is None:
            row = extra_row(_anchor(['conversation', model._conversation_id], 'activity', turn or 'unassigned'), turn_last_rows.get(turn))
            if turn: turn_last_rows[turn] = row
        append(row,1,''.join(markup))
    files_by_turn = {}
    projection.artifact_after_anchors = {}
    for file in view['turn_files']: files_by_turn.setdefault(file.get('turn_ref'), []).append(file)
    for turn, files in files_by_turn.items():
        key = _anchor(['conversation', model._conversation_id], 'files', turn or 'unassigned')
        row = extra_row(key, turn_last_rows.get(turn))
        after_answer = turn in turn_rows and bool(rows[turn_rows[turn]][1])
        append(row,1,'<small' + (' class="agent-turn-files-after-answer"' if after_answer else '') + '>' + ('本轮文件' if turn else '未关联消息的文件') + '</small>')
        for file in files:
            record = receipt(file)
            if record and file['kind'] == 'generated':
                projection.artifact_anchors[record['id']] = key
                # Placement below an exact turn reply is view metadata, not an
                # invented per-message API attachment. It also works when the
                # new file-only row has not reached the chat component yet.
                if turn in turn_rows and projection.row_anchors.get(turn_rows[turn]):
                    projection.artifact_after_anchors[record['id']] = projection.row_anchors[turn_rows[turn]]
            else: append(row,1,_file_card(file))
    # Explicit per-message generated-file receipts can attach without guessing.
    for entry in view['timeline']:
        target = message_rows.get(entry['id'])
        for file in entry['files']:
            if file['kind'] != 'generated': continue
            record = receipt(file)
            if record and target and target[1] == 1:
                projection.artifact_anchors[record['id']] = projection.row_anchors[target[0]]
            else:
                row = extra_row(_anchor(['conversation', model._conversation_id], 'file', file['id']))
                append(row,1,_file_card(file))
    # Place explicit turn sections after their own turn, without asserting a
    # per-message attachment. Reindex every row map together; raw decode stays exact.
    if insert_after:
        children = {}
        for child, parent in insert_after.items(): children.setdefault(parent, []).append(child)
        order = []
        def emit(index):
            order.append(index)
            for child in children.get(index, []): emit(child)
        for index in range(len(projection.rows)):
            if index not in insert_after: emit(index)
        positions = {old: new for new, old in enumerate(order)}
        projection.rows = [projection.rows[index] for index in order]
        projection._original_rows = [projection._original_rows[index] for index in order]
        projection.row_anchors = {positions[index]: key for index, key in projection.row_anchors.items()}
        projection.view_only_rows = {positions[index] for index in projection.view_only_rows}
        projection.user_files = {positions[index]: files for index, files in projection.user_files.items()}
        projection.cell_details = {(positions[index], column): markup for (index, column), markup in projection.cell_details.items()}
        projection.cell_segments = {(positions[index], column): segments for (index, column), segments in projection.cell_segments.items()}
        if hasattr(projection, 'reply_state'):
            row, turn, waiting = projection.reply_state
            projection.reply_state = (positions[row], turn, waiting)
    if hasattr(projection, 'reply_state'):
        row, turn, waiting = projection.reply_state
        empty = not (projection.rows[row][1] or '').strip() and not projection.cell_details.get((row, 1)) and not any(
            segment.get('markup') for segment in projection.cell_segments.get((row, 1), []))
        append(row, 1, '<span hidden class="agent-reply-state" data-conversation-id="' + html.escape(model._conversation_id, quote=True)
               + '" data-empty="' + ('true' if empty else 'false') + '" data-turn-id="' + html.escape(turn, quote=True) + '" data-waiting="' + ('true' if waiting else 'false') + '"></span>')
    return projection
