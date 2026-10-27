const assert=require('assert/strict'),fs=require('fs'),vm=require('vm');
const requests=[];let conversation='one',fallback=0;
class FormData {constructor(){this.files=[];}append(key,file){this.files.push(file);}getAll(){return this.files;}}
class Response {constructor(body,options){this.body=body;this.status=options.status;}}
class XHR {
 constructor(){this.upload={};}
 open(method,url){this.url=url;}
 send(data){this.file=data.files[0];requests.push(this);}
 abort(){this.onabort();}
 succeed(){this.status=200;this.responseText=JSON.stringify(['/tmp/gradio/hash/'+this.file.name]);this.onload();}
 fail(){this.onerror();}
}
const window={fetch:async()=>{fallback++;return 'ordinary';},gradio_config:{root:'http://localhost'},chuanhuInputConversation:()=>conversation};
vm.runInNewContext(fs.readFileSync('web_assets/javascript/agent-upload.js','utf8'),{window,document:{},XMLHttpRequest:XHR,FormData,Response,location:{origin:'http://localhost',href:'http://localhost/'},URL});
const file=(name,size=10)=>({name,size});
const submit=files=>{const data=new FormData();files.forEach(f=>data.append('files',f));return window.fetch('http://localhost/upload?upload_id=native',{method:'POST',body:data});};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 assert.equal(await window.fetch('http://localhost/ordinary'), 'ordinary');assert.equal(fallback,1);
 const files=[file('cancel-first'),file('keep-second')];assert(window.chuanhuBeginUpload(files));
 assert.equal(window.chuanhuUploadCards().length,2);assert.equal(window.chuanhuUploadCards()[0].progress,null);
 const unrelated=new FormData();files.forEach(f=>unrelated.append('files',f));
 assert.equal(await window.fetch('http://other-host/upload?upload_id=other',{method:'POST',body:unrelated}),'ordinary');
 assert.equal(await window.fetch('http://localhost/other/upload?upload_id=other',{method:'POST',body:unrelated}),'ordinary');
 assert.equal(requests.length,0);
 const pending=submit(files);assert.equal(requests.length,1);
 requests[0].upload.onprogress({lengthComputable:true,loaded:4,total:10});assert.equal(window.chuanhuUploadCards()[0].progress,.4);
 window.chuanhuUploadRemove(window.chuanhuUploadCards()[0].id);await tick();assert.equal(requests.length,2);
 requests[1].succeed();const response=await pending;assert.deepEqual(JSON.parse(response.body),['/tmp/gradio/hash/keep-second','/tmp/gradio/hash/keep-second']);
 const native=JSON.parse(response.body).map((path,index)=>({path,orig_name:files[index].name,size:files[index].size}));
 const staged=window.chuanhuUploadStaging(native);assert.equal(staged.length,1);assert.equal(staged[0].orig_name,'keep-second');
 window.chuanhuUploadCommitted(staged);assert.equal(window.chuanhuUploadHasPending(),false);
 const failed=[file('retry')];window.chuanhuBeginUpload(failed);const failure=submit(failed);requests.at(-1).fail();assert.equal((await failure).status,503);
 assert.equal(window.chuanhuUploadCards()[0].status,'failed');assert(window.chuanhuUploadHasPending());
 window.chuanhuUploadRemove(window.chuanhuUploadCards()[0].id);assert.equal(window.chuanhuUploadHasPending(),false);
 window.chuanhuBeginUpload([file('late')]);const late=submit([file('late')]);conversation='two';assert.equal(window.chuanhuUploadCards().length,0);
 assert.equal(window.chuanhuUploadHasPending(),false);
 assert(window.chuanhuBeginUpload([file('new')]));const fresh=submit([file('new')]);
 assert.equal((await late).status,409);assert.equal(window.chuanhuAgentUploadTarget,'two');
 requests.at(-1).succeed();await fresh;const freshFiles=window.chuanhuUploadStaging([{path:'/tmp/gradio/hash/new'}]);window.chuanhuUploadCommitted(freshFiles);
 const mixed=[file('good'),file('bad')];window.chuanhuBeginUpload(mixed);const mixedResult=submit(mixed);requests.at(-1).succeed();await tick();requests.at(-1).fail();await mixedResult;
 window.chuanhuUploadRemove(window.chuanhuUploadCards()[1].id);assert.equal(window.chuanhuUploadCards()[0].status,'failed');assert(window.chuanhuUploadHasPending());
 conversation='three';assert.equal(window.chuanhuUploadHasPending(),false);assert(window.chuanhuBeginUpload([file('next')]));
 const fast=[file('instant-remove')];conversation='four';window.chuanhuBeginUpload(fast);window.chuanhuUploadRemove(window.chuanhuUploadCards()[0].id);const requestCount=requests.length;assert.equal((await submit(fast)).status,409);assert.equal(requests.length,requestCount);assert.equal(window.chuanhuUploadHasPending(),false);
 conversation='';assert.equal(window.chuanhuUploadHasPending(),false);assert.equal(window.chuanhuBeginUpload([file('ordinary')]),false);
 console.log('XHR byte progress, sequential abort, failure send lock and captured conversation passed');
})().catch(error=>{console.error(error);process.exit(1);});
