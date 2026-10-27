import html
import re
import pytest
import gradio as gr
from fastapi.testclient import TestClient
from agent_fixtures import env, select
from modules.agent.ui import ArtifactPanel


@pytest.mark.parametrize('name,expected', [
    ('报告 空格 & "完整".txt','报告 空格 & "完整".txt'),
    ('../../escape\r\nInjected.txt','.._.._escape__Injected.txt'),
    ('..','artifact'),
])
def test_card_uses_safe_original_filename_not_cache_basename(env,tmp_path,name,expected):
    model=select(env)
    path=tmp_path/'cachehash-original.txt';path.write_text('synthetic')
    model._artifacts=[dict(id='a',session_id='s',turn_id='t',name=name,path=str(path),status='ready',size=9)]
    values=ArtifactPanel.values(model)
    value=html.unescape(re.search(r'data-download-name="([^"]*)"',values[1]['value']).group(1))
    assert value==expected
    assert values[2]['value']==[str(path)]


def test_gradio_native_routes_keep_same_name_contents_separate_without_filename_header(tmp_path):
    first=tmp_path/'hash-one-report.txt';first.write_bytes(b'first bytes')
    second=tmp_path/'hash-two-report.txt';second.write_bytes(b'second bytes')
    with gr.Blocks(analytics_enabled=False) as app:
        gr.File()
    app.allowed_paths=[str(tmp_path)]
    client=TestClient(gr.routes.App.create_app(app))
    for path,content in ((first,b'first bytes'),(second,b'second bytes')):
        result=client.get('/file='+str(path))
        assert result.status_code==200 and result.content==content
        # Gradio serves no attachment filename that could override the anchor's
        # same-origin download attribute. Cache identities stay untouched.
        assert 'content-disposition' not in result.headers
