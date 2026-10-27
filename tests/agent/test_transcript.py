"""Synthetic Agents 3.22.0 fixtures; stdlib-only, no SDK client or project config."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('transcript_under_test', ROOT / 'modules/agent/transcript.py')
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


def message(identity='m1', text='Synthetic answer', role='assistant', turn='turn1', phase='final_answer'):
    return {'id': identity, 'type': 'message', 'turn_id': turn, 'role': role,
            'phase': phase if role == 'assistant' else None, 'status': 'completed',
            'content': [{'type': 'output_text' if role == 'assistant' else 'input_text', 'text': text}]}


def document(items=None, **kwargs):
    snapshot = t.normalize(items if items is not None else [message()], scope_id='synthetic-scope', **kwargs)
    return {'history_format': {'name': 'chuanhu', 'version': 2}, 'model_selection': 'OpenAI Agent',
            'system': 'Synthetic instructions', 'agent_transcript': snapshot}


class TranscriptTests(unittest.TestCase):
    def test_actual_message_shape_phases_and_ids_remain_separate(self):
        d = document([message('u', 'Question', 'user'), message('c', 'Working', phase='commentary'), message('a', 'Answer')])
        entries = d['agent_transcript']['timeline']
        self.assertEqual([e['phase'] for e in entries], [None, 'commentary', 'final_answer'])
        self.assertEqual(len({e['id'] for e in entries}), 3)
        self.assertEqual(len(t.render_input(d)['timeline']), 3)

    def test_duplicate_item_replaces_snapshot_without_duplicate_message(self):
        d = document([message('u', 'Question', 'user'), message('a', 'partial'), message('a', 'final')])
        entries = d['agent_transcript']['timeline']
        self.assertEqual([e['source_id'] for e in entries], ['u', 'a'])
        self.assertEqual(entries[1]['content'][0]['text'], 'final')

    def test_terminal_item_not_regressed_by_late_partial_snapshot(self):
        partial = message(text='late stale delta'); partial['status'] = 'in_progress'
        d = document([message(text='final'), partial])
        self.assertEqual(d['agent_transcript']['timeline'][0]['content'][0]['text'], 'final')
        out = t.merge(document()['agent_transcript'], document([partial])['agent_transcript'])
        self.assertEqual(out['timeline'][0]['status'], 'completed')

    def test_import_gets_fresh_scope_ids_and_keeps_file_references(self):
        d = document(artifacts=[{'id': 'art', 'turn_id': 'turn1', 'path': 'f', 'message_item_id': 'm1'}])
        out = t.loads(t.serialize(d), scope_id='new-import-scope', imported=True)
        before = d['agent_transcript']; after = out['agent_transcript']
        self.assertEqual(after['scope_id'], 'new-import-scope')
        self.assertNotEqual(before['timeline'][0]['id'], after['timeline'][0]['id'])
        self.assertEqual(after['files'][0]['attachment']['message_ref'], after['timeline'][0]['id'])
        self.assertEqual(after['timeline'][0]['file_refs'], [after['files'][0]['id']])
        self.assertIsNone(t.render_input(out)['timeline'][0]['files'][0]['download'])

    def test_identity_stable_across_text_and_status_updates(self):
        a = document([message('a', 'partial')])
        b = document([message('a', 'final')])
        self.assertEqual(a['agent_transcript']['timeline'][0]['id'], b['agent_transcript']['timeline'][0]['id'])

    def test_scope_prevents_id_collision_between_conversations(self):
        a = document()['agent_transcript']['timeline'][0]['id']
        b = t.normalize([message()], scope_id='another')['timeline'][0]['id']
        self.assertNotEqual(a, b)

    def test_null_api_user_id_keeps_identical_occurrences(self):
        d = document([message(None, 'same', 'user'), message(None, 'same', 'user')])
        entries = d['agent_transcript']['timeline']
        self.assertEqual(len(entries), 2)
        self.assertNotEqual(entries[0]['id'], entries[1]['id'])

    def test_conflicting_source_types_refused(self):
        with self.assertRaises(t.TranscriptError):
            document([message(), {'id': 'm1', 'type': 'web_search_call', 'turn_id': 'turn1'}])

    def test_input_file_attaches_before_first_render_and_wire_is_replaced(self):
        d = document([message('u', 'wire with manifest', 'user')], input_mappings=[
            {'item_id': 'u', 'text': 'Clean question', 'files': [{'id': 'input1', 'name': 'report.csv', 'size': 17}]}])
        rendered = t.render_input(d)
        self.assertEqual(rendered['timeline'][0]['content'], [{'type': 'text', 'text': 'Clean question'}])
        self.assertEqual(rendered['timeline'][0]['files'][0]['name'], 'report.csv')
        self.assertEqual(rendered['timeline'][0]['files'][0]['download'], None)
        self.assertEqual(rendered['turn_files'], [])

    def test_legacy_input_digest_accepted_only_for_unambiguous_message(self):
        digest = hashlib.sha256(b'same').hexdigest()
        mapping = {'wire_sha256': digest, 'text': 'clean', 'files': [{'id': 'in1', 'name': 'f.txt'}]}
        a = document([message('u', 'same', 'user')], input_mappings=[mapping])
        self.assertEqual(len(t.render_input(a)['timeline'][0]['files']), 1)
        b = document([message('u1', 'same', 'user'), message('u2', 'same', 'user')], input_mappings=[mapping])
        self.assertTrue(all(not e['files'] for e in t.render_input(b)['timeline']))
        self.assertEqual(t.render_input(b)['turn_files'][0]['attachment']['basis'], 'unresolved')

    def test_api_artifact_turn_only_does_not_invent_message_ownership(self):
        d = document(artifacts=[{'id': 'art1', 'session_id': 'session1', 'environment_id': 'env1',
                                'turn_id': 'turn1', 'path': '/workspace/outputs/report.pdf', 'size_bytes': 20, 'created_at': 1}])
        r = t.render_input(d)
        self.assertEqual(r['timeline'][0]['files'], [])
        self.assertEqual(r['turn_files'][0]['name'], 'report.pdf')
        self.assertEqual(r['turn_files'][0]['attachment']['basis'], 'turn_only')
        self.assertNotIn('path', r['turn_files'][0])
        self.assertNotIn('session_id', r['turn_files'][0])

    def test_explicit_artifact_message_receipt_and_same_name_versions(self):
        d = document([message('a1'), message('a2', turn='turn2')], artifacts=[
            {'id': 'art1', 'turn_id': 'turn1', 'path': '/workspace/outputs/report.pdf', 'message_item_id': 'a1'},
            {'id': 'art2', 'turn_id': 'turn2', 'path': '/workspace/outputs/report.pdf', 'message_item_id': 'a2'}])
        r = t.render_input(d)
        self.assertEqual([len(e['files']) for e in r['timeline']], [1, 1])
        self.assertNotEqual(r['timeline'][0]['files'][0]['id'], r['timeline'][1]['files'][0]['id'])

    def test_artifact_wrong_turn_cannot_attach_to_message(self):
        d = document(artifacts=[{'id': 'a', 'turn_id': 'turn-other', 'message_item_id': 'm1', 'path': 'f'}])
        r = t.render_input(d)
        self.assertEqual(r['timeline'][0]['files'], [])
        self.assertEqual(len(r['turn_files']), 1)

    def test_foreign_session_artifact_filtered_when_trusted_session_supplied(self):
        d = document(artifacts=[{'id': 'a', 'session_id': 'foreign', 'turn_id': 'turn1', 'path': 'f'}], session_id='local')
        self.assertEqual(d['agent_transcript']['files'], [])

    def test_file_only_turn_is_visible_without_synthetic_assistant_message(self):
        d = document([], artifacts=[{'id': 'a', 'turn_id': 'turn1', 'path': 'report.txt'}])
        r = t.render_input(d)
        self.assertEqual(r['timeline'], [])
        self.assertEqual(len(r['turn_files']), 1)

    def test_tools_call_and_result_preserve_join_key_and_failed_status(self):
        items = [{'id': 'out', 'type': 'function_call_output', 'turn_id': 'turn1', 'call_id': 'call1', 'status': 'failed', 'error': 'synthetic error'},
                 {'id': 'call', 'type': 'function_call', 'turn_id': 'turn1', 'call_id': 'call1', 'name': 'test', 'status': 'completed', 'arguments': {'q': 'x'}}]
        d = document(items, turns=[{'id': 'turn1', 'agent_id': 'root', 'status': 'completed', 'created_at': 1, 'started_at': 2, 'completed_at': 3}])
        r = t.render_input(d)
        self.assertEqual([e['details']['call_id'] for e in r['timeline']], ['call1', 'call1'])
        self.assertEqual(r['timeline'][0]['status'], 'failed')
        self.assertEqual(r['turns'][0]['status'], 'completed')

    def test_actual_web_actions_and_no_invented_search_results(self):
        actions = [{'type': 'search', 'queries': ['one', 'two']}, {'type': 'open_page', 'url': 'https://example.test/a?q=term'},
                   {'type': 'find_in_page', 'url': 'https://example.test/a', 'pattern': 'needle'}, None]
        items = [{'id': str(i), 'type': 'web_search_call', 'turn_id': 'turn1', 'status': 'completed', 'action': action} for i, action in enumerate(actions)]
        d = document(items)
        self.assertEqual([e['details']['action'] for e in t.render_input(d)['timeline']], actions)
        self.assertNotIn('sources', t.serialize(d))

    def test_browser_shape_does_not_claim_url_or_include_screenshot_data(self):
        d = document([{'id': 'b', 'turn_id': 'turn1', 'type': 'computer_use_call', 'status': 'completed', 'title': 'Read page',
                       'output': {'type': 'computer_screenshot', 'image_url': 'data:image/jpeg;base64,SYNTHETIC'}}])
        wire = t.serialize(d)
        self.assertNotIn('SYNTHETIC', wire)
        self.assertNotIn('image_url', wire)
        self.assertIn('screenshot_available_in_source', wire)

    def test_auth_history_has_no_live_form_request_or_secret_values(self):
        items = [{'id': 'req', 'turn_id': 'turn1', 'type': 'computer_use_approval_request', 'request_id': 'do-not-replay',
                  'request': {'fields': [{'id': 'password', 'value': 'never-store'}]}},
                 {'id': 'res', 'turn_id': 'turn1', 'type': 'computer_use_approval_request_result', 'request_id': 'do-not-replay',
                  'response': {'action': 'submit', 'fields': [{'value': 'never-store'}]}}]
        wire = t.serialize(document(items))
        self.assertNotIn('never-store', wire)
        self.assertNotIn('do-not-replay', wire)

    def test_reasoning_and_encrypted_content_are_excluded(self):
        d = document([{'id': 'r', 'type': 'reasoning', 'summary': [{'text': 'hidden-test'}]},
                       {'id': 'mcp', 'type': 'mcp_call', 'turn_id': 'turn1', 'output': {'encrypted_content': 'hidden-test', 'ok': 'display'}}])
        self.assertNotIn('hidden-test', t.serialize(d))
        self.assertEqual(len(d['agent_transcript']['timeline']), 1)

    def test_unknown_item_placeholder_not_raw_blob(self):
        d = document([{'id': 'future', 'turn_id': 'turn1', 'type': 'future-tool', 'output': 'unverified-content'}])
        self.assertEqual(d['agent_transcript']['timeline'][0]['kind'], 'unsupported')
        self.assertNotIn('unverified-content', t.serialize(d))

    def test_tool_secrets_are_scrubbed_recursively(self):
        item = {'id': 'mcp', 'turn_id': 'turn1', 'type': 'mcp_call', 'status': 'completed',
                'arguments': {'api_key': 'synthetic-secret', 'nested': {'password': 'synthetic-password'}},
                'output': 'Bearer synthetic-bearer\nplain synthetic-secret\nhttps://user:pass@example.test/a?token=url-secret&q=term'}
        wire = t.serialize(document([item], secrets=['synthetic-secret']))
        for value in ('synthetic-secret', 'synthetic-password', 'synthetic-bearer', 'url-secret', 'user:pass'):
            self.assertNotIn(value, wire)
        self.assertIn('q=term', wire)

    def test_size_and_depth_flags(self):
        item = {'id': 'cmd', 'type': 'command_execution', 'turn_id': 'turn1', 'command': 'test', 'output': 'x' * 40000}
        d = document([item])
        self.assertTrue(d['agent_transcript']['timeline'][0]['capture']['truncated'])
        self.assertLess(len(json.dumps(d['agent_transcript']['timeline'][0]['details']).encode()), t.MAX_TOOL_BYTES)
        deep = {'x': {'x': {'x': {'x': {'x': {'x': {'x': {'x': {'x': {'x': 'bottom'}}}}}}}}}}
        _, flags = t.sanitize(deep)
        self.assertTrue(flags['truncated'])

    def test_capture_loss_and_turn_metadata_survive_roundtrip(self):
        d = document([{'id': 'cmd', 'type': 'command_execution', 'turn_id': 'turn1', 'output': 'x' * 40000}],
                     turns=[{'id': 'turn1', 'status': 'failed', 'agent_id': 'root', 'created_at': 1,
                             'error': {'message': 'synthetic failed'}, 'usage': {'input_tokens': 3, 'output_tokens': 4, 'total_tokens': 7}}])
        a = t.loads(t.serialize(d), scope_id='s')
        self.assertTrue(a['agent_transcript']['timeline'][0]['capture']['truncated'])
        self.assertEqual(a['agent_transcript']['turns'][0]['agent_source_id'], 'root')
        self.assertEqual(a['agent_transcript']['turns'][0]['usage']['total_tokens'], 7)
        self.assertEqual(a['agent_transcript']['turns'][0]['error']['message'], 'synthetic failed')
        self.assertIn('output', a['agent_transcript']['timeline'][0]['details'])

    def test_incremental_snapshot_merge_preserves_earlier_turns(self):
        a = document([message('a1', text='first')])['agent_transcript']
        b = document([message('a2', text='second', turn='turn2')])['agent_transcript']
        out = t.merge(a, b)
        self.assertEqual([e['content'][0]['text'] for e in out['timeline']], ['first', 'second'])
        c = document([message('a2', text='second final', turn='turn2')])['agent_transcript']
        out = t.merge(out, c)
        self.assertEqual(len(out['timeline']), 2)
        self.assertEqual(out['timeline'][-1]['content'][0]['text'], 'second final')

    def test_authoritative_replace_requires_complete_marker_and_same_scope(self):
        a = document()['agent_transcript']
        b = document([message('new')])['agent_transcript']
        with self.assertRaises(t.TranscriptError): t.merge(a, b, authoritative=True)
        b['capture']['items'] = 'complete'
        self.assertEqual(len(t.merge(a, b, authoritative=True)['timeline']), 1)
        b['scope_id'] = 'foreign'
        with self.assertRaises(t.TranscriptError): t.merge(a, b)

    def test_generated_file_id_stable_when_explicit_attachment_arrives(self):
        a = document(artifacts=[{'id': 'art', 'turn_id': 'turn1', 'path': 'f'}])['agent_transcript']
        b = document(artifacts=[{'id': 'art', 'turn_id': 'turn1', 'path': 'f', 'message_item_id': 'm1'}])['agent_transcript']
        self.assertEqual(a['files'][0]['id'], b['files'][0]['id'])
        merged = t.merge(a, b)
        self.assertEqual(len(merged['files']), 1)
        self.assertEqual(merged['files'][0]['attachment']['message_ref'], merged['timeline'][0]['id'])

    def test_text_only_merge_keeps_captured_file_attachment(self):
        a = document(artifacts=[{'id': 'art', 'turn_id': 'turn1', 'path': 'f', 'message_item_id': 'm1'}])['agent_transcript']
        b = document([message(text='extended text')])['agent_transcript']
        out = t.merge(a, b)
        self.assertEqual(out['timeline'][0]['file_refs'], [out['files'][0]['id']])

    def test_complete_items_snapshot_does_not_claim_complete_artifacts(self):
        a = document(artifacts=[{'id': 'art', 'turn_id': 'turn1', 'path': 'f', 'message_item_id': 'm1'}])['agent_transcript']
        b = document([message(text='new snapshot')], capture={'items': 'complete'})['agent_transcript']
        out = t.merge(a, b, authoritative=True)
        self.assertEqual(len(out['files']), 1)
        self.assertEqual(out['timeline'][0]['file_refs'], [out['files'][0]['id']])

    def test_malformed_capture_and_attachment_refused(self):
        d = document(); d['agent_transcript']['capture'] = 'invalid'
        with self.assertRaises(t.TranscriptError): t.render_input(d)
        d = document(artifacts=[{'id': 'art', 'turn_id': 'turn1', 'path': 'f'}])
        d['agent_transcript']['files'][0]['attachment'] = 'invalid'
        with self.assertRaises(t.TranscriptError): t.render_input(d)

    def test_history_operations_never_log_replayed_answer(self):
        with patch('logging.info', side_effect=AssertionError('History must not replay logs')):
            d = document()
            loaded = t.loads(t.serialize(d), scope_id='s')
            t.render_input(loaded)

    def test_known_fields_survive_unknown_future_fields_without_raw_storage(self):
        d = document()
        d['future'] = {'password': 'future-secret'}
        d['agent_transcript']['timeline'][0]['future'] = {'encrypted_content': 'future-hidden'}
        out = t.loads(json.dumps(d), scope_id='s')
        self.assertEqual(out['history'][0]['content'], 'Synthetic answer')
        self.assertNotIn('future-secret', t.serialize(out))
        self.assertNotIn('future-hidden', t.serialize(out))

    def test_imported_tool_url_is_revalidated_and_unknown_authority_removed(self):
        d = document([{'id': 'web', 'type': 'web_search_call', 'turn_id': 'turn1', 'action': {'type': 'open_page', 'url': 'https://example.test'}}])
        details = d['agent_transcript']['timeline'][0]['details']
        details.update(path='/etc/passwd', ready=True)
        details['action']['url'] = 'javascript:alert(1)'
        out = t.loads(json.dumps(d), scope_id='s')
        e = t.render_input(out)['timeline'][0]
        self.assertIsNone(e['details']['action']['url'])
        self.assertNotIn('path', e['details'])
        self.assertTrue(e['capture']['omitted'])

    def test_nested_typed_reasoning_and_identifier_secrets_not_stored(self):
        d = document([{'id': 'synthetic-secret', 'type': 'mcp_call', 'turn_id': 'turn1',
                       'output': {'nested': {'type': 'reasoning', 'text': 'hidden-text'}}}], secrets=['synthetic-secret'])
        wire = t.serialize(d)
        self.assertNotIn('synthetic-secret', wire)
        self.assertNotIn('hidden-text', wire)

    def test_partial_collection_defaults_and_screenshot_loss_are_explicit(self):
        d = document([{'id': 'b', 'type': 'computer_use_call', 'turn_id': 'turn1', 'output': {'type': 'computer_screenshot', 'image_url': 'data:synthetic'}}],
                     artifacts=[{'id': 'a', 'turn_id': 'turn1', 'path': 'f'}])
        self.assertEqual(d['agent_transcript']['capture']['artifacts'], 'partial')
        self.assertTrue(t.loads(t.serialize(d), scope_id='s')['agent_transcript']['timeline'][0]['capture']['omitted'])

    def test_oversized_message_is_refused_not_silently_truncated(self):
        with patch.object(t, 'MAX_TEXT_BYTES', 8):
            with self.assertRaises(t.TranscriptError):
                document([message(text='x' * 9)])

    def test_image_is_visible_placeholder_without_remote_fetch(self):
        m = message(role='user')
        m['content'] = [{'type': 'input_image', 'image_url': 'https://private.test/image'}]
        d = document([m])
        self.assertNotIn('private.test', t.serialize(d))
        self.assertEqual(t.render_input(d)['timeline'][0]['content'][0]['type'], 'media_placeholder')

    def test_legacy_strings_and_unpaired_user_migrate(self):
        old = {'system': 's', 'history': ['u', 'a', 'u2'], 'chatbot': [['u', 'a'], ['u2', None]]}
        d = t.migrate(old, scope_id='legacy-scope')
        self.assertEqual(d['history'], [{'role': 'user', 'content': 'u'}, {'role': 'assistant', 'content': 'a'}, {'role': 'user', 'content': 'u2'}])
        self.assertEqual(d['chatbot'], old['chatbot'])
        self.assertEqual(old['history'], ['u', 'a', 'u2'])

    def test_legacy_role_content_and_file_cells_never_read_paths(self):
        old = {'history': [{'role': 'user', 'content': 'u'}, {'role': 'assistant', 'content': 'a'}],
               'chatbot': [['u', 'a'], [None, ['/etc/passwd', 'private']]]}
        with patch('builtins.open', side_effect=AssertionError('No file access allowed')):
            d = t.migrate(old, scope_id='legacy-scope')
            rendered = t.render_input(d)
        self.assertEqual(rendered['turn_files'][0]['name'], 'passwd')
        self.assertNotIn('/etc/passwd', t.serialize(d))

    def test_empty_history(self):
        d = t.migrate({'history': [], 'chatbot': []}, scope_id='empty')
        self.assertEqual(t.render_input(d)['timeline'], [])

    def test_transcript_wins_over_stale_compatibility_fields(self):
        d = document()
        d.update(history=[{'role': 'assistant', 'content': 'stale'}], chatbot=[[None, 'stale']])
        loaded = t.loads(json.dumps(d), scope_id='ignored')
        self.assertEqual(loaded['history'][0]['content'], 'Synthetic answer')

    def test_roundtrip_preserves_messages_file_refs_tools_and_ids(self):
        items = [message('u', 'Question', 'user'), {'id': 'cmd', 'type': 'command_execution', 'turn_id': 'turn1', 'status': 'completed', 'command': 'echo test', 'output': 'test'}, message('a')]
        d = document(items, input_mappings=[{'item_id': 'u', 'files': [{'id': 'in', 'name': 'in.csv'}]}],
                     artifacts=[{'id': 'out', 'turn_id': 'turn1', 'path': 'out.csv', 'message_item_id': 'a'}])
        a = t.loads(t.serialize(d), scope_id='ignored')
        b = t.loads(t.serialize(a), scope_id='ignored')
        self.assertEqual(a, b)
        self.assertEqual([e['id'] for e in a['agent_transcript']['timeline']], [e['id'] for e in d['agent_transcript']['timeline']])
        self.assertEqual([len(e['files']) for e in t.render_input(a)['timeline']], [1, 0, 1])

    def test_future_major_refused_without_mutating_original(self):
        d = document(); d['history_format']['version'] = 99
        original = deepcopy(d)
        with self.assertRaises(t.UnsupportedVersion):
            t.serialize(d)
        self.assertEqual(d, original)

    def test_future_transcript_version_refused(self):
        d = document(); d['agent_transcript']['version'] = 99
        with self.assertRaises(t.UnsupportedVersion):
            t.render_input(d)

    def test_imported_authority_path_ready_are_inert(self):
        d = document(artifacts=[{'id': 'artifact', 'turn_id': 'turn1', 'path': 'f'}])
        d.update(owner='victim', session_id='victim-session', connection_ref='victim-key')
        d['agent_transcript']['files'][0].update(path='/etc/passwd', availability='ready', download='file:///etc/passwd')
        loaded = t.loads(json.dumps(d), scope_id='new')
        wire = t.serialize(loaded)
        for value in ('victim-session', 'victim-key', '/etc/passwd'):
            self.assertNotIn(value, wire)
        self.assertIsNone(t.render_input(loaded)['turn_files'][0]['download'])

    def test_trusted_resolver_receives_local_ids_not_json_source_or_path(self):
        d = document(artifacts=[{'id': 'source-artifact', 'turn_id': 'turn1', 'path': 'f'}])
        seen = []
        def resolver(local):
            seen.append(local)
            return 'trusted-download-handle'
        r = t.render_input(d, resolve_file=resolver)
        self.assertEqual(seen, [d['agent_transcript']['files'][0]['id']])
        self.assertEqual(r['turn_files'][0]['download'], 'trusted-download-handle')

    def test_dangling_turn_message_and_file_refs_refused(self):
        d = document()
        d['agent_transcript']['timeline'][0]['turn_ref'] = 'unknown'
        with self.assertRaises(t.TranscriptError): t.render_input(d)
        d = document(); d['agent_transcript']['timeline'][0]['file_refs'] = ['unknown']
        with self.assertRaises(t.TranscriptError): t.render_input(d)

    def test_duplicate_local_ids_refused(self):
        d = document()
        d['agent_transcript']['timeline'].append(deepcopy(d['agent_transcript']['timeline'][0]))
        with self.assertRaises(t.TranscriptError): t.render_input(d)

    def test_safe_urls_deny_local_script_and_strip_auth(self):
        for url in ('file:///etc/passwd', 'javascript:alert(1)', 'data:text/html,x', 'https://example.test/\n'):
            self.assertIsNone(t.safe_url(url))
        self.assertEqual(t.safe_url('https://user:pass@example.test/a?token=x&q=hello#secret'), 'https://example.test/a?token=%5BREDACTED%5D&q=hello')

    def test_capture_never_claims_subagent_collection(self):
        d = document(capture={'items': 'complete', 'subagents': 'complete'})
        self.assertEqual(d['agent_transcript']['capture']['items'], 'complete')
        self.assertEqual(d['agent_transcript']['capture']['subagents'], 'not_collected')

    def test_more_than_one_api_page_no_silent_drop(self):
        d = document([message(str(i), text=str(i)) for i in range(205)])
        self.assertEqual(len(t.render_input(d)['timeline']), 205)

    def test_invalid_json_and_nan_document(self):
        with self.assertRaises(t.TranscriptError): t.loads('{bad', scope_id='s')
        d = document(); d['temperature'] = float('nan')
        self.assertNotIn('NaN', t.serialize(d))

    def test_document_size_limit(self):
        with patch.object(t, 'MAX_DOCUMENT_BYTES', 10):
            with self.assertRaises(t.TranscriptError): t.serialize(document())


class AuditRegressions(unittest.TestCase):
    def test_secret_names_are_cleaned_in_nested_args_output_and_error(self):
        secret = 'PRIVATE-NEEDLE'
        item = {'id': 'mcp', 'type': 'mcp_call', 'turn_id': 'turn1', 'status': 'completed',
                'arguments': {'outer': {'abc_' + secret: 'safe-argument'}},
                'output': [{secret: {'nested_' + secret: 'safe-output'}}],
                'error': {'outer': {'error_' + secret: 'safe-error'}}}
        d = document([item], secrets=[secret])
        wire = t.serialize(d, secrets=[secret])
        self.assertNotIn(secret, wire)
        for value in ('safe-argument', 'safe-output', 'safe-error'):
            self.assertIn(value, wire)
        self.assertTrue(d['agent_transcript']['timeline'][0]['capture']['redacted'])

    def test_sanitized_key_collisions_keep_all_distinct_values(self):
        value = {'abc_FIRST': 'one', 'abc_SECOND': 'two', 'abc_[REDACTED]': 'three'}
        safe, flags = t.sanitize(value, secrets=['FIRST', 'SECOND'])
        self.assertEqual(list(safe.values()), ['one', 'two', 'three'])
        self.assertEqual(len(safe), 3)
        self.assertEqual(list(safe), ['abc_[REDACTED]', 'abc_[REDACTED]#2', 'abc_[REDACTED]#3'])
        self.assertTrue(flags['redacted'])

    def test_truncated_key_collisions_keep_all_values(self):
        safe, flags = t.sanitize({'x' * 150 + 'a': 'one', 'x' * 150 + 'b': 'two'})
        self.assertEqual(list(safe.values()), ['one', 'two'])
        self.assertTrue(flags['truncated'])

    def test_secret_in_url_parameter_name_not_exported(self):
        secret = 'PRIVATE-NEEDLE'
        d = document([{'id': 'web', 'type': 'web_search_call', 'turn_id': 'turn1', 'status': 'completed',
                       'action': {'type': 'open_page', 'url': 'https://example.test/?abc_' + secret + '=safe&q=term'}}], secrets=[secret])
        wire = t.serialize(d, secrets=[secret])
        self.assertNotIn(secret, wire)
        self.assertIn('q=term', wire)

    def test_imported_nested_key_secret_is_cleaned_again(self):
        d = document([{'id': 'mcp', 'type': 'mcp_call', 'turn_id': 'turn1', 'output': {}}])
        d['agent_transcript']['timeline'][0]['details']['output'] = {'PRIVATE-NEEDLE': 'safe'}
        out = t.loads(json.dumps(d), scope_id='s', secrets=['PRIVATE-NEEDLE'])
        self.assertNotIn('PRIVATE-NEEDLE', t.serialize(out))

    def test_identity_unknown_partial_snapshots_cannot_silently_overwrite(self):
        first = document([message(None, 'first', 'user')])['agent_transcript']
        second = document([message(None, 'second', 'user')])['agent_transcript']
        before = deepcopy(first)
        with self.assertRaisesRegex(t.TranscriptError, 'identity-unknown'):
            t.merge(first, second)
        self.assertEqual(first, before)
        self.assertEqual(t.legacy_projection(first)[0][0]['content'], 'first')

    def test_unknown_occurrences_rejected_even_for_an_asserted_complete_replace(self):
        first = document([message(None, 'first', 'user')])['agent_transcript']
        second = document([message(None, 'second', 'user')], capture={'items': 'complete'})['agent_transcript']
        with self.assertRaises(t.TranscriptError): t.merge(first, second, authoritative=True)

    def test_receipt_occurrences_merge_separate_partial_pages(self):
        first = document([message(None, 'first', 'user')], occurrence_ids={0: 'receipt-first'})['agent_transcript']
        second = document([message(None, 'second', 'user')], occurrence_ids={0: 'receipt-second'})['agent_transcript']
        out = t.merge(first, second)
        self.assertEqual([e['content'][0]['text'] for e in out['timeline']], ['first', 'second'])

    def test_repeated_text_with_distinct_receipts_not_deduplicated(self):
        a = document([message(None, 'same', 'user')], occurrence_ids={0: 'first'})['agent_transcript']
        b = document([message(None, 'same', 'user')], occurrence_ids={0: 'second'})['agent_transcript']
        self.assertEqual(len(t.merge(a, b)['timeline']), 2)

    def test_same_receipt_updates_same_message_without_content_identity(self):
        a = document([message(None, 'before', 'user')], occurrence_ids={0: 'receipt'})['agent_transcript']
        b = document([message(None, 'after', 'user')], occurrence_ids={0: 'receipt'})['agent_transcript']
        out = t.merge(a, b)
        self.assertEqual(len(out['timeline']), 1)
        self.assertEqual(out['timeline'][0]['id'], a['timeline'][0]['id'])
        self.assertEqual(out['timeline'][0]['content'][0]['text'], 'after')

    def test_receipt_identity_survives_append_reorder_and_null_to_api_id(self):
        a = document([message(None, 'one', 'user')], occurrence_ids={0: 'one'})['agent_transcript']
        b = document([message(None, 'one', 'user'), message(None, 'two', 'user')], occurrence_ids={0: 'one', 1: 'two'})['agent_transcript']
        c = document([message(None, 'two', 'user'), message('api-one', 'one', 'user')], occurrence_ids={0: 'two', 1: 'one'}, capture={'items': 'complete'})['agent_transcript']
        self.assertEqual(a['timeline'][0]['id'], b['timeline'][0]['id'])
        self.assertEqual(a['timeline'][0]['id'], c['timeline'][1]['id'])
        out = t.merge(t.merge(a, b), c, authoritative=True)
        self.assertEqual([e['content'][0]['text'] for e in out['timeline']], ['two', 'one'])
        self.assertEqual(out['timeline'][1]['source_id'], 'api-one')

    def test_different_turn_receipts_do_not_collide(self):
        a = document([message(None, 'same', 'user', turn='turn1')], occurrence_ids={0: 'turn1-receipt'})['agent_transcript']
        b = document([message(None, 'same', 'user', turn='turn2')], occurrence_ids={0: 'turn2-receipt'})['agent_transcript']
        out = t.merge(a, b)
        self.assertEqual(len(out['timeline']), 2)
        self.assertNotEqual(out['timeline'][0]['turn_ref'], out['timeline'][1]['turn_ref'])

    def test_invalid_occurrence_receipts_refused(self):
        for receipts in (['receipt'], {-1: 'receipt'}, {1: 'receipt'}, {0: None}, {0: 'sk-secret'}):
            with self.subTest(receipts=receipts):
                with self.assertRaises(t.TranscriptError): document([message(None, role='user')], occurrence_ids=receipts)

    def test_final_json_encoding_respects_budget_with_quotes_backslashes_unicode(self):
        for payload in ('"' * 5000, '\\' * 5000, '\n' * 5000, '汉🙂"\\' * 5000):
            for budget in (2, 16, 256, 512, 1024):
                with self.subTest(payload=payload[:8], budget=budget):
                    safe, flags = t.sanitize({'a': payload}, max_bytes=budget)
                    self.assertLessEqual(len(json.dumps(safe, ensure_ascii=False).encode()), budget)
                    self.assertTrue(flags['truncated'])

    def test_preview_remains_valid_json_and_invalid_budgets_refused(self):
        safe, flags = t.sanitize({'a': '"' * 5000}, max_bytes=512)
        self.assertEqual(json.loads(json.dumps(safe)), safe)
        self.assertTrue(flags['truncated'])
        for budget in (0, 1, -1, True, 3.5):
            with self.assertRaises(t.TranscriptError): t.sanitize({}, max_bytes=budget)

    def test_turn_error_final_encoding_and_flags_survive_serialization(self):
        d = document(turns=[{'id': 'turn1', 'status': 'failed', 'error': {'message': '"\\' * 50000}}])
        for snapshot in (d, t.loads(t.serialize(d), scope_id='s')):
            record = snapshot['agent_transcript']['turns'][0]
            self.assertLessEqual(len(json.dumps(record['error'], ensure_ascii=False).encode()), t.MAX_TOOL_BYTES)
            self.assertTrue(record['error_capture']['truncated'])

    def test_sanitized_occurrence_roundtrip_keeps_identity_mode(self):
        d = document([message(None, 'one', 'user')], occurrence_ids={0: 'receipt-one'})
        out = t.loads(t.serialize(d), scope_id='ignored')
        self.assertEqual(out['agent_transcript']['timeline'][0]['identity'], 'application_occurrence')
        newer = document([message(None, 'two', 'user')], occurrence_ids={0: 'receipt-two'})['agent_transcript']
        self.assertEqual(len(t.merge(out['agent_transcript'], newer)['timeline']), 2)


@unittest.skipUnless(importlib.util.find_spec('openai') is not None, 'SDK contract pass needs pinned openai 3.22.0')
class SDKFixtureTests(unittest.TestCase):
    def test_synthetic_fixtures_validate_against_actual_pinned_types(self):
        import openai
        from openai.types.beta.agent_session_message import AgentSessionMessage
        from openai.types.beta.agent_command_execution_item import AgentCommandExecutionItem
        from openai.types.beta.agent_function_call_item import AgentFunctionCallItem
        from openai.types.beta.agent_session_item import FunctionCallOutputItemResource, ComputerUseCallItemResource
        from openai.types.beta.agent_mcp_call_item import AgentMcpCallItem
        from openai.types.beta.agent_web_search_call_item import AgentWebSearchCallItem
        from openai.types.beta.agents.sessions.session_artifact import SessionArtifact
        from openai.types.beta.agents.sessions.turn import Turn
        self.assertEqual(openai.__version__, '3.22.0')
        fixtures = [
            (AgentSessionMessage, message()),
            (AgentCommandExecutionItem, {'id': 'cmd', 'turn_id': 'turn1', 'type': 'command_execution', 'command': 'echo synthetic', 'cwd': '/workspace', 'status': 'completed', 'output': 'synthetic', 'exit_code': 0, 'duration_ms': 1}),
            (AgentFunctionCallItem, {'id': 'fn', 'turn_id': 'turn1', 'type': 'function_call', 'name': 'synthetic', 'call_id': 'call1', 'arguments': {'q': 'one'}, 'status': 'completed'}),
            (FunctionCallOutputItemResource, {'id': 'fo', 'turn_id': 'turn1', 'type': 'function_call_output', 'call_id': 'call1', 'output': 'synthetic result', 'status': 'completed'}),
            (AgentMcpCallItem, {'id': 'mcp', 'turn_id': 'turn1', 'type': 'mcp_call', 'server_label': 'synthetic', 'name': 'synthetic', 'arguments': {'q': 'one'}, 'error': None, 'output': {'text': 'synthetic'}, 'status': 'completed'}),
            (AgentWebSearchCallItem, {'id': 'web', 'turn_id': 'turn1', 'type': 'web_search_call', 'status': 'completed', 'action': {'type': 'open_page', 'url': 'https://example.test/a'}}),
            (ComputerUseCallItemResource, {'id': 'browser', 'turn_id': 'turn1', 'type': 'computer_use_call', 'status': 'completed', 'title': 'Synthetic activity', 'output': None}),
        ]
        items = [cls.model_validate(fixture).model_dump() for cls, fixture in fixtures]
        artifact = SessionArtifact.model_validate({'id': 'art', 'turn_id': 'turn1', 'session_id': 'session1', 'environment_id': 'env1', 'object': 'agent.session.artifact', 'created_at': 1, 'path': '/workspace/outputs/synthetic.txt', 'size_bytes': 12}).model_dump()
        turn = Turn.model_validate({'id': 'turn1', 'agent_id': 'root', 'session_id': 'session1', 'object': 'agent.session.turn', 'created_at': 1, 'status': 'completed'}).model_dump()
        rendered = t.render_input(document(items, artifacts=[artifact], turns=[turn], session_id='session1'))
        self.assertEqual(len(rendered['timeline']), 7)
        self.assertEqual(rendered['turn_files'][0]['name'], 'synthetic.txt')

    def test_audit_regressions_with_actual_sdk_types(self):
        from openai.types.beta.agent_mcp_call_item import AgentMcpCallItem
        from openai.types.beta.agent_session_message import AgentSessionMessage
        from openai.types.beta.agents.sessions.turn import Turn
        secret = 'PRIVATE-NEEDLE'
        item = AgentMcpCallItem.model_validate({'id': 'mcp', 'turn_id': 'turn1', 'type': 'mcp_call', 'server_label': 'synthetic', 'name': 'synthetic', 'arguments': {'abc_' + secret: 'safe'}, 'output': {'abc_' + secret: {'nested_' + secret: 'safe'}}, 'error': {'abc_' + secret: 'safe'}, 'status': 'completed'})
        wire = t.serialize(document([item.model_dump()], secrets=[secret]), secrets=[secret])
        self.assertNotIn(secret, wire)
        one = AgentSessionMessage.model_validate(message(None, 'one', 'user'))
        two = AgentSessionMessage.model_validate(message(None, 'two', 'user'))
        a = document([one.model_dump()])['agent_transcript']
        b = document([two.model_dump()])['agent_transcript']
        with self.assertRaises(t.TranscriptError): t.merge(a, b)
        a = document([one.model_dump()], occurrence_ids={0: 'receipt-one'})['agent_transcript']
        b = document([two.model_dump()], occurrence_ids={0: 'receipt-two'})['agent_transcript']
        self.assertEqual(len(t.merge(a, b)['timeline']), 2)
        turn = Turn.model_validate({'id': 'turn1', 'agent_id': 'root', 'session_id': 'session1', 'object': 'agent.session.turn', 'created_at': 1, 'status': 'failed', 'error': {'code': 'server_error', 'message': '\"\\' * 50000}})
        record = document(turns=[turn.model_dump()])['agent_transcript']['turns'][0]
        self.assertLessEqual(len(json.dumps(record['error'], ensure_ascii=False).encode()), t.MAX_TOOL_BYTES)
        self.assertTrue(record['error_capture']['truncated'])

    def test_annotations_and_message_file_ownership_are_not_in_agent_contract(self):
        from openai.types.beta.output_text import OutputText
        from openai.types.beta.agents.sessions.session_artifact import SessionArtifact
        from openai.types.beta.agent_session_item import ComputerUseCallItemResource
        self.assertNotIn('annotations', OutputText.model_fields)
        self.assertNotIn('message_id', SessionArtifact.model_fields)
        self.assertNotIn('mime_type', SessionArtifact.model_fields)
        self.assertNotIn('url', ComputerUseCallItemResource.model_fields)


if __name__ == '__main__':
    unittest.main()
