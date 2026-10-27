// Execute actual elapsed UI script with deterministic clock and owned DOM nodes.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('web_assets/javascript/agent-activity.js','utf8');
function fixture({ready='complete',conversation='chat',nodes=[],details=[],scroller=null}={}) {
    let now=0,active=conversation,next=0;const intervals=new Map(),observers=[],listeners=new Map();
    const app={querySelector:()=>typeof scroller==='function'?scroller():scroller,querySelectorAll:selector=>selector.endsWith('.agent-history-detail')?details:nodes};
    const document={readyState:ready,documentElement:{},addEventListener:(event,fn)=>listeners.set(event,fn),removeEventListener:(event,fn)=>{if(listeners.get(event)===fn)listeners.delete(event);}};
    const context={document,gradioApp:()=>app,performance:{now:()=>now},chuanhuInputConversation:()=>active,
        setInterval:fn=>{intervals.set(++next,fn);return next;},clearInterval:key=>intervals.delete(key),
        MutationObserver:class {constructor(fn){this.fn=fn;observers.push(this);}observe(target,options){this.observing=true;this.options=options;}takeRecords(){const records=this.pending||[];this.pending=[];return records;}disconnect(){this.observing=false;}}};
    vm.createContext(context);const start=()=>vm.runInContext(source,context);
    const notify=(records=[])=>observers.filter(observer=>observer.observing).forEach(observer=>observer.fn(records));
    return {context,start,notify,intervals,listeners,observers,setTime:value=>{now=value;},setConversation:value=>{active=value;},tick:()=>Array.from(intervals.values()).forEach(fn=>fn())};
}
function node(base=1000,running=true,conversation='chat',clone=false){
    const detail={dataset:{conversationId:conversation,layer:'group'},closest:selector=>selector==='.history-message'&&clone?{}:null};
    let text=Math.floor(base/1000)+'s',writes=0;
    return {dataset:{elapsedMs:String(base),running:String(running)},get textContent(){return text;},set textContent(value){text=value;writes++;},get writes(){return writes;},closest:()=>detail};
}
const live=node(),f=fixture({nodes:[live]});f.start();assert.equal(f.intervals.size,1);
f.setTime(500);f.tick();assert.equal(live.textContent,'1s');f.notify();f.setTime(1000);f.tick();assert.equal(live.textContent,'2s','DOM mutations do not restart clocks');
live.dataset.elapsedMs='2200';f.notify();assert.equal(live.textContent,'2s');f.setTime(1500);f.tick();assert.equal(live.textContent,'2s','fresh owner observation replaces baseline');
f.start();assert.equal(f.observers.length,1,'same script version does not duplicate observers');f.setTime(1700);f.tick();assert.equal(live.textContent,'2s','same version reload preserves elapsed clock');
live.dataset.running='false';live.textContent='2s';f.notify();f.setTime(2000);f.tick();assert.equal(live.textContent,'2s');assert.equal(f.intervals.size,0,'completed observation stays frozen');
const stale=node(),g=fixture({nodes:[stale]});g.start();g.setConversation('other');g.setTime(1000);g.tick();assert.equal(stale.textContent,'1s');assert.equal(g.intervals.size,0,'navigation stops stale clocks');
for(const value of [-1,NaN,Infinity,31536000001]){const bad=node(value),h=fixture({nodes:[bad]});h.start();assert.equal(h.intervals.size,0);}
const cloned=node(1000,true,'chat',true),foreign=node(1000,true,'other');const h=fixture({nodes:[cloned,foreign]});h.start();assert.equal(h.intervals.size,0);
const deferred=node(),j=fixture({ready:'loading',nodes:[deferred]});j.start();assert.equal(j.intervals.size,0);j.listeners.get('DOMContentLoaded')();assert.equal(j.intervals.size,1);
j.context.__chuanhuActivityCleanup();assert.equal(j.intervals.size,0);assert(!j.observers[0].observing);
console.log('Elapsed activity: running, mutation, owner baseline, reload, completion, stale visit, invalid metadata, cloned history and cleanup passed');

