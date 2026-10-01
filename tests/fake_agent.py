"""Synthetic backend shared by HTTP smoke and the real project-layout preview."""
import threading
import time
import uuid

class FakeAgentBackend:
    def __init__(self, directory):
        self.sessions={}
        self.commands=[]
        self.lock=threading.Lock()
        self.artifact=directory/'synthetic.txt'
        self.artifact.write_text('Synthetic artifact. No API was called.\n')

    def messages(self, command):
        with self.lock: self.commands.append(command)
        action=command['action'];sid=command.get('session_id')
        if action=='run':
            sid=sid or 'sess_'+uuid.uuid4().hex;tid='turn_'+uuid.uuid4().hex
            self.sessions[sid]={'outcome':'in_progress','text':'','turn_id':tid}
            yield {'type':'progress','session_id':sid,'turn_id':tid,'outcome':'incomplete','progress':'agent.session.turn.created'}
            for i in range(8):
                time.sleep(.1)
                if self.sessions[sid]['outcome']=='cancelled':
                    yield {'type':'error','session_id':sid,'turn_id':tid,'outcome':'cancelled','message':'Synthetic cancellation confirmed.'}
                    return
                yield {'type':'progress','session_id':sid,'turn_id':tid,'outcome':'incomplete','progress':'agent.session.turn.in_progress','text':'Synthetic task step '+str(i+1)}
            text='Synthetic result: '+command['prompt'];self.sessions[sid].update(outcome='completed',text=text)
            yield {'type':'result','session_id':sid,'turn_id':tid,'outcome':'completed','text':text}
        elif action=='inspect':
            yield {'type':'result',**self.sessions[sid],'session_id':sid,'artifacts':[{'path':'/workspace/synthetic.txt'}]}
        elif action=='cancel':
            self.sessions[sid]['outcome']='cancelled'
            yield {'type':'result','outcome':'cancel_requested','text':'Synthetic cancellation submitted.'}
        elif action=='download':
            yield {'type':'result','files':[str(self.artifact)]}
        elif action=='delete':
            del self.sessions[sid]
            yield {'type':'result','outcome':'deleted'}
