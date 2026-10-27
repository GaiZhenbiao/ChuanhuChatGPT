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


def test_mobile_long_tasks_keep_selected_body_loader_and_stop(tmp_path):
    cli = os.environ.get('CHUANHU_PLAYWRIGHT_CLI') or shutil.which('playwright-cli')
    if not cli:
        pytest.skip('Set CHUANHU_PLAYWRIGHT_CLI for real browser regression')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    session = 'fast-history-' + str(port)
    with (tmp_path/'server.log').open('w') as log:
        server = subprocess.Popen([sys.executable, 'tests/main_chat_preview.py', '--port', str(port)],
                                  cwd=ROOT, stdout=log, stderr=log, env=dict(os.environ, GRADIO_ANALYTICS_ENABLED='False',CHUANHU_SYNTHETIC_SLOW_SECONDS='90',CHUANHU_TRACE_HISTORY='1'))
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
                let phase='reload';try {
                await page.setViewportSize({width:400,height:729});
                const errors=[];page.on('pageerror',error=>errors.push(error.stack));
                await page.reload();
                const composer=page.getByPlaceholder("在这里输入",{exact:true});
                await page.getByRole("listbox",{name:"选择模型",exact:true}).click();
                await page.getByRole("option",{name:"OpenAI Agent",exact:true}).click();
                await page.waitForFunction(()=>JSON.parse(document.querySelector('[data-model-capabilities]')?.dataset.modelCapabilities||'{}').agent_tools===true);
                phase='submit C';await composer.fill("slow mobile C");await composer.press("Enter");
                const busy=()=>page.waitForFunction(()=>JSON.parse(document.querySelector("[data-model-capabilities]")?.dataset.modelCapabilities||"{}").busy===true);
                await busy();
                await page.waitForFunction(()=>document.querySelector('#chuanhu-chatbot')?.textContent.includes('slow mobile C') && JSON.parse(document.querySelector('[data-model-capabilities]')?.dataset.modelCapabilities||'{}').task_generation && document.querySelector('#history-select-dropdown label.selected'));
                const c=await page.locator("#history-select-dropdown label.selected").textContent();
                await page.evaluate(c=>window.capturedHistory={c,caps:document.querySelector('[data-model-capabilities]')?.dataset.modelCapabilities,body:document.querySelector('#chuanhu-chatbot')?.textContent,radio:document.querySelector('#history-select-dropdown')?.innerHTML},c);
                phase='new D';await page.locator("#new-chat-btn").click();
                await page.waitForFunction(()=>document.querySelectorAll("#chuanhu-chatbot .message.bot").length===0);
                phase='submit D';await composer.fill("slow mobile D");await page.locator("#submit-btn").click();await busy();
                await page.waitForFunction(()=>document.querySelector('#chuanhu-chatbot')?.textContent.includes('slow mobile D') && document.querySelectorAll('#history-select-dropdown label[data-testid]').length===2);
                const d=await page.locator('#history-select-dropdown label.selected').textContent();
                await page.evaluate(()=>{window.historyDebug=[];document.addEventListener('click',e=>window.historyDebug.push({trusted:e.isTrusted,tag:e.target.tagName,value:e.target.value,label:e.target.closest('label')?.textContent}),true);const old=window.chuanhuHistorySelection;window.chuanhuHistorySelection=x=>{const result=old(x);window.historyDebug.push({filename:x,result});return result;};});
                phase='switch C';await page.locator('#chuanhu-menu-btn').click();await page.getByTestId(c.trim()+'-radio-label').click();
                await page.waitForFunction(()=>document.querySelector("#chuanhu-chatbot")?.textContent.includes("slow mobile C"));
                await page.locator('#chuanhu-menu-btn').click();phase='loader C';await page.waitForSelector("#chuanhu-chatbot .generating-loader");
                phase='stop C';await page.locator("#cancel-btn").click();
                await page.waitForFunction(()=>document.querySelector("#chuanhu-chatbot")?.textContent.includes("模拟任务已停止"));
                await page.waitForFunction(()=>JSON.parse(document.querySelector("[data-model-capabilities]")?.dataset.modelCapabilities||"{}").turn_terminal===true);
                const terminalAt=Date.now();await page.waitForFunction(()=>{const button=document.querySelector('#submit-btn');return button && !button.hidden && !button.classList.contains('hidden') && JSON.parse(document.querySelector('[data-model-capabilities]')?.dataset.modelCapabilities||'{}').busy===false;},null,{timeout:2500});
                const agentSendReadyAt=Date.now();console.log('LIFECYCLE AGENT_TERMINAL_TO_SEND_MS',agentSendReadyAt-terminalAt);
                phase='rapid latest D';await page.locator('#chuanhu-menu-btn').click();
                for(const name of [d,c,d]) await page.getByTestId(name.trim()+'-radio-label').click();
                await page.waitForFunction(()=>document.querySelector('#chuanhu-chatbot')?.textContent.includes('slow mobile D'));
                let current=d;
                for(const key of ['ArrowUp','ArrowDown','ArrowLeft','ArrowRight']) {
                    phase='keyboard '+key;
                    await page.getByTestId(current.trim()+'-radio-label').locator('input').focus();
                    await page.keyboard.press(key);
                    current=current===d?c:d;
                    const expected=current===d?'slow mobile D':'slow mobile C';
                    await page.waitForFunction(expected=>document.querySelector('#chuanhu-chatbot')?.textContent.includes(expected),expected);
                }
                for(const key of ['Space','Enter']) {
                    phase='keyboard '+key;
                    await page.getByTestId(current.trim()+'-radio-label').locator('input').focus();
                    await page.keyboard.press(key);
                    await page.waitForFunction(()=>document.querySelector('#chuanhu-chatbot')?.textContent.includes('slow mobile D'));
                }
                phase='pending selection then New';
                await page.getByTestId(c.trim()+'-radio-label').click();
                await page.locator('#chuanhu-menu-btn').click();
                await page.locator('#new-chat-btn').click();
                await page.waitForFunction(()=>document.querySelectorAll('#chuanhu-chatbot .message.bot').length===0 && document.querySelectorAll('#history-select-dropdown label.selected').length===0);
                await page.waitForTimeout(700);
                if(await page.locator('#history-select-dropdown label.selected').count()) throw Error('Old pending selection revived after New');
                if(errors.length) throw Error(JSON.stringify(errors));
                return {terminalAt,agentSendReadyAt,deltaMs:agentSendReadyAt-terminalAt};
                } catch(error) {throw Error(phase+': '+error.message+' '+await page.evaluate(()=>JSON.stringify({caps:document.querySelector('[data-model-capabilities]')?.dataset.modelCapabilities,body:document.querySelector('#chuanhu-chatbot')?.textContent,historyDebug:window.historyDebug,capturedHistory:window.capturedHistory})));}
            }'''
            result = subprocess.run([cli,'-s='+session,'run-code',code],cwd=tmp_path,capture_output=True,text=True,timeout=100)
            if '### Error' in result.stdout:
                subprocess.run([cli,'-s='+session,'screenshot','--filename='+str(tmp_path/'failed.png')],cwd=tmp_path,capture_output=True,timeout=20)
                subprocess.run([cli,'-s='+session,'snapshot'],cwd=tmp_path,capture_output=True,text=True,timeout=20)
            (tmp_path/'browser-result.txt').write_text(result.stdout+result.stderr)
            print('LIFECYCLE MOBILE EVIDENCE',str(tmp_path),result.stdout)
            assert result.returncode==0 and '### Error' not in result.stdout, result.stdout+result.stderr+(tmp_path/'server.log').read_text()
        finally:
            subprocess.run([cli,'-s='+session,'close'],cwd=tmp_path,capture_output=True,timeout=20)
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()
