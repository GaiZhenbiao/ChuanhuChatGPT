"""Offline server markup contracts for cards mounted beside assistant messages.

The observer and native click behavior run in tests/javascript/artifact-cards.test.cjs
through test_ui.test_card_native_download_and_retry_dom_contract. These tests
use the real Python projection and renderer to validate the markup it consumes.
"""
from copy import deepcopy
import json
from pathlib import Path
import re
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

from modules.agent.ui import AgentPanel, ArtifactPanel
from modules.model_capabilities import AGENT_CAPABILITIES


class AgentFixture(SimpleNamespace):
    is_hosted_agent = True
    ui_capabilities = AGENT_CAPABILITIES


def model(records, rows=None, conversation='conversation'):
    return AgentFixture(
        _artifacts=records,
        _display=[['first?', 'same answer'], ['second?', 'same answer']] if rows is None else rows,
        _cloud_items=[
            dict(id='user-one', role='user', content='first?', turn_id='turn-one'),
            dict(id='answer-one', role='assistant', content='same answer', turn_id='turn-one'),
            dict(id='user-two', role='user', content='second?', turn_id='turn-two'),
            dict(id='answer-two', role='assistant', content='same answer', turn_id='turn-two'),
        ],
        _state={'session_id': 'session', 'turn_id': 'turn-two'},
        _conversation_id=conversation,
        _answer_row=None,
    )


def artifact(identifier, turn='turn-one', status='ready', **extra):
    return dict(id=identifier, name='same.txt', session_id='session', turn_id=turn,
                status=status, **extra)


def markup_cards(values):
    return ET.fromstring(values[1]['value']).findall('button')


def anchor(rendered):
    return ET.fromstring('<message>' + rendered + '</message>').find('span[@class="agent-message-anchor"]')


def test_real_card_keys_match_each_rendered_answer_across_identical_text_and_restore():
    records = [artifact('second', 'turn-two', path='/tmp/second/same.txt'),
               artifact('first', path='/tmp/first/same.txt')]
    current = model(records, conversation='conversation"<&\'')
    original = deepcopy(vars(current))
    values = ArtifactPanel.values(current)
    cards = {card.get('data-artifact-id'): card for card in markup_cards(values)}
    rendered = AgentPanel().render_chat(current, current._display)
    first, second = [anchor(row[1]) for row in rendered]
    assert first.get('data-message-key') != second.get('data-message-key')
    assert cards['first'].get('data-message-key') == first.get('data-message-key')
    assert cards['second'].get('data-message-key') == second.get('data-message-key')
    for card in cards.values():
        assert card.get('data-conversation-id') == current._conversation_id
        assert card.get('data-conversation-id') == first.get('data-conversation-id')
    assert vars(current) == original
    # Restoring a shortened view does not switch the surviving file to row index 0.
    restored = model(records, rows=[['second?', 'same answer']], conversation='restored')
    restored_values = {card.get('data-artifact-id'): card for card in markup_cards(ArtifactPanel.values(restored))}
    restored_render = AgentPanel().render_chat(restored, restored._display)
    assert restored_values['second'].get('data-message-key') == cards['second'].get('data-message-key')
    assert restored_values['second'].get('data-message-key') == anchor(restored_render[0][1]).get('data-message-key')
    assert restored_values['first'].get('data-message-key') != anchor(restored_render[0][1]).get('data-message-key')
    assert restored_values['second'].get('data-conversation-id') == 'restored'


def test_ready_cards_have_native_button_semantics_and_no_redundant_visible_download_state():
    current = model([artifact('file"<&\'', path='/tmp/file/same.txt', size=1234)])
    values = ArtifactPanel.values(current)
    card, = markup_cards(values)
    assert card.tag == 'button' and card.get('type') == 'button'
    assert card.get('disabled') is None
    assert card.get('data-file-action') == 'download'
    assert card.get('data-artifact-id') == 'file"<&\''
    assert card.get('aria-label') == 'same.txt，下载文件'
    assert card.find('.//span[@class="model-file-name"]').get('title') == 'same.txt'
    assert card.find('.//span[@class="model-file-state"]') is None
    visible = ''.join(card.itertext())
    assert '可下载' not in visible and '下载文件' not in visible
    assert ''.join(card.find('.//span[@class="model-file-name"]').itertext()) == 'same'
    assert ''.join(card.find('.//span[@class="model-file-meta"]').itertext()) == 'TXT · 1.21 KB'
    assert card.find('.//span[@class="model-file-feedback"]').get('aria-live') == 'polite'
    assert json.loads(values[2]['label']) == ['file"<&\'']
    assert values[2]['value'] == ['/tmp/file/same.txt']


