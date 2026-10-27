const fs=require('fs'),vm=require('vm'),assert=require('assert');
const handlers={};let conversation='a',changes=0;
const text={value:'original',dispatchEvent:()=>changes++};
const network={checked:true,dispatchEvent:()=>changes++};
const document={readyState:'complete',documentElement:{},addEventListener:(name,fn)=>handlers[name]=fn,
 querySelector:selector=>selector==='#user-input-tb textarea'?text:selector==='#agent-network-access input[type=checkbox]'?network:null};
const window={chuanhuInputConversation:()=>conversation,chuanhuDraftEditRevision:0};
vm.runInNewContext(fs.readFileSync('web_assets/javascript/agent-inputs.js','utf8'),{document,window,Event:class{},MutationObserver:class{observe(){}}});
const pending=(value='original',revision=window.chuanhuDraftEditRevision)=>window.chuanhuAgentPendingDraft={conversation,text:value,revision};
const receipt=(token,value='original',owner=conversation)=>({token,text:value,conversation:owner});
pending();window.chuanhuClearSubmittedDraft(null);assert.strictEqual(text.value,'original');
// A new edit between submit and acknowledgement is never overwritten.
text.value='new draft';handlers.input({target:{matches:()=>true}});
window.chuanhuClearSubmittedDraft(receipt('one'));assert.strictEqual(text.value,'new draft');
// Even editing back to the same bytes is a newer draft, not permission to clear.
text.value='original';pending('original',0);window.chuanhuClearSubmittedDraft(receipt('two'));assert.strictEqual(text.value,'original');
// A genuinely unchanged acknowledged draft clears once.
pending();window.chuanhuClearSubmittedDraft(receipt('three'));assert.strictEqual(text.value,'');assert.strictEqual(changes,1);
text.value='original';pending();window.chuanhuClearSubmittedDraft(receipt('three'));assert.strictEqual(text.value,'original');
// Reset/history/model intent clears the pending client record; late replies do nothing.
window.chuanhuAgentPendingDraft=null;window.chuanhuClearSubmittedDraft(receipt('four'));assert.strictEqual(text.value,'original');
pending();conversation='b';window.chuanhuClearSubmittedDraft(receipt('five','original','a'));assert.strictEqual(text.value,'original');
// Chat commands echo only into the same current config revision, once.
window.chuanhuAgentToolRevision=2;
window.chuanhuApplyToolPatch({token:'old',conversation:'b',revision:1,network:false});assert(network.checked);
window.chuanhuApplyToolPatch({token:'different',conversation:'a',revision:2,network:false});assert(network.checked);
window.chuanhuApplyToolPatch({token:'current',conversation:'b',revision:2,network:false});assert.strictEqual(network.checked,false);assert.strictEqual(changes,2);
network.checked=true;window.chuanhuApplyToolPatch({token:'current',conversation:'b',revision:2,network:false});assert(network.checked);
console.log('Draft acknowledgement editing/conversation guards and versioned local tool echo passed');
