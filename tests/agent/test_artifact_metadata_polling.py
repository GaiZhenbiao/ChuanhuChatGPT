"""Real list/download paths with synthetic held content, never provider requests."""
from copy import deepcopy
from threading import Event, Thread
from types import SimpleNamespace
import time
import pytest
from modules.agent.artifacts import ArtifactObserver
from modules.agent.runtime import list_artifact_metadata


def record(key='first', **extra):
    return dict(id=key,session_id='sess_one',turn_id='turn_one',filename=key+'.txt',size_bytes=3,**extra)


class Provider:
    def __init__(self):
        self.entered=Event();self.release=Event();self.later=False;self.reads=[];self.downloads=[]
        endpoint=SimpleNamespace(list=self.list,with_streaming_response=SimpleNamespace(content=self.content))
        self.client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(artifacts=endpoint))))
    def list(self,*args,**kwargs):
        self.reads.append(time.monotonic())
        return [record()]+([record('later')] if self.later else [])
    def content(self,key,**kwargs):
        self.downloads.append(key)
        owner=self
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def iter_bytes(self):
                if key=='first':
                    owner.entered.set();assert owner.release.wait(5)
                yield b'abc'
        return Response()


def test_second_file_metadata_arrives_while_first_bytes_are_still_blocked(tmp_path):
    provider=Provider();seen=Event();ready=Event();frames=[]
    def emit(kind,**frame):
        frames.extend(deepcopy(frame.get('artifacts',[])))
        if any(r['id']=='later' for r in frames):seen.set()
        if any(r['id']=='later' and r['status']=='ready' for r in frames):ready.set()
    with ArtifactObserver(provider.client,emit,interval=.02,cache_root=tmp_path/'cache') as observer:
        try:
            observer.observe_session('sess_one','turn_one')
            assert provider.entered.wait(2)
            provider.later=True
            assert seen.wait(2),'later metadata must not wait for first content or root completion'
            assert not provider.release.is_set()
            snapshot=observer.snapshot('sess_one','turn_one')
            assert {r['id'] for r in snapshot}=={'first','later'}
            assert all(r['status']=='preparing' and 'path' not in r for r in snapshot)
            assert provider.downloads==['first'],'one byte worker, no duplicate competing content'
            provider.release.set();assert ready.wait(2)
            assert provider.downloads==['first','later']
            observer._refresh()
            assert all(r['status']=='ready' for r in observer.snapshot('sess_one','turn_one'))
        finally:provider.release.set()
    observer.download_thread.join(2);assert not observer.download_thread.is_alive()


def test_metadata_listing_never_opens_content_or_cache(monkeypatch):
    from modules.agent import artifact_cache
    monkeypatch.setattr(artifact_cache,'ArtifactCache',lambda *a,**k:pytest.fail('metadata cannot acquire cache locks'))
    provider=Provider();provider.later=True
    records=list_artifact_metadata(provider.client,'sess_one',turn_id='turn_one')
    assert len(records)==2 and all(r['status']=='preparing' and 'path' not in r for r in records)
    assert not provider.downloads


def test_emissions_keep_preparing_before_failure_without_blocking_snapshot():
    entered=Event();release=Event();finished=Event();wire=[]
    def emit(kind,**frame):
        status=frame['artifacts'][0]['status']
        if status=='preparing':entered.set();assert release.wait(3)
        wire.append(status)
    observer=ArtifactObserver(object(),emit)
    observer.session_id='sess_one';observer.turn_id='turn_one'
    metadata=dict(id='first',session_id='sess_one',turn_id='turn_one',name='first.txt',status='preparing')
    first=Thread(target=observer._publish,args=([metadata],))
    def fail():observer._publish([dict(metadata,status='failed',error='synthetic')]);finished.set()
    second=Thread(target=fail)
    first.start();assert entered.wait(2);second.start()
    try:
        assert observer.snapshot('sess_one','turn_one')==[metadata]
        assert not finished.wait(.05)
        release.set();first.join(2);second.join(2)
        observer._publish([metadata])
        assert wire==['preparing','failed']
        assert observer.snapshot('sess_one','turn_one')[0]['status']=='failed'
    finally:release.set();first.join(2);second.join(2)


def test_stop_does_not_publish_cancelled_download_as_failure(tmp_path):
    provider=Provider();frames=[]
    observer=ArtifactObserver(provider.client,lambda kind,**f:frames.extend(deepcopy(f.get('artifacts',[]))),interval=.02,cache_root=tmp_path/'cache')
    observer.observe_session('sess_one','turn_one');assert provider.entered.wait(2)
    started=time.monotonic();observer.__exit__()
    assert time.monotonic()-started<1.0,'shutdown must not wait for held content'
    before=deepcopy(frames);provider.release.set();observer.download_thread.join(2)
    assert not observer.download_thread.is_alive() and frames==before
    assert all(r['status']=='preparing' for r in frames)
    assert not observer.ready
    assert not list((tmp_path/'cache').rglob('*.part'))


def test_list_error_is_reported_and_recovery_still_discovers_files(monkeypatch):
    import modules.agent.artifacts as artifacts
    frames=[];observer=ArtifactObserver(object(),lambda kind,**f:frames.append(f))
    observer.session_id='sess_one';observer.turn_id='turn_one'
    def fail(*a,**k):raise RuntimeError('synthetic')
    monkeypatch.setattr(artifacts,'list_artifact_metadata',fail)
    observer._refresh();observer._refresh()
    assert len(frames)==1 and 'artifact_error' in frames[0]
    monkeypatch.setattr(artifacts,'list_artifact_metadata',lambda *a,**k:[dict(record(),status='preparing')])
    observer._refresh();assert frames[-1]['artifacts'][0]['id']=='first'
    assert not observer.error_reported
