const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert/strict');
const source=fs.readFileSync('tests/javascript/message-actions.test.cjs','utf8');
const prefix=source.slice(0,source.indexOf('\nconst tests = [];'));
const context=vm.createContext({require,__dirname:path.join(process.cwd(),'tests/javascript'),Buffer,TextDecoder,process});
vm.runInContext(prefix+'\nglobalThis.makeFixture=fixture;globalThis.inputPayload=payload;',context);
const payload=context.inputPayload;
const copyExact=async(f,expected)=>{f.bubble(f.rows()[0]).querySelector('.copy-bot-btn').click();await Promise.resolve();f.dom.flush();assert.equal(f.copied.at(-1),expected);};
const bodies=f=>f.context.agentBodySegments(f.bubble(f.rows()[0]));
(async()=>{
 const f=context.makeFixture();f.refresh();
 f.context.performance={now:()=>0};vm.runInContext(fs.readFileSync('web_assets/javascript/agent-activity.js','utf8'),f.context);f.dom.flush();
 const bubble=f.bubble(f.rows()[0]),activity=Array.from(bubble.querySelectorAll('.agent-history-detail'));
 assert.equal(bodies(f).length,3);assert(activity.length>=3);
 for(const node of activity){node.open=true;node.setAttribute('open','');}
 f.dom.flush();
 const timers=Array.from(bubble.querySelectorAll('.agent-activity-elapsed'));assert.equal(timers.length,2);
 const timerState=timers.map(n=>[n.textContent,n.dataset.elapsedMs,n.dataset.running]);
 for(let round=0;round<3;round++){
  bubble.querySelector('.toggle-md-btn').click();f.dom.flush();
  assert(bodies(f).every(n=>!n.querySelector('.raw-message').classList.contains('hideM')&&n.querySelector('.md-message').classList.contains('hideM')));
  assert.deepEqual(Array.from(bubble.querySelectorAll('.agent-history-detail')),activity);assert(activity.every(n=>n.open));
  assert.deepEqual(timers.map(n=>[n.textContent,n.dataset.elapsedMs,n.dataset.running]),timerState);
  await copyExact(f,payload.raw);
  bubble.querySelector('.toggle-md-btn').click();f.dom.flush();
  assert(bodies(f).every(n=>n.querySelector('.raw-message').classList.contains('hideM')&&!n.querySelector('.md-message').classList.contains('hideM')));
 }
 bubble.querySelector('.toggle-md-btn').click();f.dom.flush();
 // Streaming replacement keeps the message mode and each activity's own open
 // state. No toggle recreates activity, summary, timer or body markup.
 f.replace(payload.appended);f.refresh();
 assert.equal(bodies(f).length,4);assert(bodies(f).every(n=>n.querySelector('.md-message').classList.contains('hideM')));
 assert(f.bubble(f.rows()[0]).querySelectorAll('.agent-history-detail').every(n=>n.open));
 await copyExact(f,payload.appendedRaw);
 f.replace(payload.initial);f.refresh();assert(bodies(f).every(n=>n.querySelector('.md-message').classList.contains('hideM')));
 for(const corrupt of ['missing','bad','foreign']){
  const item=context.makeFixture();item.refresh();const anchor=item.bubble(item.rows()[0]).querySelector('.agent-message-anchor');
  if(corrupt==='missing')anchor.remove();else if(corrupt==='bad')anchor.dataset.agentMessageRaw='invalid';else{const p=JSON.parse(Buffer.from(anchor.dataset.agentMessageRaw,'base64'));p.conversation='foreign';anchor.dataset.agentMessageRaw=Buffer.from(JSON.stringify(p)).toString('base64');}
  await copyExact(item,payload.raw);
 }
 const legacy=context.makeFixture({snapshot:{...payload.initial,rows:[[null,payload.legacyCompound]]}});legacy.refresh();await copyExact(legacy,payload.legacyExpected);
 const broken=context.makeFixture();broken.refresh();const b=broken.bubble(broken.rows()[0]);b.querySelector('.agent-message-anchor').remove();b.querySelector('.agent-body-segment').dataset.agentBodyRaw='bad';
 b.querySelector('.copy-bot-btn').click();await Promise.resolve();assert.equal(broken.copied.length,0,'Invalid body sources never copy a partial or guessed message');
 console.log('Interleaved body modes and exact copy passed: 3/4 bodies, activity identity/open/timing, streaming, restore, malformed suffix, legacy multi-body.');
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