@pytest.mark.parametrize(('status', 'action', 'disabled', 'state'), [
    ('preparing', '', True, '准备中'),
    ('ready', 'download', False, None),
    ('failed', 'retry', False, '下载失败，点击重试'),
])
def test_rendered_status_transitions_preserve_the_same_message_owner(status, action, disabled, state):
    current = model([artifact('file', status=status, path='/tmp/file/same.txt' if status == 'ready' else None)])
    values = ArtifactPanel.values(current)
    card, = markup_cards(values)
    assert card.get('data-file-action') == action
    assert (card.get('disabled') is not None) is disabled
    rendered = AgentPanel().render_chat(current, current._display)
    assert card.get('data-message-key') == anchor(rendered[0][1]).get('data-message-key')
    assert card.findtext('.//span[@class="model-file-state"]') == state
    assert values[2]['value'] == (['/tmp/file/same.txt'] if status == 'ready' else [])
    assert json.loads(values[2]['label']) == (['file'] if status == 'ready' else [])


def test_native_id_list_stays_parallel_to_only_ready_downloadable_paths_for_duplicate_names():
    current = model([
        artifact('preparing', status='preparing'),
        artifact('second', 'turn-two', path='/tmp/second/same.txt'),
        artifact('failed', status='failed', error='download interrupted'),
        artifact('missing-path', status='ready'),
        artifact('first', path='/tmp/first/same.txt'),
    ])
    values = ArtifactPanel.values(current)
    cards = markup_cards(values)
    assert [''.join(card.find('.//span[@class="model-file-name"]').itertext()) for card in cards] == ['same'] * 5
    assert json.loads(values[2]['label']) == ['second', 'first']
    assert values[2]['value'] == ['/tmp/second/same.txt', '/tmp/first/same.txt']
    assert cards[3].get('data-file-action') == '' and cards[3].get('disabled') is not None
    assert cards[2].findtext('.//span[@class="model-file-error"]') == '：download interrupted'


def test_css_hides_source_panel_and_empty_bubble_without_hiding_mounted_file_holders():
    css = (Path(__file__).resolve().parents[2] / 'web_assets/stylesheet/chatbot.css').read_text()
    rules = [(selector.strip(), body) for selector, body in re.findall(r'([^{}]+)\{([^{}]+)\}', css)]
    def declarations(selector):
        return '\n'.join(body for selectors, body in rules if selector in [item.strip() for item in selectors.split(',')])
    assert re.search(r'display\s*:\s*none\s*!important', declarations('#model-output-files'))
    assert re.search(r'display\s*:\s*none\s*!important', declarations('.agent-file-only-message'))
    assert re.search(r'display\s*:\s*none\s*!important', declarations('.agent-message-anchor'))
    assert not re.search(r'display\s*:\s*none', declarations('#chuanhu-chatbot .agent-message-files'))


def test_bot_column_stays_fixed_against_gradio_mobile_auto_without_resizing_user_bubbles():
    css = (Path(__file__).resolve().parents[2] / 'web_assets/stylesheet/chatbot.css').read_text()
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    rules = [(selector.strip(), body) for selector, body in re.findall(r'([^{}]+)\{([^{}]+)\}', css)]
    def bodies(selector):
        return '\n'.join(body for selectors, body in rules if selector in [item.strip() for item in selectors.split(',')])
    assert re.search(r'(?<!max-)\bwidth\s*:\s*100%\s*!important', bodies('.message.bot'))
    assert 'max-width: calc(85% - 40px)' in bodies('.message.bot')
    assert 'max-width: calc(100% - 23px) !important' in bodies('.message.bot')
    assert re.search(r'(?<!max-)\bwidth\s*:\s*auto\s*!important', bodies('.message.user'))
    assert '#chuanhu-chatbot .agent-message-has-files > .message.bot' not in css
