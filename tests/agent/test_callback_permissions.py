import asyncio
import gradio as gr
from gradio.state_holder import SessionState
from modules.agent.ui import AgentPanel
from agent_fixtures import env,select,send,complete


def create_app(env, model):
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();question=gr.State();input_box=gr.Textbox();chat=gr.Chatbot();status=gr.Markdown();submit=gr.Button();cancel=gr.Button()
        submit.click(env.wrappers['transfer_input'],[input_box,current],[question,input_box,submit,cancel]).then(env.wrappers['predict'],[current,question,chat],[chat,status])
        panel=AgentPanel();panel.selectors();panel.output_components();panel.settings_components();panel.wire(current,chat,status)
    state=SessionState(app);state[current._id]=model
    return app,state,question,{fn.fn.__name__:i for i,fn in enumerate(app.fns) if fn.fn}


def test_transfer_input_must_reject_other_owner_before_reserving(env,monkeypatch):
    complete(env,monkeypatch);model=select(env,username='alice')
    app,state,question,indexes=create_app(env,model)
    try:
        try:
            asyncio.run(app.process_api(indexes['transfer_input'],['foreign input',None],state=state,request=gr.Request(username='bob',session_hash='review-ui')))
        except gr.Error: pass
        assert not getattr(model,'_pending_send',None), 'Bob must not reserve and lock Alice model state'
    finally: app.close()


def test_pending_send_cannot_be_redirected_by_fork_callback(env,monkeypatch):
    calls,_=complete(env,monkeypatch);model=select(env);send(env,model)
    original=model._state['session_id']
    app,state,question,indexes=create_app(env,model)
    async def exercise():
        req=gr.Request(session_hash='review-ui')
        await app.process_api(indexes['transfer_input'],['intended for original session',None],state=state,request=req)
        try: await app.process_api(indexes['fork'],[None],state=state,request=req)
        except gr.Error: pass
        assert model._state.get('session_id')==original, 'Fork changed the queued request target within the same model object'
        result=await app.process_api(indexes['predict'],[None,None,model.chatbot],state=state,request=req)
        while result['is_generating']:
            result=await app.process_api(indexes['predict'],[None,None,model.chatbot],state=state,request=req,iterator=result['iterator'])
        assert [c for c in calls if c['action']=='run'][-1]['session_id']==original
    try: asyncio.run(exercise())
    finally: app.close()
