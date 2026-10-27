"""真实Gradio快速新建→历史点击；全程独立合成供应商与历史。"""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_fast_new_chat_history_click_keeps_radio_and_body_consistent(tmp_path):
    cli = os.environ.get('CHUANHU_PLAYWRIGHT_CLI') or shutil.which('playwright-cli')
    if not cli:
        pytest.skip('Set CHUANHU_PLAYWRIGHT_CLI for real browser regression')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    session = 'fast-history-' + str(port)
    with (tmp_path/'server.log').open('w') as log:
        server = subprocess.Popen([sys.executable, 'tests/main_chat_preview.py', '--port', str(port)],
                                  cwd=ROOT, stdout=log, stderr=log, env=dict(os.environ, GRADIO_ANALYTICS_ENABLED='False', CHUANHU_TRACE_LIFECYCLE='1'))
        try:
            url = f'http://127.0.0.1:{port}'
            deadline = time.monotonic()+40
            while time.monotonic()<deadline:
                assert server.poll() is None, (tmp_path/'server.log').read_text()
                try:
                    urllib.request.urlopen(url,timeout=1).close(); break
                except OSError: time.sleep(.1)
            else: pytest.fail('Synthetic server did not start')
            opened = subprocess.run([cli,'-s='+session,'open',url],cwd=tmp_path,capture_output=True,text=True,timeout=40)
            assert opened.returncode==0 and '### Error' not in opened.stdout, opened.stdout+opened.stderr
            code = '''async page => {
                let phase="initial";try { await page.evaluate(()=>{window.submitTrace=[];window.addEventListener('keydown',event=>{if(event.key==='Enter')window.submitTrace.push({caps:document.querySelector('[data-model-capabilities]')?.dataset.modelCapabilities,disabled:event.target.disabled,send:document.querySelector('#submit-btn')?.outerHTML});},true);}); const composer=page.getByPlaceholder("在这里输入",{exact:true});
                await composer.fill("Ordinary fast history anchor"); await composer.press("Enter");
                await page.waitForFunction(() => document.querySelector("#chuanhu-chatbot")?.textContent.includes("Ordinary synthetic response"));
                const firstAnswerAt=Date.now();await page.waitForFunction(() => document.querySelectorAll("#history-select-dropdown input:checked").length===1);
                phase='delete';await page.locator('#chuanhu-chatbot .delete-latest-btn').click();
                await page.waitForFunction(()=>document.querySelectorAll('#chuanhu-chatbot .message.bot').length===0);
                phase='wait send ready after delete';await page.waitForFunction(()=>{const button=document.querySelector('#submit-btn');return !JSON.parse(document.querySelector('[data-model-capabilities]')?.dataset.modelCapabilities||'{}').busy && button && !button.hidden && !button.classList.contains('hidden');},null,{timeout:2500});
                const readyAt=Date.now();if(readyAt-firstAnswerAt>2500)throw Error('Ordinary answer→Send exceeded 2500ms');
                console.log('LIFECYCLE UI_ANSWER',firstAnswerAt,'UI_SEND_READY',readyAt,'DELTA_MS',readyAt-firstAnswerAt);
                phase='resubmit after delete';await composer.fill('Ordinary fast history anchor');await composer.press('Enter');
                await page.waitForFunction(()=>document.querySelector('#chuanhu-chatbot')?.textContent.includes('Ordinary synthetic response'));
                for(let i=0;i<3;i++) { phase="history loop "+i;
                    await page.locator("#new-chat-btn").click();
                    await page.waitForFunction(() => document.querySelectorAll("#chuanhu-chatbot .message.bot").length===0);
                    if(await page.locator("#history-select-dropdown input:checked").count()) throw Error("Ordinary draft selected");
                    // Deliberately do not wait for capability visit or later .then callbacks.
                    await page.locator("#history-select-dropdown label").first().click();
                    await page.waitForFunction(() => document.querySelector("#chuanhu-chatbot")?.textContent.includes("Ordinary synthetic response"));
                }
                await page.locator("#new-chat-btn").click();
                await page.waitForFunction(() => document.querySelectorAll("#chuanhu-chatbot .message.bot").length===0);
                await page.getByRole("listbox",{name:"选择模型",exact:true}).click();
                await page.getByRole("option",{name:"OpenAI Agent",exact:true}).click();
                await page.waitForFunction(() => JSON.parse(document.querySelector("[data-model-capabilities]")?.dataset.modelCapabilities||"{}").agent_tools===true);
                await composer.fill("Agent fast history anchor"); await composer.press("Enter");
                await page.waitForFunction(() => JSON.parse(document.querySelector("[data-model-capabilities]")?.dataset.modelCapabilities||"{}").turn_terminal===true);
                const agentUiTerminalAt=Date.now();await page.waitForFunction(()=>{const button=document.querySelector('#submit-btn');return button && !button.hidden && !button.classList.contains('hidden') && JSON.parse(document.querySelector('[data-model-capabilities]')?.dataset.modelCapabilities||'{}').busy===false;},null,{timeout:2500});
                const agentReadyAt=Date.now();
                for(let i=0;i<3;i++) {
                    await page.locator("#new-chat-btn").click();
                    await page.waitForFunction(() => document.querySelectorAll("#chuanhu-chatbot .message.bot").length===0);
                    if(await page.locator("#history-select-dropdown input:checked").count()) throw Error("Agent draft selected");
                    await page.locator("#history-select-dropdown label").first().click();
                    await page.waitForFunction(() => document.querySelectorAll("#chuanhu-chatbot .message.bot").length>0);
                    if(await page.locator("#history-select-dropdown input:checked").count()!==1) throw Error("History body/selection mismatch");
                }
            return {firstAnswerAt,readyAt,deltaMs:readyAt-firstAnswerAt,agentUiTerminalAt,agentReadyAt,agentUiDeltaMs:agentReadyAt-agentUiTerminalAt}; } catch(e) {throw Error(phase+': '+e.message+' '+await page.evaluate(()=>JSON.stringify({caps:document.querySelector('[data-model-capabilities]')?.dataset.modelCapabilities,body:document.querySelector('#chuanhu-chatbot')?.textContent,status:document.querySelector('#status-display')?.textContent,botCount:document.querySelectorAll('#chuanhu-chatbot .message.bot').length,inputDisabled:document.querySelector('#user-input-tb textarea')?.disabled,sendDisabled:document.querySelector('#submit-btn')?.disabled,submitTrace:window.submitTrace})));} }'''
            result = subprocess.run([cli,'-s='+session,'run-code',code],cwd=tmp_path,capture_output=True,text=True,timeout=100)
            (tmp_path/'browser-result.txt').write_text(result.stdout+result.stderr)
            print('LIFECYCLE EVIDENCE',str(tmp_path),result.stdout,(tmp_path/'server.log').read_text())
            assert result.returncode==0 and '### Error' not in result.stdout, result.stdout+result.stderr+(tmp_path/'server.log').read_text()
        finally:
            subprocess.run([cli,'-s='+session,'close'],cwd=tmp_path,capture_output=True,timeout=20)
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()
