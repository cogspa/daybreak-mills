const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),{spawn}=require('node:child_process'),{pathToFileURL}=require('node:url');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});let server,folder;
 try{
  const p=await browser.newPage({viewport:{width:1500,height:960}}),errors=[];p.on('pageerror',e=>{errors.push(e.message);console.error(e.message);});
  await p.goto(pathToFileURL(path.resolve(__dirname,'../app/daybreak-studio.html')).href);await p.waitForFunction(()=>typeof SESSION!=='undefined'&&SESSION.ready);
  await p.evaluate(()=>{setTab('out');window.testFiles=[];download=(blob,name)=>testFiles.push({blob,name});$('e-res').value='2048';});
  await p.locator('#e-job').click();await p.waitForFunction(()=>!OUTPUT.busy);
  assert.equal(await p.evaluate(()=>testFiles.length),0);assert.match(await p.locator('#export-message').textContent(),/Review the checks/);
  await p.locator('#export-draft').check();await p.locator('#e-job').click();await p.waitForFunction(()=>!OUTPUT.busy);
  const job=await p.evaluate(async()=>JSON.parse(await testFiles.find(f=>f.name.endsWith('_job.json')).blob.text()));
  assert.ok(job.design_export.checkpoint_id);assert.match(job.design_export.sha256,/^[a-f0-9]{64}$/);assert.ok(job.texture.includes(job.design_export.id.slice(0,8)));
  const saved=await p.evaluate(id=>projectRead('checkpoints',id),job.design_export.checkpoint_id);assert.ok(saved.snapshot);
  // Same design generates the same pixels; old decorative randomness is gone.
  assert.ok(await p.evaluate(()=>{const a=document.createElement('canvas'),b=document.createElement('canvas');drawNet(a,512,{guides:false});drawNet(b,512,{guides:false});return a.toDataURL()===b.toDataURL();}));
  const beforeCancel=await p.evaluate(()=>testFiles.length);
  await p.evaluate(()=>{window.cancelRun=outputRun('range','matrix');});await p.getByRole('button',{name:'Cancel export',exact:true}).click();await p.evaluate(()=>window.cancelRun);
  assert.equal(await p.evaluate(()=>testFiles.length),beforeCancel);assert.match(await p.locator('#export-message').textContent(),/cancelled/);
  await p.locator('#e-svg').click();await p.waitForFunction(()=>!OUTPUT.busy);await p.locator('#e-pdf').click();await p.waitForFunction(()=>!OUTPUT.busy);
  const files=await p.evaluate(async()=>Promise.all(testFiles.filter(f=>/svg|pdf/.test(f.name)).map(async f=>({name:f.name,text:await f.blob.text()}))));
  assert.ok(files.some(f=>f.name.endsWith('.svg')&&f.text.includes('DESIGN PROOF')&&f.text.includes('checkpoint_id')));assert.ok(files.some(f=>f.name.endsWith('.pdf')&&f.text.includes('/Info 7 0 R')));
  folder=fs.mkdtempSync(path.join(os.tmpdir(),'daybreak-queue-browser-'));server=spawn('python3',[path.join(__dirname,'queue_server.py'),folder]);
  const port=await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(+d.toString().trim()));server.once('error',reject);});
  const token=JSON.parse(fs.readFileSync(path.join(folder,'bridge-pairing.json'))).token;
  await p.evaluate(async({port,token})=>{BRIDGE='http://127.0.0.1:'+port;bridgeToken=token;pingBridge=async()=>{const r=await fetch(BRIDGE+'/status',{headers:bridgeHeaders()});bridge=await r.json();renderBridge();return bridge;};await pingBridge();$('deploy-open').checked=false;$('deploy-what').value='one';},{port,token});
  await p.locator('#deploy-go').click();await p.waitForFunction(()=>!OUTPUT.busy);await p.evaluate(()=>queueRefresh());
  const entry=await p.evaluate(async()=>{const r=await fetch(BRIDGE+'/queue',{headers:bridgeHeaders()});return (await r.json()).queue[0];});assert.ok(entry.design.id);fs.copyFileSync(path.join(folder,'.render-queue',entry.id,'source.zip'),'/private/tmp/daybreak-stage5-proof.zip');
  await p.getByRole('button',{name:'Cancel',exact:true}).click();
  await p.waitForFunction(async()=>{await queueRefresh();return $('render-queue').textContent.includes('cancelled');});
  fs.writeFileSync(path.join(folder,'fake.mode'),'ok');await p.getByRole('button',{name:'Retry saved package'}).click();
  await p.waitForFunction(async()=>{await queueRefresh();return $('render-queue').textContent.includes('complete');});
  await p.getByRole('button',{name:'Download render',exact:true}).click();assert.ok(await p.evaluate(()=>testFiles.some(f=>f.name.endsWith('.png'))));
  await p.evaluate(()=>{state.copy.claim='AFTER EXPORT';redraw();});await p.getByRole('button',{name:'Restore design version'}).click();await p.waitForFunction(()=>!SESSION.busy&&state.copy.claim!=='AFTER EXPORT');
  await p.screenshot({path:'/private/tmp/daybreak-stage5-output.png'});assert.deepEqual(errors,[]);
  console.log('PASS: export checks, proof labeling, saved snapshot trace, stable textures, paired queue submission, cancellation, retry, results and design restoration');
 }finally{server?.kill();await browser.close();if(folder)fs.rmSync(folder,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
