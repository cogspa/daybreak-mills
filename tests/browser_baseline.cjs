// Run with Playwright available through NODE_PATH; no runtime app dependency.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const os = require('node:os');
const { pathToFileURL } = require('node:url');
(async () => {
  const root = path.resolve(__dirname, '..');
  const browser = await chromium.launch({headless:true, ...(process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {})});
  let pairingServer, pairingFolder;
  try {
    const page = await browser.newPage();
    const errors = [], logs = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', e => { if(e.type()==='log') logs.push(e.text()); });
    await page.goto(pathToFileURL(path.join(root,'app/daybreak-studio.html')).href);
    await page.waitForFunction(() => typeof SESSION !== 'undefined' && SESSION.ready && state.g && !SESSION.restoring);
    await page.waitForTimeout(1000);
    const results = await page.evaluate(async () => {
      clearTimeout(SESSION.t);
      const initial = sessionSnapshot();
      initial.copy.claim = 'BASELINE CHECK';
      initial.zones.logo = {x:0.1,y:0.05,w:0.7,h:0.12};
      const asset = document.createElement('canvas');asset.width=16;asset.height=16;
      asset.getContext('2d').fillRect(0,0,16,16);initial.assets.logo=asset.toDataURL();
      if(!await sessionApply(initial)) throw new Error('Session import failed');
      const restored = sessionSnapshot();
      sessionTouch();await sessionAutosave();
      const stored = await sessionLoadStored();
      const jobs=[];
      for(const size of ['Mini','Regular','Family','Mega']){
        jobs.push(await withFlavour('cocoa',size,async()=>jobJSON(2048)));
      }
      const savedDownload=download, outputs=[];
      download=(blob,name)=>outputs.push({blob,name});
      $('e-res').value='2048';exportSVG();exportPDF();
      download=savedDownload;
      const expectedMM = [state.g.totalW*1000,state.g.totalH*1000];
      const exports=[];
      for(const output of outputs) exports.push({name:output.name,text:await output.blob.text()});
      const single=await buildSingle();
      return {expectedMM,restored,stored,jobs,exports,zip:Array.from(new Uint8Array(await single.blob.arrayBuffer()))};
    });
    assert.equal(results.restored.copy.claim,'BASELINE CHECK');
    assert.deepEqual(results.stored.zones.logo,results.restored.zones.logo);
    assert.equal(results.stored.assets.logo,results.restored.assets.logo);
    assert.equal(results.jobs.length,4);
    const spec=JSON.parse(fs.readFileSync(path.join(root,'spec/boxes.json')));
    for(const job of results.jobs){const size=spec.sizes[job.box.size];assert.equal(job.box.inches.W,size.w);assert.equal(job.box.inches.H,size.h);assert.equal(job.box.inches.D,size.d);}
    const svg=results.exports.find(x=>x.name.endsWith('.svg')).text;
    const dimensions=await page.evaluate(text=>{const doc=new DOMParser().parseFromString(text,'image/svg+xml'); if(doc.querySelector('parsererror')) throw new Error('Malformed SVG');return ['width','height'].map(k=>parseFloat(doc.documentElement.getAttribute(k)));},svg);
    dimensions.forEach((n,i)=>assert.ok(Math.abs(n-results.expectedMM[i])<0.1));
    const pdf=results.exports.find(x=>x.name.endsWith('.pdf')).text;
    assert.ok(pdf.startsWith('%PDF-1.4'));
    const media=pdf.match(/\/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]/);
    assert.ok(media);[+media[1],+media[2]].forEach((n,i)=>assert.ok(Math.abs(n-results.expectedMM[i]*72/25.4)<0.01));
    assert.ok(logs.some(x=>/UV.*pass|pass.*UV/i.test(x)),JSON.stringify(logs));
    pairingFolder=fs.mkdtempSync(path.join(os.tmpdir(),'daybreak-pairing-test-'));
    pairingServer=spawn(process.env.PYTHON || 'python3',[path.join(__dirname,'pairing_server.py'),pairingFolder]);
    const port=await new Promise((resolve,reject)=>{pairingServer.stdout.once('data',d=>resolve(Number(d.toString().trim())));pairingServer.once('error',reject);pairingServer.once('exit',code=>reject(new Error(`Pairing server exited ${code}`)));});
    // Use an ephemeral test port, leaving any running user bridge untouched.
    await page.evaluate(async port=>{
      pingBridge=async()=>{const hit=await probe(port);bridge=hit ? hit.j : null;BRIDGE=`http://127.0.0.1:${port}`;renderBridge();return bridge;};
      bridgeToken='';await pingBridge();setTab('out');
    },port);
    assert.ok(await page.evaluate(()=>bridge), await page.evaluate(async()=>{try{const r=await fetch(BRIDGE+'/status',{headers:bridgeHeaders()});return `${r.status} ${await r.text()}`;}catch(e){return String(e);}}));
    assert.equal(await page.evaluate(()=>bridge.pairing_required),true);
    await page.locator('#bridge-pair-file').setInputFiles(path.join(pairingFolder,'bridge-pairing.json'));
    await page.waitForFunction(()=>bridge && bridge.authenticated === true);
    assert.equal(await page.locator('#bridge-blender').isEnabled(),true);
    assert.deepEqual(errors,[]);
    const out=process.env.BASELINE_OUTPUT;
    if(out){fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'browser-single.zip'),Buffer.from(results.zip));for(const job of results.jobs)fs.writeFileSync(path.join(out,job.box.size+'_job.json'),JSON.stringify(job,null,2));}
    console.log('PASS: offline boot, UV self-test, session/assets round trip, autosave, four sizes, SVG/PDF, single package export and authenticated pairing');
  } finally {if(pairingServer) pairingServer.kill();await browser.close();if(pairingFolder) fs.rmSync(pairingFolder,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
