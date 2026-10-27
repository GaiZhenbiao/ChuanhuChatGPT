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


def test_background_new_switch_reload_files_and_targeted_stop(tmp_path):
    cli = os.environ.get('CHUANHU_PLAYWRIGHT_CLI') or shutil.which('playwright-cli')
    if not cli:
        pytest.skip('Set CHUANHU_PLAYWRIGHT_CLI for real browser regression')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    session = 'fast-history-' + str(port)
    with (tmp_path/'server.log').open('w') as log:
        server = subprocess.Popen([sys.executable, 'tests/main_chat_preview.py', '--port', str(port)],
                                  cwd=ROOT, stdout=log, stderr=log, env=dict(os.environ, GRADIO_ANALYTICS_ENABLED='False'))
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
                let phase="choose agent";try {
                const composer=page.getByPlaceholder("在这里输入",{exact:true});
                const caps=()=>JSON.parse(document.querySelector("[data-model-capabilities]")?.dataset.modelCapabilities||"{}");
                const waitBusy=()=>page.waitForFunction(()=>JSON.parse(document.querySelector("[data-model-capabilities]")?.dataset.modelCapabilities||"{}").busy===true);
                const waitTerminal=()=>page.waitForFunction(()=>JSON.parse(document.querySelector("[data-model-capabilities]")?.dataset.modelCapabilities||"{}").turn_terminal===true);
                const label=()=>page.locator("#history-select-dropdown input:checked").locator("..").textContent();
                const open=async name=>{await page.locator("#history-select-dropdown label").filter({hasText:name.trim()}).click();};
                const fresh=async()=>{await page.locator("#new-chat-btn").click();await page.waitForFunction(()=>document.querySelectorAll("#chuanhu-chatbot .message.bot").length===0);};
                await page.getByRole("listbox",{name:"选择模型",exact:true}).click();
                await page.getByRole("option",{name:"OpenAI Agent",exact:true}).click();
                await page.waitForFunction(()=>JSON.parse(document.querySelector("[data-model-capabilities]")?.dataset.modelCapabilities||"{}").agent_tools===true);
                phase="submit A";await composer.fill("slow files background A");await composer.press("Enter");await waitBusy();
                await page.waitForFunction(()=>document.querySelectorAll("#history-select-dropdown input:checked").length===1);
                const a=await label();
                phase="submit B";await fresh();await composer.fill("background B");await page.locator("#submit-btn").click();await waitTerminal();
                const b=await label();
                if(!(await page.locator("#chuanhu-chatbot").textContent()).includes("模拟 Agent 回答：background B"))throw Error("B answer missing");
                phase="switch A busy";await open(a);await waitBusy();
                if(!(await page.locator("#chuanhu-chatbot").textContent()).includes("slow files background A"))throw Error("A not restored");
                phase="reload";await page.reload();
                await page.waitForFunction(()=>document.querySelectorAll("#history-select-dropdown label").length>=2);
                phase="reload A terminal";await open(a);await page.waitForFunction(()=>document.querySelector("#chuanhu-chatbot")?.textContent.includes("模拟 Agent 回答：slow files background A"));await waitTerminal();
                const body=await page.locator("#chuanhu-chatbot").textContent();
                if(!body.includes("模拟 Agent 回答：slow files background A")||body.includes("模拟 Agent 回答：background B"))throw Error("A background result mixed");
                if(await page.locator("#agent-artifact-list").count())await page.waitForFunction(()=>document.querySelector("#agent-artifact-list")?.textContent.includes("synthetic"));
                phase="switch B terminal";await open(b);await page.waitForFunction(()=>document.querySelector("#chuanhu-chatbot")?.textContent.includes("模拟 Agent 回答：background B"));await waitTerminal();
                phase="submit C";await fresh();await composer.fill("slow background C");await page.locator("#submit-btn").click();await waitBusy();
                await page.waitForFunction(()=>document.querySelectorAll("#history-select-dropdown input:checked").length===1);const c=await label();
                phase="submit D";await fresh();await composer.fill("slow background D");await page.locator("#submit-btn").click();await waitBusy();
                await page.waitForFunction(()=>document.querySelectorAll("#history-select-dropdown input:checked").length===1);const d=await label();
                phase="stop C";await open(c);await page.waitForFunction(()=>document.querySelector("#chuanhu-chatbot")?.textContent.includes("slow background C"));await waitBusy();await page.locator("#cancel-btn").click();await waitTerminal();await page.waitForFunction(()=>document.querySelector("#chuanhu-chatbot")?.textContent.includes("模拟任务已停止"));
                if(!(await page.locator("#chuanhu-chatbot").textContent()).includes("模拟任务已停止"))throw Error("C stop missing");
                phase="switch D";await open(d);await page.waitForFunction(()=>document.querySelector("#chuanhu-chatbot")?.textContent.includes("slow background D"));await waitBusy();
                if((await page.locator("#chuanhu-chatbot").textContent()).includes("模拟任务已停止"))throw Error("D cancelled by C Stop");
                await page.locator("#cancel-btn").click();await waitTerminal();
                console.log("BACKGROUND_CONTINUOUS_QA_OK");
                } catch(e) {throw Error(phase+": "+e.message);}
            }'''
            result = subprocess.run([cli,'-s='+session,'run-code',code],cwd=tmp_path,capture_output=True,text=True,timeout=100)
            if '### Error' in result.stdout:
                subprocess.run([cli,'-s='+session,'screenshot','--filename='+str(tmp_path/'failed.png')],cwd=tmp_path,capture_output=True,timeout=20)
                subprocess.run([cli,'-s='+session,'snapshot'],cwd=tmp_path,capture_output=True,text=True,timeout=20)
            assert result.returncode==0 and '### Error' not in result.stdout, result.stdout+result.stderr+(tmp_path/'server.log').read_text()
        finally:
            subprocess.run([cli,'-s='+session,'close'],cwd=tmp_path,capture_output=True,timeout=20)
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()