const detail={dataset:{conversationId:'chat',activityKey:'step'},open:false,closest:()=>null,matches:()=>true};
const details=[detail],kept=fixture({details});kept.start();detail.open=true;kept.listeners.get('toggle')({target:detail});
const completed={...detail,open:false};details[0]=completed;
kept.notify();assert.equal(completed.open,true,'expanded tool remains open after completion DOM replacement');
completed.open=false;kept.listeners.get('toggle')({target:completed});details[0]={...completed,open:true};kept.notify();assert.equal(details[0].open,false,'explicit collapsed state survives running default open');
const foreignDetail={...completed,dataset:{conversationId:'other',activityKey:'step'},open:false};details[0]=foreignDetail;kept.notify();assert.equal(foreignDetail.open,false,'other conversation cannot inherit expanded state');
kept.context.__chuanhuActivityCleanup();assert(!kept.listeners.has('toggle'));
console.log('Activity expansion survives completion and explicit collapse, scoped to conversation');
// Both layers retain choices separately; unstable display occurrences do not.
function ownedDetail(key,layer='tool',persist='true',conversation='chat') {
 return {dataset:{conversationId:conversation,scopeId:'scope',turnId:'t1',activityKey:key,layer,persistOpen:persist},open:false,closest:()=>null,matches:()=>true};
}
const group=ownedDetail('boundary','group'),child=ownedDetail('child'),uncertain=ownedDetail('','tool','false');
const layers=[group,child,uncertain],k=fixture({details:layers});k.start();
for(const detail of layers){detail.open=true;k.listeners.get('toggle')({target:detail});}
layers[0]=ownedDetail('boundary','group');layers[1]=ownedDetail('child');layers[2]=ownedDetail('','tool','false');k.notify();
assert(layers[0].open&&layers[1].open);assert(!layers[2].open,'unresolved snapshot never inherits expansion');
const unstableGroup=ownedDetail('boundary','group','false');layers[0]=unstableGroup;layers[1]=ownedDetail('child');k.notify();
assert(!unstableGroup.open&&layers[1].open,'reliable child remains remembered under non-persistent group');
unstableGroup.open=true;k.listeners.get('toggle')({target:unstableGroup});layers[0]=ownedDetail('new-unresolved','group','false');k.notify();assert(!layers[0].open);
layers[0]=ownedDetail('new-boundary','group');layers[1]=ownedDetail('child');k.notify();assert(!layers[0].open&&layers[1].open,'split group does not blindly inherit, child follows its canonical identity');
layers[0]=ownedDetail('boundary','group','true','other');k.setConversation('other');k.notify();assert(!layers[0].open,'A/B choices do not cross conversation');
layers[0]=ownedDetail('boundary','group');k.setConversation('chat');k.notify();assert(layers[0].open,'A restores its own choice');
console.log('Two layers, regroup, unresolved snapshots and A/B expansion isolation passed');

// Native toggle is asynchronous: DOM changes before callback, stream or timer.
for (const layer of ['group','tool']) {
 for (const initial of [false,true]) {
  const old=ownedDetail('race-'+initial,layer);old.open=initial;
  const list=[old],elapsed=node(),race=fixture({details:list,nodes:[elapsed]});race.start();
  old.open=!initial;race.notify();assert.equal(old.open,!initial,'same-node mutation never restores stale cache');
  race.tick();assert.equal(old.open,!initial,'timer never restores stale cache');
  race.listeners.get('toggle')({target:old});
  const replacement=ownedDetail('race-'+initial,layer);replacement.open=initial;list[0]=replacement;
  race.notify();assert.equal(replacement.open,!initial,'replacement restores last DOM intent');
  // Detached predecessor events and later edits must not replace new intent.
  replacement.open=initial;race.notify();old.open=!initial;
  race.listeners.get('toggle')({target:old});race.tick();assert.equal(replacement.open,initial);
  list[0]=ownedDetail('race-'+initial,layer);race.notify();assert.equal(list[0].open,initial,'new choice survives late old event');
 }
 // Replacement before the old toggle/mutation callback still captures old DOM.
 const old=ownedDetail('early-replace',layer),list=[old],race=fixture({details:list});race.start();
 old.open=true;list[0]=ownedDetail('early-replace',layer);race.notify();assert(list[0].open);
 race.listeners.get('toggle')({target:old});assert(list[0].open);
 // A new DOM user choice before its first observer callback wins old cache.
 const newer=ownedDetail('early-replace',layer);list[0]=newer;
 race.notify([{type:'attributes',attributeName:'open',target:newer}]);assert(!newer.open);
 // Same case with timer draining native attribute records ahead of observer.
 const newest=ownedDetail('early-replace',layer);newest.open=true;list[0]=newest;
 race.observers[0].pending=[{type:'attributes',attributeName:'open',target:newest}];race.notify();assert(newest.open);
 // A subsequent stream replacement carries precisely that most recent choice.
 list[0]=ownedDetail('early-replace',layer);race.notify();assert(list[0].open);
}
console.log('Asynchronous outer/inner open/close, timer/mutation, pre-toggle replacement, new intent and stale events passed');

