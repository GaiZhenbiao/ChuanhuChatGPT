const fs=require('fs'),vm=require('vm'),assert=require('assert');
let target='#agent-upload-files',busy=false,selected=[],events=0;
const input={disabled:false,files:[],dispatchEvent:()=>events++};
class DataTransfer { constructor(){this.files=[];this.items={add:file=>this.files.push(file)};} }
const context={window:{chuanhuSupports:()=>true,chuanhuInputBusy:()=>busy,chuanhuInputTarget:()=>target},
    gradioApp:()=>({querySelector:selector=>{selected.push(selector);return input;}}),DataTransfer,Event:class {}};
vm.createContext(context);vm.runInContext(fs.readFileSync('web_assets/javascript/file-input.js','utf8'),context);
(async()=>{
    await context.upload_files([{name:'one.png'}]);await context.upload_files([{name:'two.png'}]);
    assert.strictEqual(input.files[0].name,'two.png');assert.strictEqual(events,2);
    assert(selected.every(selector=>selector==='#agent-upload-files input[type=file]'));
    busy=true;await context.upload_files([{name:'blocked'}]);assert.strictEqual(events,2);
    busy=false;target='#upload-index-file';await context.upload_files([{name:'ordinary.pdf'}]);
    assert.strictEqual(selected.at(-1),'#upload-index-file input[type=file]');
    let change,mutated,current='original',error=false,progress=false;
    const errorNode={};
    const document={readyState:'complete',documentElement:{},addEventListener:(name,fn)=>{if(name==='change')change=fn;},
        querySelector:selector=>selector.endsWith('.error')?(error?errorNode:null):selector.endsWith('.uploading')?(progress?{}:null):null};
    const window={chuanhuInputConversation:()=>current};
    vm.runInNewContext(fs.readFileSync('web_assets/javascript/agent-inputs.js','utf8'),
        {document,window,MutationObserver:class{constructor(fn){mutated=fn;}observe(){}}});
    change({composedPath:()=>[{matches:()=>true,files:[{}]}]});current='another-conversation';
    assert.strictEqual(window.chuanhuAgentUploadTarget,'original');assert(window.chuanhuAgentUploading);
    let prevented=false,stopped=false;
    const recreated={matches:()=>true,files:[{}],value:'second-batch'};
    change({composedPath:()=>[recreated],preventDefault:()=>prevented=true,stopImmediatePropagation:()=>stopped=true});
    assert(prevented&&stopped);assert.strictEqual(recreated.value,'');
    assert.strictEqual(window.chuanhuAgentUploadTarget,'original');
    error=true;mutated();assert.strictEqual(window.chuanhuAgentUploading,false);
    change({composedPath:()=>[{matches:()=>true,files:[{}]}]});
    assert.strictEqual(window.chuanhuAgentUploadTarget,'another-conversation');
    mutated();assert(window.chuanhuAgentUploading); // Old error cannot unlock a new retry.
    progress=true;mutated();assert(window.chuanhuAgentUploading);
    progress=false;mutated();assert.strictEqual(window.chuanhuAgentUploading,false);
    let handlers={},payload={value:'',dispatchEvent(){}},clicks=0,preventedDelete=0;
    const rows=[{},{}],preview={querySelector:()=>({textContent:JSON.stringify({target:'visible-chat',ids:['first','second']})}),querySelectorAll:()=>rows};
    const remove={matches:selector=>selector==='button'||selector==='.label-clear-button',closest:selector=>selector==='#agent-pending-files'?preview:rows[0]};
    const clear={matches:selector=>selector==='button',closest:selector=>selector==='#agent-pending-files'?preview:null};
    const deleteDoc={readyState:'complete',documentElement:{},addEventListener:(name,fn)=>handlers[name]=fn,
        querySelector:selector=>selector.includes('textarea')?payload:selector==='#agent-input-remove'?{click:()=>clicks++}:null};
    const deleteWindow={};
    vm.runInNewContext(fs.readFileSync('web_assets/javascript/agent-inputs.js','utf8'),
        {document:deleteDoc,window:deleteWindow,MutationObserver:class{observe(){}},Event:class{},requestAnimationFrame:fn=>fn()});
    const removal=(button,type='click',key)=>({type,key,composedPath:()=>[button],preventDefault:()=>preventedDelete++,stopImmediatePropagation(){}});
    handlers.click(removal(remove));
    assert.deepStrictEqual(JSON.parse(payload.value),{target:'visible-chat',ids:['first']});
    handlers.keydown(removal(clear,'keydown','Enter'));
    assert.deepStrictEqual(JSON.parse(payload.value),{target:'visible-chat',ids:['first','second']});
    assert.strictEqual(clicks,2);assert.strictEqual(preventedDelete,2);
    deleteWindow.chuanhuAgentUploading=true;handlers.click(removal(clear));assert.strictEqual(clicks,2);
    console.log('Input routing, repeated paste, busy guard, captured conversation and upload error passed');
})().catch(error=>{console.error(error);process.exit(1);});
