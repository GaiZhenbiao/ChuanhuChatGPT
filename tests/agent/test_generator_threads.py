import asyncio
import threading
import anyio
import gradio as gr
from gradio.state_holder import SessionState
from agent_fixtures import env,select


def test_network_command_generator_does_not_keep_thread_owned_lock(env,monkeypatch):
    model=select(env)
    ownership=[]
    validate=env.agents.validate_settings
    def record_validate(*args,**kwargs):
        ownership.append(threading.get_ident())
        return validate(*args,**kwargs)
    monkeypatch.setattr(env.agents,'validate_settings',record_validate)
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();prompt=gr.Textbox();chat=gr.Chatbot();status=gr.Markdown()
        gr.Button().click(env.wrappers['predict'],[current,prompt,chat],[chat,status])
    state=SessionState(app);state[current._id]=model
    occupied=threading.Event();release=threading.Event();worker_ids=[]
    def occupy_previous_worker():
        worker_ids.append(threading.get_ident());occupied.set();assert release.wait(5)
    async def exercise():
        req=gr.Request(session_hash='review-ui')
        first=await app.process_api(0,[None,'关网',[]],state=state,request=req)
        assert first['is_generating'] and ownership
        busy=asyncio.create_task(anyio.to_thread.run_sync(occupy_previous_worker))
        try:
            while not occupied.is_set():await asyncio.sleep(.005)
            assert worker_ids[0]!=ownership[0], 'Agent execution belongs to its independent background thread'
            print('FIRST_YIELD_AND_OCCUPIED_THREAD',ownership[0])
            final=await app.process_api(0,[None,'关网',[]],state=state,request=req,iterator=first['iterator'])
            assert not final['is_generating']
        finally:
            release.set();await busy
    try:asyncio.run(exercise())
    finally:app.close()


def test_empty_reconnect_can_finish_on_another_thread(env):
    import threading
    model=select(env);iterator=model.reconnect();first=threading.Event();release=threading.Event();errors=[]
    def start():
        try:next(iterator);first.set();release.wait(3)
        except Exception as error:errors.append(error);first.set()
    worker=threading.Thread(target=start);worker.start();assert first.wait(3)
    try:
        try:next(iterator)
        except StopIteration:pass
        except Exception as error:errors.append(error)
    finally:release.set();worker.join(3)
    assert not errors and not worker.is_alive()


def test_agent_generators_never_yield_inside_thread_owned_lock():
    import ast
    from pathlib import Path
    source=ast.parse((Path(__file__).resolve().parents[2]/'modules/models/OpenAIAgents.py').read_text())
    for node in ast.walk(source):
        if isinstance(node,ast.With) and any(isinstance(item.context_expr,ast.Attribute) and item.context_expr.attr=='_lock' for item in node.items):
            assert not any(isinstance(child,(ast.Yield,ast.YieldFrom)) for statement in node.body for child in ast.walk(statement)), f'Yield inside a thread-owned lock at line {node.lineno}'
