const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),{spawn}=require('node:child_process'),{pathToFileURL}=require('node:url');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});let server,folder;
 try{
  folder=fs.mkdtempSync(path.join(os.tmpdir(),'daybreak-connect-'));
  server=spawn('python3',[path.join(__dirname,'pairing_server.py'),folder,'--approve-pairing']);
  const port=await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(+d.toString().trim()));server.once('error',reject);});
  const p=await browser.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.goto(pathToFileURL(path.resolve(__dirname,'../app/daybreak-studio.html')).href);await p.waitForFunction(()=>typeof SESSION!=='undefined'&&SESSION.ready);
  await p.evaluate(async port=>{pingBridge=async()=>{const hit=await probe(port);bridge=hit?.j||null;BRIDGE='http://127.0.0.1:'+port;renderBridge();return bridge;};setTab('out');await pingBridge();},port);
  await p.getByRole('button',{name:'Connect to Blender',exact:true}).click();
  await p.waitForFunction(()=>bridge?.authenticated===true);
  assert.match(await p.locator('#bridge-connect-status').textContent(),/remember/);
  assert.equal(await p.evaluate(()=>localStorage.getItem(bridgeStorageKey)),JSON.parse(fs.readFileSync(path.join(folder,'bridge-pairing.json'))).token);
  await p.evaluate(()=>sessionStorage.clear());await p.reload();await p.waitForFunction(()=>SESSION.ready);
  assert.ok(await p.evaluate(()=>bridgeToken.length===64));
  assert.equal(await p.evaluate(async port=>(await probe(port)).j.authenticated,port),true);
  assert.deepEqual(errors,[]);console.log('PASS: Connect button, approval exchange, remembered connection after reload without a session token');
 }finally{server?.kill();await browser.close();if(folder)fs.rmSync(folder,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
