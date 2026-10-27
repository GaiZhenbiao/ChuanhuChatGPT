"""流中发布文件与文字事件互不阻塞，只使用本地合成数据。"""
from threading import Event

from modules.agent.artifacts import ArtifactObserver
from agent_fixtures import complete, env, select, send


def test_live_poll_publishes_file_before_turn_finishes(monkeypatch):
    import modules.agent.artifacts as artifacts
    published = Event()
    calls, frames = [], []

    def download(client, session_id, *, skip_artifact_ids, on_progress, cache_root, should_cancel, live, turn_id, artifact_ids):
        calls.append(set(skip_artifact_ids))
        if 'file-one' not in skip_artifact_ids:
            on_progress([{'id': 'file-one', 'status': 'ready', 'path': '/synthetic'}])
        return []

    def emit(kind, **frame):
        frames.append(frame)
        if frame.get('artifacts', [{}])[0].get('status') == 'ready': published.set()

    monkeypatch.setattr(artifacts, 'list_artifact_metadata', lambda *args, **kwargs: [{'id':'file-one','status':'preparing'}])
    monkeypatch.setattr(artifacts, 'download_artifacts', download)
    with ArtifactObserver(object(), emit, interval=0.01) as observer:
        observer.observe_session('sess_one', 'turn_one')
        assert published.wait(1)
        assert frames[-1]['artifacts'][0]['status'] == 'ready'
        assert not observer.stop.is_set()
    assert observer.ready == {'file-one'}


def test_running_model_projects_ready_file_without_history_reload(env, monkeypatch):
    _, path = complete(env, monkeypatch)
    model = select(env)
    seen = []

    def worker(command):
        if command['action'] == 'run':
            yield dict(type='progress', session_id='sess_one', turn_id='turn_one', outcome='in_progress', text='处理中')
            yield dict(type='progress', session_id='sess_one', artifacts=[dict(id='file-one', session_id='sess_one', turn_id='turn_one', status='ready', name=path.name, path=str(path))])
            seen.append((model._running, model._artifacts[0]['status']))
            yield dict(type='result', session_id='sess_one', turn_id='turn_one', outcome='completed', text='已完成')
        elif command['action'] == 'download':
            assert command['skip_artifact_ids'] == ['file-one']
            yield dict(type='result', artifacts=[])
        else:
            raise AssertionError(command['action'])

    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    send(env, model)
    assert seen == [(True, 'ready')]
    assert model.chatbot == [['hello', '已完成']]
