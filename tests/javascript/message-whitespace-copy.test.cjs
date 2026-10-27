// Exact source checks use real projection, formatter and Copy/Toggle handlers.
const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert/strict');
const source=fs.readFileSync('tests/javascript/message-actions.test.cjs','utf8');
const context=vm.createContext({require,__dirname:path.join(process.cwd(),'tests/javascript'),Buffer,TextDecoder,process});
vm.runInContext(source.slice(0,source.indexOf('\nconst tests = [];'))+'\nglobalThis.makeFixture=fixture;globalThis.inputPayload=payload;',context);
const payload=context.inputPayload;
(async()=>{
 for(const mode of ['valid','missing','bad','foreign','v2']){
  const f=context.makeFixture();f.refresh();const bubble=f.bubble(f.rows()[0]);
  const activity=Array.from(bubble.querySelectorAll('.agent-history-detail'));
  activity.forEach((node,index)=>{node.open=Boolean(index%2);});
  const parents=activity.map(node=>node.parentElement),opened=activity.map(node=>node.open);
  const visible=f.context.agentBodySegments(bubble),sources=f.context.agentBodySources(bubble);
  assert.equal(visible.length,payload.visibleCount);assert.equal(sources.length,payload.sourceCount);
  assert.equal(bubble.querySelectorAll('.agent-body-copy-source').length,payload.whitespaceCount);
  for(const receipt of bubble.querySelectorAll('.agent-body-copy-source')){
   assert.equal(receipt.getAttribute('hidden'),'hidden');assert.equal(receipt.childNodes.length,0);
  }
  const anchor=bubble.querySelector('.agent-message-anchor');
  if(mode==='missing')anchor.remove();
  else if(mode==='bad')anchor.dataset.agentMessageRaw='invalid';
  else if(mode!=='valid'){
   const full=JSON.parse(Buffer.from(anchor.dataset.agentMessageRaw,'base64'));
   if(mode==='foreign')full.conversation='foreign';else full.v=2;
   anchor.dataset.agentMessageRaw=Buffer.from(JSON.stringify(full)).toString('base64');
  }
  for(let toggle=0;toggle<3;toggle++){
   bubble.querySelector('.copy-bot-btn').click();await Promise.resolve();f.dom.flush();
   assert.equal(f.copied.at(-1),payload.raw,'Canonical body bytes must survive '+mode+' suffix');
   bubble.querySelector('.toggle-md-btn').click();f.dom.flush();
   assert.deepEqual(Array.from(bubble.querySelectorAll('.agent-history-detail')),activity);
   assert.deepEqual(activity.map(node=>node.parentElement),parents);assert.deepEqual(activity.map(node=>node.open),opened);
  }
 }
 if(payload.whitespaceCount){
  const f=context.makeFixture();f.refresh();const bubble=f.bubble(f.rows()[0]);bubble.querySelector('.agent-message-anchor').remove();
  bubble.querySelector('.agent-body-copy-source').dataset.agentBodyRaw='invalid';
  bubble.querySelector('.copy-bot-btn').click();await Promise.resolve();assert.equal(f.copied.length,0,'Broken hidden source cannot produce partial text');
 }
 console.log('Production exact whitespace copy passed: '+payload.raw.length+' characters, '+payload.sourceCount+' body sources, '+payload.visibleCount+' visible pairs.');
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
