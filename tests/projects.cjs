const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
 try{
  const context=await browser.newContext(), page=await context.newPage(),errors=[];
  const url=pathToFileURL(path.resolve(__dirname,'../app/daybreak-studio.html')).href;
  const track=p=>p.on('pageerror',e=>errors.push(e.message));track(page);
  const ready=async p=>{await p.goto(url);await p.waitForFunction(()=>typeof SESSION!=='undefined' && SESSION.ready);assert.equal(await p.evaluate(()=>SESSION.error),'');};
  await ready(page);
  // Recreate the previous release's single-session database, then migrate it.
  await page.evaluate(async()=>{
   const snap=sessionSnapshot();snap.copy.claim='LEGACY COPY';snap.view={az:27,el:18,dist:3,spin:false};
   const cv=document.createElement('canvas');cv.width=16;cv.height=16;cv.getContext('2d').fillRect(0,0,16,16);snap.assets.logo=cv.toDataURL();
   clearTimeout(SESSION.t);SESSION.db.close();SESSION.db=null;
   await new Promise((res,rej)=>{const r=indexedDB.deleteDatabase('daybreak-mills');r.onsuccess=res;r.onerror=rej;});
   await new Promise((res,rej)=>{const r=indexedDB.open('daybreak-mills',1);r.onupgradeneeded=()=>r.result.createObjectStore('session');r.onsuccess=()=>{const db=r.result,tx=db.transaction('session','readwrite');tx.objectStore('session').put(snap,'current');tx.oncomplete=()=>{db.close();res();};tx.onerror=rej;};});
  });
  await ready(page);
  assert.equal(await page.evaluate(()=>SESSION.name),'Recovered session');
  assert.equal(await page.evaluate(()=>state.copy.claim),'LEGACY COPY');
  assert.equal(await page.evaluate(()=>state.view.az),27);
  const legacyID=await page.evaluate(()=>SESSION.id);
  await page.locator('#projects-open').click();
  await page.locator('#project-name').fill('Family launch');await page.locator('#project-rename').click();
  await page.waitForFunction(()=>!SESSION.busy && SESSION.name==='Family launch').catch(async e=>{console.log(await page.evaluate(()=>({name:SESSION.name,busy:SESSION.busy,error:SESSION.error,notice:SESSION.notice,input:$('project-name').value})),errors);throw e;});
  const checkpoint=await page.evaluate(()=>projectCheckpoint('Approved direction'));
  await page.evaluate(()=>{state.copy.claim='EXPERIMENT';$('c-claim').value='EXPERIMENT';sessionTouch();});
  await page.evaluate(()=>projectCreate('Second project'));
  assert.equal(await page.evaluate(()=>state.copy.claim),'');
  assert.equal(await page.evaluate(()=>state.assets.logo),null);
  const second=await page.evaluate(()=>SESSION.id);
  await page.evaluate(id=>projectOpen(id),legacyID);
  assert.equal(await page.evaluate(()=>state.copy.claim),'EXPERIMENT');
  await page.evaluate(id=>projectRestore(id),checkpoint);
  assert.equal(await page.evaluate(()=>state.copy.claim),'LEGACY COPY');
  assert.ok(await page.evaluate(()=>state.assets.logo.src.startsWith('data:image/')));
  const duplicate=await page.evaluate(()=>projectDuplicate('Alternative'));
  assert.notEqual(duplicate,legacyID);
  await page.evaluate(()=>{state.copy.claim='DUPLICATE ONLY';sessionTouch();});
  await page.evaluate(id=>projectOpen(id),legacyID);
  assert.equal(await page.evaluate(()=>state.copy.claim),'LEGACY COPY');
  assert.ok(await page.evaluate(async()=>{const c=await projectDB(['checkpoints'],'readonly',(tx,done)=>{const r=tx.objectStore('checkpoints').getAll();r.onsuccess=()=>done(r.result);});return c.some(x=>x.name.startsWith('Before restoring'));}));
  // Recovery restores the previous committed autosave, preserving the current one.
  await page.evaluate(()=>{state.copy.claim='RECOVERY TEST';sessionTouch();});await page.evaluate(()=>sessionAutosave());
  await page.evaluate(()=>projectRecover());assert.equal(await page.evaluate(()=>state.copy.claim),'LEGACY COPY');
  // A sketch still inside its debounce window must stay with its source project.
  await page.evaluate(async id=>{
    const cv=adCanvas('logo');cv.getContext('2d').fillRect(0,0,cv.width,cv.height);adCommit();await projectOpen(id);
  },second);
  assert.equal(await page.evaluate(()=>state.assets.logo),null);
  await page.evaluate(id=>projectOpen(id),legacyID);
  assert.ok(await page.evaluate(()=>state.assets.logo && state.assets.logo.naturalWidth>16));
  // Invalid imports leave the active project and persisted work intact.
  await assert.rejects(page.evaluate(()=>projectCreate('Broken',{format:'daybreak-session/1',brand:{name:'Oops',flavours:null}})));
  assert.equal(await page.evaluate(()=>SESSION.id),legacyID);
  assert.equal(await page.evaluate(()=>state.copy.claim),'LEGACY COPY');
  // Simulate quota failure, then retry without dropping edits.
  const failure=await page.evaluate(async()=>{
   const original=projectDB;state.copy.claim='UNSAVED';sessionTouch();clearTimeout(SESSION.t);
   projectDB=async()=>{throw new Error('Quota exceeded');};await sessionAutosave();
   const result={dirty:SESSION.dirty,error:SESSION.error};projectDB=original;await sessionAutosave();return result;
  });
  assert.equal(failure.dirty,true);assert.match(failure.error,/Not saved/);
  assert.equal(await page.evaluate(async()=>(await sessionLoadStored()).copy.claim),'UNSAVED');
  // A second tab saves from a stale revision; it must produce a recovery copy.
  const other=await context.newPage();track(other);await ready(other);
  await page.evaluate(()=>{state.copy.claim='FIRST TAB';sessionTouch();});await page.evaluate(()=>sessionAutosave());
  await other.evaluate(()=>{state.copy.claim='SECOND TAB';sessionTouch();});await other.evaluate(()=>sessionAutosave());
  assert.notEqual(await other.evaluate(()=>SESSION.id),legacyID);
  assert.match(await other.evaluate(()=>SESSION.name),/recovered copy/);
  assert.equal(await page.evaluate(async()=>(await projectRead('projects',SESSION.id)).snapshot.copy.claim),'FIRST TAB');
  // Save completion may not mark a newer edit as saved.
  const concurrent=await page.evaluate(async()=>{
    const original=projectDB;let release,started;const gate=new Promise(r=>release=r),entered=new Promise(r=>started=r);
    projectDB=async(...args)=>{const result=await original(...args);if(args[1]==='readwrite' && args[0].includes('projects')){started();await gate;}return result;};
    state.copy.claim='OLDER SAVE';sessionTouch();clearTimeout(SESSION.t);const save=sessionAutosave();await entered;
    state.copy.claim='NEWER EDIT';sessionTouch();clearTimeout(SESSION.t);release();await save;const dirty=SESSION.dirty;projectDB=original;await sessionAutosave();return dirty;
  });
  assert.equal(concurrent,true);
  await page.evaluate(id=>projectOpen(id),legacyID);
  await page.evaluate(()=>projectShow());
  await page.screenshot({path:process.env.PROJECT_SCREENSHOT || '/private/tmp/daybreak-stage2-projects.png'});
  await other.close();
  await page.reload();await page.waitForFunction(()=>SESSION.ready);
  assert.equal(await page.evaluate(()=>state.copy.claim),'NEWER EDIT');
  assert.equal(await page.evaluate(()=>SESSION.id),legacyID);
  assert.deepEqual(errors,[]);
  console.log('PASS: legacy migration, gallery/rename, project isolation, duplication, checkpoints, restore recovery, images/view restoration, invalid import, quota failure/retry, stale-tab recovery, save races and reopen');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
