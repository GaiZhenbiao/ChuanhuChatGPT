from copy import deepcopy
import threading
import gradio as gr
from agent_fixtures import env,select,send,complete


def test_two_inflight_cancels_keep_session_reserved_until_both_finish(env,monkeypatch):
    complete(env,monkeypatch);one=select(env);send(env,one)
    two=select(env);three=select(env)
    for model in (two,three):
        model._state=deepcopy(one._state)
        model._session_settings=deepcopy(one._session_settings)
    one._state['outcome']=two._state['outcome']='in_progress'
    started={name:threading.Event() for name in ('cancel-one','cancel-two')}
    release={name:threading.Event() for name in started}
    errors=[]
    def worker(command):
        assert command['action']=='cancel'
        name=threading.current_thread().name
        started[name].set()
        assert release[name].wait(5)
        yield {'type':'result','outcome':'cancel_requested'}
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    def cancel(model):
        try:model._cancel(model._state['generation'])
        except Exception as error:errors.append(error)
    threads=[threading.Thread(target=cancel,args=(model,),name=name) for model,name in ((one,'cancel-one'),(two,'cancel-two'))]
    generator=None
    try:
        for thread in threads:thread.start()
        assert all(start.wait(3) for start in started.values())
        release['cancel-one'].set();threads[0].join(3)
        assert threads[1].is_alive() and not errors
        # The first stop has completed; a refreshed third browser sees old turn terminal.
        assert three._state['outcome']=='completed'
        blocked=False
        generator=three.predict('new turn must wait for second stop',[])
        try:next(generator)
        except gr.Error:blocked=True
        assert blocked, 'First cancel removed the shared marker while the second old-turn cancel was still in flight'
    finally:
        if generator is not None:generator.close()
        for item in release.values():item.set()
        for thread in threads:thread.join(3)
