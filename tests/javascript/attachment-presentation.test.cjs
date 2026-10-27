// Actual submission JS, draft guard and card projection; no browser geometry claim.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const payload=JSON.parse(fs.readFileSync(0,'utf8'));
const helper=fs.readFileSync('tests/javascript/message-actions.test.cjs','utf8');
const start=helper.indexOf('const escape ='),end=helper.indexOf('\nfunction fixture(');
const context=vm.createContext({assert,Buffer});vm.runInContext(helper.slice(start,end),context);
const dom=vm.runInContext('createDOM()',context),document=dom.document;
const element=(tag,attrs={})=>{const n=document.createElement(tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);return n};
const textarea=element('textarea');textarea.value=payload.draft.text;
const textroot=element('div',{id:'user-input-tb'});textroot.append(textarea);
const composer=element('div',{id:'chatbot-input-tb-row'}),native=element('div',{id:'agent-pending-files'});
const label=element('span',{'data-testid':'block-label'});label.textContent=payload.before_label;native.append(label);
document.body.append(textroot,composer,native);
// The fixture supplies a fragment stand-in; the real card script runs unchanged.
textarea.constructor.prototype.prepend=function(node){this.appendChild(node);this.childNodes.unshift(this.childNodes.pop());};
const simpleMatches=textarea.constructor.prototype.matches;
textarea.constructor.prototype.matches=function(selector){
 if(!selector.includes(' '))return simpleMatches.call(this,selector);
 const parts=selector.trim().split(/\s+/);
 if(!simpleMatches.call(this,parts.pop()))return false;
 let parent=this.parentElement;
 while(parts.length){const part=parts.pop();while(parent&&!simpleMatches.call(parent,part))parent=parent.parentElement;if(!parent)return false;parent=parent.parentElement;}
 return true;
};
Object.defineProperty(textarea.constructor.prototype,'content',{get(){return this;}});
const window={chuanhuInputConversation:()=>payload.draft.conversation,chuanhuInputBusy:()=>false,chuanhuDraftEditRevision:0};
Object.assign(context,{window,document,gradioApp:()=>document,Event:class{constructor(type,options){this.type=type;Object.assign(this,options);}},MutationObserver:dom.MutationObserver,queueMicrotask:f=>dom.microtasks.push(f),requestAnimationFrame:f=>dom.frames.push(f)});
vm.runInContext(fs.readFileSync('web_assets/javascript/agent-inputs.js','utf8'),context);
vm.runInContext(fs.readFileSync('web_assets/javascript/attachment-cards.js','utf8'),context);dom.flush();
const submit=vm.runInContext('('+payload.entry+')',context);
const capture=text=>submit(text,null,'gpt-6.1-sol','default',0,[],...Array(14).fill(null));
assert(composer.querySelector('.agent-input-card'),'Real card renderer must mount the submitted attachment');
capture(payload.draft.text);
label.textContent=payload.file_update.label;window.chuanhuClearSubmittedDraft(payload.draft);dom.flush();
assert.equal(textarea.value,'');assert.equal(composer.querySelector('.agent-pending-cards').hidden,true);
textarea.value=payload.draft.text;capture(payload.draft.text);textarea.value='new draft';
textarea.dispatchEvent(new context.Event('input',{bubbles:true}));
const newMetadata=JSON.parse(payload.before_label);newMetadata.files[0].id='new-stable-id';newMetadata.ids=['new-stable-id'];
label.textContent=JSON.stringify(newMetadata);window.chuanhuClearSubmittedDraft({...payload.draft,token:'second'});dom.flush();
assert.equal(textarea.value,'new draft');assert.equal(composer.querySelector('.agent-pending-cards').hidden,false);
assert.equal(composer.querySelector('.agent-input-remove-card').dataset.inputId,'new-stable-id');
// Editing back to the exact submitted bytes remains a new revision.
capture(payload.draft.text);textarea.value='edit';textarea.dispatchEvent(new context.Event('input',{bubbles:true}));
textarea.value=payload.draft.text;textarea.dispatchEvent(new context.Event('input',{bubbles:true}));
window.chuanhuClearSubmittedDraft({...payload.draft,token:'third'});assert.equal(textarea.value,payload.draft.text);
console.log('Production draft receipt clears text and submitted card; newer text/file and equal-byte edits survive.');