assert.equal(f.observers[0].options.attributes,true);
assert.deepEqual(Array.from(f.observers[0].options.attributeFilter),['open'],'native open mutations must be observed');

// A replacement restores before paint, with only its local transition disabled.
const restored=ownedDetail('restore-motion'),restoreList=[restored],restore=fixture({details:restoreList});
const frames=[],layouts=[];
restore.context.requestAnimationFrame=fn=>frames.push(fn);
restore.context.getComputedStyle=(detail,pseudo)=>{
 layouts.push({detail,pseudo,open:detail.open,restoring:detail.dataset.restoringOpen});
 return {height:'80px'};
};
restore.start();restored.open=true;restore.notify();
const replacement=ownedDetail('restore-motion');restoreList[0]=replacement;restore.notify();
assert(replacement.open);
assert.equal(replacement.dataset.restoringOpen,'true');
assert.equal(layouts.length,1);assert.equal(layouts[0].pseudo,'::details-content');
assert.equal(layouts[0].open,true);assert.equal(layouts[0].restoring,'true');
replacement.open=false;restore.notify();frames.shift()();
assert.equal(replacement.dataset.restoringOpen,undefined);
assert(!replacement.open,'paint cleanup never overwrites a new native choice');
restoreList[0]=ownedDetail('restore-motion');restore.notify();
assert(!restoreList[0].open);assert.equal(frames.length,0,'unchanged open requires no restoration marker');
console.log('Replacement layout resolves before paint; local restore cleanup preserves new native intent');

// Background tabs may not paint while hundreds of stream replacements arrive.
const backgroundList=[ownedDetail('background-restore')],background=fixture({details:backgroundList});
const pendingFrames=new Map();let frameId=0;
background.context.requestAnimationFrame=fn=>{pendingFrames.set(++frameId,fn);return frameId;};
background.context.cancelAnimationFrame=id=>pendingFrames.delete(id);
background.start();backgroundList[0].open=true;background.notify();
for(let i=0;i<100;i++){
 const previous=backgroundList[0];backgroundList[0]=ownedDetail('background-restore');background.notify();
 assert.equal(previous.dataset.restoringOpen,undefined,'replaced nodes retain no restore marker');
 assert(backgroundList[0].open);assert.equal(pendingFrames.size,1,'all replacements share one pending frame');
}
backgroundList[0].open=false;background.notify();
pendingFrames.values().next().value();pendingFrames.clear();
assert(!backgroundList[0].open,'shared paint never overwrites newer user intent');
assert.equal(backgroundList[0].dataset.restoringOpen,undefined);
backgroundList[0].open=true;background.notify();backgroundList[0]=ownedDetail('background-restore');background.notify();
assert.equal(pendingFrames.size,1);
background.context.__chuanhuActivityCleanup();assert.equal(pendingFrames.size,0);
assert.equal(backgroundList[0].dataset.restoringOpen,undefined,'cleanup clears the current marker and cancels paint');
console.log('100 background replacements share one frame; detached markers and cleanup references are released');

