"""Palette, filename safety and shared markup across all three file surfaces."""
import json
from threading import RLock
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

from modules.agent.file_icons import file_extension, file_icon, file_size_label, file_type_label
from modules.agent.message_files import MessageFileProjection, render_projection
from modules.agent.ui import AgentPanel, ArtifactPanel
from modules.model_capabilities import AGENT_CAPABILITIES


@pytest.mark.parametrize('name,extension,kind', [
    ('report.PdF', 'PDF', 'pdf'), ('table.CsV', 'CSV', 'sheet'), ('report.DOCX', 'DOCX', 'document'),
    ('file.xyz', 'XYZ', 'unknown'), ('file.abcde', 'ABCDE', 'unknown'), ('file.<&', '<&', 'unknown'),
    ('bundle.TAR.GZ', 'TAR.GZ', 'archive'), ('types.d.TS', 'D.TS', 'code'),
    ('photo.JPG', 'JPG', 'image'), ('notes.txt', 'TXT', 'text'),
    ('README', '', 'unknown'), ('.env', '', 'unknown'), ('trailing.', '', 'unknown'),
    ('report.unrecognizedextension', 'UNRECOGNIZEDEXTENSION', 'unknown'),
    ('name.<svg onload="bad()">', '<SVG ONLOAD="BAD()">', 'unknown'),
])
def test_extension_normalization_palette_and_safe_bounded_icon(name, extension, kind):
    assert file_extension(name) == extension
    icon = ET.fromstring(file_icon(name))
    assert icon.get('data-file-kind') == kind
    label = icon.find('.//text')
    if extension and len(extension) <= 5:
        assert label.text == extension
        assert label.get('fill') == 'currentColor' and label.get('stroke') == 'none'
        assert label.get('font-size') == ('4' if len(extension) >= 4 else '5')
        if len(extension) >= 4:
            assert label.get('textLength') == '10'
    else:
        assert label is None
    assert icon.find('.//svg').get('fill') == 'none'
    assert icon.find('.//path').get('fill') == 'currentColor'
    assert float(icon.find('.//path').get('fill-opacity')) == .14
    assert icon.find('.//path').get('d').endswith('V9H13z')
    assert icon.findall('.//path')[1].get('fill') == 'none'
    assert file_type_label(name) == ((extension or 'FILE')[:5] + ('…' if len(extension) > 5 else ''))
    assert icon.find('.//svg').get('onload') is None
    assert len(icon.findall('.//svg')) == 1


def test_composer_user_and_bot_use_identical_icon_renderer_and_escape_names():
    name = 'name"<&.CsV'
    class AgentFixture(SimpleNamespace):
        ui_capabilities = AGENT_CAPABILITIES
    model = AgentFixture(is_hosted_agent=True,
        _lock=RLock(), _conversation_id='chat', _pending_upload_paths=[],
        _input_stager=SimpleNamespace(snapshot=lambda: [SimpleNamespace(input_id='input', name=name, size=12)]),
        _artifacts=[dict(id='file', name=name, size=12, status='ready', path='/tmp/synthetic', turn_id='turn')],
        _display=[['hello', 'answer']], _cloud_items=[], _state={'session_id':'session', 'turn_id':'turn'}, _answer_row=0)
    pending = json.loads(AgentPanel.input_value(model, interactive=True)['label'])['files'][0]
    assert pending['extension'] == 'CSV'
    assert pending['basename'] == 'name"<&'
    assert pending['size_label'] == '0.01 KB'
    assert pending['icon'] == file_icon(name, input_card=True)
    projection = MessageFileProjection([['hello', 'answer']], {}, {}, set(), 'chat',
        _original_rows=[['hello', 'answer']], user_files={0:[{'name':name, 'size':12}]})
    user = render_projection(projection, lambda text:text, lambda text:text)[0][0]
    assert file_icon(name) in user
    assert 'agent-input-card agent-file-card' in user
    assert 'name&quot;&lt;&amp;.CsV' in user
    assert '>name&quot;&lt;&amp;</span>' in user
    assert '<span class="agent-input-meta" data-file-part="meta">CSV · 0.01 KB</span>' in user
    bot = ArtifactPanel.values(model)[1]['value']
    assert file_icon(name) in bot
    assert 'model-file-card agent-file-card' in bot
    for part in ('content', 'name', 'basename', 'meta'):
        assert f'data-file-part="{part}"' in user
        assert f'data-file-part="{part}"' in bot
    assert 'name&quot;&lt;&amp;.CsV' in bot
    assert '<span class="model-file-extension">CSV</span> · <span class="model-file-size">0.01 KB</span>' in bot


def test_long_and_missing_extension_metadata_has_one_separator_and_bounded_type():
    for name, label in [('file.unknownextensionlong', 'UNKNO…'), ('README', 'FILE'), ('.env', 'FILE')]:
        assert file_type_label(name) == label
        meta = file_type_label(name) + ' · ' + file_size_label(1234)
        assert meta == label + ' · 1.21 KB'
        assert meta.count(' · ') == 1


@pytest.mark.parametrize('name,basename', [('archive.TAR.GZ', 'archive'), ('definition.d.ts', 'definition'),
    ('README', 'README'), ('.env', '.env'), ('.config.json', '.config'), ('trailing.', 'trailing.')])
def test_pending_and_user_titles_share_compound_suffix_rules_and_keep_full_hint(name, basename):
    model = SimpleNamespace(is_hosted_agent=True, _lock=RLock(), _conversation_id='chat', _pending_upload_paths=[],
        _input_stager=SimpleNamespace(snapshot=lambda: [SimpleNamespace(input_id='input', name=name, size=12)]))
    pending = json.loads(AgentPanel.input_value(model, interactive=True)['label'])['files'][0]
    assert pending['name'] == name and pending['basename'] == basename
    projection = MessageFileProjection([['hello', 'answer']], {}, {}, set(), 'chat',
        _original_rows=[['hello', 'answer']], user_files={0:[{'name':name, 'size':12}]})
    user = render_projection(projection, lambda text:text, lambda text:text)[0][0]
    assert f'title="{name}"><span data-file-part="basename">{basename}</span>' in user

@pytest.mark.parametrize('size,label', [(0, '0.00 KB'), (1023, '1.00 KB'), (1024, '1.00 KB'), (1024**2, '1.00 MB'), (1024**3, '1.00 GB'), (None, '大小待确认'), (-1, '大小待确认')])
def test_size_units(size, label):
    assert file_size_label(size) == label