// Reliable fractions are visible below one second; intervals stay precise.
const boundary=node(999.75),precise=fixture({nodes:[boundary]});precise.start();
assert.equal(boundary.textContent,'0.9s');assert.equal(boundary.writes,1);
for(const value of [0,0.1,0.2]){precise.setTime(value);precise.notify();precise.tick();}
assert.equal(boundary.writes,1,'unchanged tenth does not rewrite text');
precise.setTime(0.25);precise.tick();assert.equal(boundary.textContent,'1s');assert.equal(boundary.writes,2);
for(const value of [100,500,999]){precise.setTime(value);precise.notify();precise.tick();}
assert.equal(boundary.writes,2,'unchanged integer second does not rewrite text');
boundary.dataset.elapsedMs='1999.9';precise.notify();assert.equal(boundary.textContent,'1s');assert.equal(boundary.writes,2);
precise.setTime(999.1);precise.tick();assert.equal(boundary.textContent,'2s');assert.equal(boundary.writes,3);
for(const [base,expected] of [[0,'0.0s'],[.1,'0.1s'],[10,'0.1s'],[100,'0.1s'],[999,'0.9s'],[1000,'1s'],[60000,'1m 0s']]){
 const live=node(base),test=fixture({nodes:[live]});test.start();assert.equal(live.textContent,expected);
 live.dataset.running='false';test.notify();test.setTime(100000);test.tick();
 assert.equal(live.textContent,expected);assert.equal(test.intervals.size,0,'terminal value stays frozen');
}
for(const base of [0,999,999.75,1000,3456.9]){
 const frozen=node(base,false),stop=fixture({nodes:[frozen]});stop.start();stop.setTime(100000);stop.notify();stop.tick();
 assert.equal(frozen.textContent,Math.floor(base/1000)+'s');assert.equal(frozen.writes,0);assert.equal(stop.intervals.size,0);
}
const missing=node();delete missing.dataset.elapsedMs;missing.textContent='unknown';const unknown=fixture({nodes:[missing]});unknown.start();unknown.setTime(2000);unknown.notify();unknown.tick();
assert.equal(missing.textContent,'unknown');assert.equal(unknown.intervals.size,0);
console.log('Subsecond floors, true zero, reliable interval precision, terminal freeze and unknown baseline passed');

// Only the outer group owns the readout, including localized minute rollover.
const minute=node(59999.75),minutes=fixture({nodes:[minute]});
minute.dataset.secondsFormat='{seconds}s';minute.dataset.minutesFormat='{minutes}分{seconds}秒';
minutes.start();assert.equal(minute.textContent,'59s');
minutes.setTime(.25);minutes.tick();assert.equal(minute.textContent,'1分0秒');assert.equal(minute.writes,1);
for(const time of [1,100,900]){minutes.setTime(time);minutes.notify();minutes.tick();}
assert.equal(minute.writes,1,'same displayed second does not rewrite localized time');
minutes.setTime(7000.25);minutes.tick();assert.equal(minute.textContent,'1分7秒');
minute.dataset.running='false';minute.textContent='1分7秒';minutes.notify();
minutes.setTime(100000);minutes.tick();assert.equal(minute.textContent,'1分7秒');assert.equal(minutes.intervals.size,0);
const childTimer=node(),childDetail=childTimer.closest();childDetail.dataset.layer='tool';
const childFixture=fixture({nodes:[childTimer]});childFixture.start();childFixture.setTime(9000);childFixture.notify();
assert.equal(childTimer.textContent,'1s');assert.equal(childFixture.intervals.size,0,'a child tool cannot run a header timer');
for(const [format,expected] of [['{minutes}m {seconds}s','1m 7s'],['{minutes}분 {seconds}초','1분 7초'],['{minutes} мин {seconds} с','1 мин 7 с']]){
 const localized=node(67999.75),test=fixture({nodes:[localized]});localized.dataset.minutesFormat=format;test.start();
 assert.equal(localized.textContent,expected);
}
console.log('Outer group only, localized 60s rollover, same-second suppression and terminal minute freeze passed');

// Model Gradio's exact beforeUpdate/afterUpdate sequence without claiming pixels.
// Its scrollHeight argument can force a collapsed layout before our hook starts.
function scrollingFixture({reader=false,top}={}) {
 const list=[ownedDetail('scroll-group','group'),ownedDetail('scroll-child')];
 list.forEach(detail=>detail.open=true);
 let heightBase=1000,scrollTop=top??(reader?900:1217),wrapper;
 const calls=[],layouts=[],scrollListeners=new Set(),inputListeners=new Map();
 function height(){return heightBase+(list[0]?.open?217:0)+(list[1]?.open?200:0);}
 const prototype={scrollTo(...args){
  calls.push({receiver:this,args:[...args],open:list.map(detail=>detail.open),height:height()});
  if(this===wrapper)scrollTop=Math.max(0,Math.min(typeof args[0]==='object'?args[0].top:args[1],height()-200));
  return 'native-result';
 }};
 wrapper=Object.assign(Object.create(prototype),{
  offsetHeight:200,
  addEventListener:(name,fn)=>{if(name==='scroll')scrollListeners.add(fn);else inputListeners.set(name,fn);},
  removeEventListener:(name,fn)=>{if(name==='scroll')scrollListeners.delete(fn);else if(inputListeners.get(name)===fn)inputListeners.delete(name);}
 });
 Object.defineProperties(wrapper,{
  scrollTop:{get:()=>scrollTop,set:value=>{scrollTop=value;}},
  scrollHeight:{get:()=>{scrollTop=Math.min(scrollTop,height()-200);return height();}}
 });
 const test=fixture({details:list,scroller:()=>wrapper});
 test.context.getComputedStyle=()=>{layouts.push(list.map(detail=>detail.open));return {height:'417px'};};
 test.start();
 return {test,list,wrapper,calls,layouts,prototype,scrollListeners,inputListeners,
  input:(type,fields={})=>inputListeners.get(type)?.({type,isTrusted:true,...fields}),
  setTop:value=>{scrollTop=value;scrollListeners.forEach(fn=>fn());},
  grow:()=>heightBase+=27,
  shrink:amount=>heightBase-=amount,
  replace:()=>{list[0]=ownedDetail('scroll-group','group');list[1]=ownedDetail('scroll-child');},
  height};
}
const following=scrollingFixture();
for(let index=0;index<12;index++){
 following.grow();following.replace();
 const collapsed=following.wrapper.scrollHeight;
 assert.equal(following.wrapper.scrollTo(0,collapsed),'native-result');
 assert.equal(following.calls.length,index+1,'one native scroll per streamed replacement');
 const call=following.calls.at(-1);
 assert.deepEqual(call.open,[true,true],'all nested choices restored before native scroll');
 assert.equal(call.args[1],following.height(),'native target is final expanded height');
 assert(call.args[1]>collapsed);
 following.test.notify();assert.equal(following.calls.length,index+1,'observer does not scroll twice');
}
assert(following.layouts.every(open=>open.every(Boolean)),'layout forced only after nested states restored');
const reader=scrollingFixture({reader:true});reader.replace();
const collapsed=reader.wrapper.scrollHeight;assert.equal(reader.wrapper.scrollTop,800,'synthetic collapsed layout clamps');
reader.wrapper.scrollTo(0,collapsed);assert.equal(reader.wrapper.scrollTop,900,'reading position restored after temporary clamp');
assert.equal(reader.calls[0].args[1],900,'reader is not sent to bottom');
const anchored=scrollingFixture({reader:true,top:300});anchored.replace();
anchored.wrapper.scrollTop=280; // ordinary native anchoring below the collapsed max
anchored.wrapper.scrollTo(0,anchored.wrapper.scrollHeight);
assert.equal(anchored.wrapper.scrollTop,280,'legitimate anchoring is not overwritten by an old absolute position');
const passiveReader=scrollingFixture({reader:true});passiveReader.replace();
passiveReader.wrapper.scrollHeight;passiveReader.test.notify();
assert.equal(passiveReader.wrapper.scrollTop,900,'observer-only restoration also repairs a demonstrated clamp');
const unshifted=scrollingFixture({reader:true,top:300});unshifted.replace();unshifted.test.notify();
assert.equal(unshifted.calls.length,0,'reader without clamp gets no compensation scroll');
// Ordinary methods/options and other receivers remain exact pass-through.
const passthrough=scrollingFixture();const options={top:100,behavior:'smooth'};
passthrough.wrapper.scrollTo(options);assert.equal(passthrough.calls.at(-1).args[0],options);
passthrough.wrapper.scrollTo(7,40);assert.deepEqual(passthrough.calls.at(-1).args,[7,40]);
const borrowed={};passthrough.wrapper.scrollTo.call(borrowed,0,12);assert.equal(passthrough.calls.at(-1).receiver,borrowed);
passthrough.test.context.__chuanhuActivityCleanup();
assert.equal(passthrough.wrapper.scrollTo,passthrough.prototype.scrollTo);
assert(!Object.hasOwn(passthrough.wrapper,'scrollTo'));assert.equal(passthrough.scrollListeners.size,0);
// Explicit new-node choice wins; a stale predecessor toggle cannot reopen it.
const intent=scrollingFixture();intent.replace();
intent.test.observers[0].pending=[{type:'attributes',attributeName:'open',target:intent.list[0]}];
intent.wrapper.scrollTo(0,intent.wrapper.scrollHeight);assert(!intent.list[0].open);
assert(intent.list[1].open,'independent child state still restores');
// The detached predecessor's synchronous click is sampled before restoring.
const early=scrollingFixture();early.list[1].open=false;early.replace();
early.wrapper.scrollTo(0,early.wrapper.scrollHeight);assert(!early.list[1].open);
// Normal model / navigation releases only our own instance hook.
const exiting=scrollingFixture();exiting.list.length=0;exiting.test.notify();
assert.equal(exiting.wrapper.scrollTo,exiting.prototype.scrollTo);assert.equal(exiting.scrollListeners.size,0);
const otherHook=scrollingFixture(),newOwner=()=>{};otherHook.wrapper.scrollTo=newOwner;
otherHook.test.context.__chuanhuActivityCleanup();assert.equal(otherHook.wrapper.scrollTo,newOwner);
console.log('Gradio bottom-call integration: 12 replacements, nested restore, reader clamp/anchoring, intent, overloads and cleanup passed');
// Restore exact own descriptors and remove bindings on wrapper replacement.
const ownList=[ownedDetail('own-method')];ownList[0].open=true;
let activeScroller;const ownListeners=new Set(),ownCalls=[];
const ownNative=function(...args){ownCalls.push([this,args]);};
const ownWrapper={scrollTop:600,scrollHeight:800,offsetHeight:200,
 addEventListener:(_,fn)=>ownListeners.add(fn),removeEventListener:(_,fn)=>ownListeners.delete(fn)};
Object.defineProperty(ownWrapper,'scrollTo',{value:ownNative,writable:true,enumerable:true,configurable:true});
const beforeDescriptor=Object.getOwnPropertyDescriptor(ownWrapper,'scrollTo');activeScroller=ownWrapper;
const ownTest=fixture({details:ownList,scroller:()=>activeScroller});ownTest.start();
activeScroller={...ownWrapper,scrollTo:ownNative};ownTest.notify();
assert.deepEqual(Object.getOwnPropertyDescriptor(ownWrapper,'scrollTo'),beforeDescriptor);
ownTest.context.__chuanhuActivityCleanup();assert.equal(activeScroller.scrollTo,ownNative);
const switched=scrollingFixture();switched.test.setConversation('other');switched.test.notify();
assert.equal(switched.wrapper.scrollTo,switched.prototype.scrollTo,'conversation exit releases the hook');
console.log('Scroll wrapper replacement, exact own descriptor restoration and conversation exit passed');

// User scroll changes are synchronous; the scroll event can still be queued.
for(const hook of [false,true]){
 const pending=scrollingFixture();pending.wrapper.scrollTop=300;pending.replace();
 if(hook)pending.wrapper.scrollTo(0,pending.wrapper.scrollHeight);
 else pending.test.notify();
 assert.equal(pending.wrapper.scrollTop,300,'pending user scroll overrides old bottom-follow');
 assert(!pending.calls.some(call=>call.args[1]===pending.height()));
}
const pendingNearClamp=scrollingFixture();pendingNearClamp.wrapper.scrollTop=900;
pendingNearClamp.replace();pendingNearClamp.test.notify();
assert.equal(pendingNearClamp.wrapper.scrollTop,900,'live reader position is sampled before a new collapsed-height measurement');
for(const hook of [false,true]){
 const shrinking=scrollingFixture();shrinking.shrink(150);shrinking.replace();
 shrinking.wrapper.scrollHeight; // actual content shrink, no human scroll
 if(hook)shrinking.wrapper.scrollTo(0,shrinking.wrapper.scrollHeight);
 else shrinking.test.notify();
 assert.equal(shrinking.wrapper.scrollTop,shrinking.height()-200,'real resize clamp retains bottom following');
}
console.log('Queued user scroll wins over cached follow state; genuine content shrink still follows');

// A wheel/key gesture can lose its exact pre-clamp top before scroll delivery.
// Do not mistake that ambiguous frame for permission to restore an old bottom.
for(const type of ['wheel','keydown','touchmove','pointerdown']){
 for(const hook of [false,true]){
  const gesture=scrollingFixture();
  Object.assign(gesture.wrapper,{offsetWidth:400,clientWidth:385});
  gesture.input(type,{deltaY:-317,key:'PageUp',target:gesture.wrapper,button:0,offsetX:390});
  gesture.wrapper.scrollTop=900;gesture.replace();gesture.wrapper.scrollHeight;
  assert.equal(gesture.wrapper.scrollTop,800);
  if(hook)gesture.wrapper.scrollTo(0,gesture.wrapper.scrollHeight);
  else gesture.test.notify();
  assert.equal(gesture.calls.length,0,'trusted pending scroll intent suppresses automatic compensation');
  assert.equal(gesture.wrapper.scrollTop,800,'do not restore the pre-gesture bottom after a clamp');
  gesture.test.context.__chuanhuActivityCleanup();assert.equal(gesture.inputListeners.size,0);
 }
}
const summaryKey=scrollingFixture();
summaryKey.input('keydown',{key:' ',target:{closest:()=>({})}});
summaryKey.replace();summaryKey.wrapper.scrollHeight;summaryKey.test.notify();
assert.equal(summaryKey.wrapper.scrollTop,summaryKey.height()-200,'native summary key is not a scroll gesture');
const bounded=scrollingFixture(),intentFrames=new Map();let intentFrameId=0;
bounded.test.context.requestAnimationFrame=fn=>{intentFrames.set(++intentFrameId,fn);return intentFrameId;};
bounded.test.context.cancelAnimationFrame=id=>intentFrames.delete(id);
bounded.input('wheel',{deltaY:-1});bounded.input('wheel',{deltaY:-1});assert.equal(intentFrames.size,1);
intentFrames.values().next().value();intentFrames.clear();
bounded.replace();bounded.wrapper.scrollHeight;bounded.test.notify();
assert.equal(bounded.wrapper.scrollTop,bounded.height()-200,'no-scroll gesture expires instead of disabling follow permanently');
bounded.input('wheel',{deltaY:-1});bounded.test.context.__chuanhuActivityCleanup();
assert.equal(intentFrames.size,0,'cleanup cancels both intent and restoration frames');
console.log('Bounded trusted wheel/key/touch/scrollbar intent prevents stale-follow compensation through a clamp');

for(const key of ['PageUp','Home','ArrowUp']){
 const focused=scrollingFixture();
 focused.input('keydown',{key,target:{closest:selector=>selector==='summary'?{}:null}});
 focused.wrapper.scrollTop=900;focused.replace();focused.wrapper.scrollHeight;focused.test.notify();
 assert.equal(focused.calls.length,0,'summary navigation keys retain native scrolling intent');
}
for(const [type,fields] of [['wheel',{deltaY:120}],['keydown',{key:'End'}],['keydown',{key:'PageDown'}]]){
 const downward=scrollingFixture();downward.input(type,fields);downward.replace();
 downward.wrapper.scrollHeight;downward.test.notify();
 assert.equal(downward.wrapper.scrollTop,downward.height()-200,'downward input at bottom does not abandon following');
}
console.log('Summary scroll keys are respected; ineffective downward input keeps bottom following');
