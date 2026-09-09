const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
 try{
  const context=await browser.newContext({viewport:{width:1500,height:960}}),p=await context.newPage(),errors=[];
  p.on('pageerror',e=>errors.push(e.message));
  await p.goto(pathToFileURL(path.resolve(__dirname,'../app/daybreak-studio.html')).href);
  await p.waitForFunction(()=>typeof SESSION!=='undefined' && SESSION.ready);
  assert.equal(await p.evaluate(()=>SESSION.error),'');
  assert.equal(await p.locator('#v-workspace').isVisible(),true);
  assert.equal(await p.locator('#glCv').isVisible(),true);
  assert.equal(await p.locator('#ws-canvas').isVisible(),true);
  await p.waitForFunction(()=>cam && proofBoxes.length===1);
  if(await p.locator('#ws-back').isVisible())await p.locator('#ws-back').click();
  await p.locator('#c-claim').fill('FIRST CLAIM');
  await p.keyboard.press('Control+z');
  await p.waitForFunction(()=>!HISTORY.busy && state.copy.claim==='');
  assert.equal(await p.evaluate(()=>state.copy.claim),'');
  await p.locator('#ws-redo').click();await p.waitForFunction(()=>!HISTORY.busy && state.copy.claim==='FIRST CLAIM');
  assert.equal(await p.evaluate(()=>state.copy.claim),'FIRST CLAIM');
  // Add two distinct image layers to the selected panel.
  const ids=await p.evaluate(async()=>{
    const cv=document.createElement('canvas');cv.width=64;cv.height=32;cv.getContext('2d').fillRect(0,0,64,32);
    const img=await loadImg(cv.toDataURL());
    state.images.push({id:state.nextId++,img,name:'First image',panel:'FRONT',x:.5,y:.5,scale:40,rot:0,thumb:img.src});
    redraw();historyRecord();
    state.images.push({id:state.nextId++,img,name:'Second image',panel:'FRONT',x:.6,y:.6,scale:40,rot:0,thumb:img.src});
    redraw();historyRecord();return state.images.map(i=>i.id);
  });
  await p.locator(`[data-layer="${ids[0]}"]`).click();
  await p.locator('#ws-x').fill('12.5');await p.locator('#ws-y').fill('18');await p.locator('#ws-w').fill('50');
  assert.ok(Math.abs(await p.evaluate(()=>wsRect(wsSelected()).w)-50)<1e-7);
  assert.ok(Math.abs(await p.evaluate(()=>wsRect(wsSelected()).h)-25)<1e-7);
  await p.locator('#ws-locked').check();
  assert.equal(await p.locator('#ws-x').isDisabled(),true);
  const locked=await p.evaluate(()=>wsRect(wsSelected()));await p.evaluate(()=>wsNumeric('x',100));
  assert.deepEqual(await p.evaluate(()=>wsRect(wsSelected())),locked);
  await p.locator('#ws-locked').uncheck();
  await p.locator('#ws-up').click();
  assert.equal(await p.evaluate(()=>state.images.at(-1).id),ids[0]);
  await p.evaluate(()=>historyStep());assert.equal(await p.evaluate(()=>state.images.at(-1).id),ids[1]);
  await p.evaluate(()=>historyStep(true));assert.equal(await p.evaluate(()=>state.images.at(-1).id),ids[0]);
  await p.locator('#ws-visible').uncheck();assert.equal(await p.evaluate(()=>wsSelected().hidden),true);
  await p.evaluate(()=>historyStep());assert.equal(await p.evaluate(()=>!!wsSelected().hidden),false);
  await p.evaluate(()=>historyStep(true));assert.equal(await p.evaluate(()=>wsSelected().hidden),true);
  await p.locator('#ws-visible').check();
  // Image dragging snaps top-left coordinates to the chosen grid.
  const snap=await p.evaluate(()=>{state.workspace.grid=5;WS.guides=[];return wsSnap(12.1,20,200,'x');});assert.equal(snap,10);
  await p.locator(`[data-layer="${ids[1]}"]`).click();
  const beforeDrag=await p.evaluate(()=>wsRect(wsSelected())),box=await p.locator('#ws-canvas').boundingBox();
  const panelMM=await p.evaluate(()=>state.g.panelMM.FRONT);
  const cx=box.x+(beforeDrag.x+beforeDrag.w/2)/panelMM[0]*box.width,cy=box.y+(beforeDrag.y+beforeDrag.h/2)/panelMM[1]*box.height;
  await p.mouse.move(cx,cy);await p.mouse.down();await p.mouse.move(cx+27,cy+16,{steps:4});await p.mouse.up();
  const moved=await p.evaluate(()=>wsRect(wsSelected()));assert.notEqual(moved.x,beforeDrag.x);assert.ok(Math.abs(moved.x/5-Math.round(moved.x/5))<1e-6);
  await p.evaluate(()=>historyStep());assert.ok(Math.abs((await p.evaluate(()=>wsRect(wsSelected()))).x-beforeDrag.x)<1e-6);
  // Six panel controls update the canvas and exact physical dimensions.
  for(const panel of ['BACK','LEFT','RIGHT','TOP','BOTTOM','FRONT']){
    await p.locator(`[data-ws-panel="${panel}"]`).click();assert.equal(await p.evaluate(()=>wsPanel()),panel);
    assert.equal(await p.locator('#glCv').isVisible(),true);
  }
  await p.waitForTimeout(150);
  const picked=await p.evaluate(()=>wsPickFace(cam.w/2,cam.h/2));assert.equal(picked,'FRONT');
  const bounds=await p.locator('#glCv').boundingBox();await p.mouse.click(bounds.x+bounds.width/2,bounds.y+bounds.height/2);
  assert.equal(await p.evaluate(()=>wsPanel()),'FRONT');
  // Managed artwork uses the same numeric zone rectangles as the exports.
  await p.locator('[data-layer="logo"]').click();await p.locator('#ws-x').fill('9');
  assert.ok(Math.abs(await p.evaluate(()=>state.zones.logo.x*state.g.panelMM.FRONT[0])-9)<1e-7);
  await p.locator('#ws-edit-asset').click();assert.equal(await p.locator('#glCv').isVisible(),true);assert.equal(await p.locator('#adCv').isVisible(),true);
  await p.evaluate(async()=>{const cv=adCanvas('logo');cv.getContext('2d').fillRect(0,0,cv.width,cv.height);adCommit();await projectSettle();historyRecord();});
  assert.ok(await p.evaluate(()=>!!state.assets.logo));
  await p.evaluate(()=>historyStep());assert.equal(await p.evaluate(()=>state.assets.logo),null);
  await p.evaluate(()=>historyStep(true));assert.ok(await p.evaluate(()=>!!state.assets.logo));
  await p.locator('#ws-back').click();
  const oldBrand=await p.evaluate(()=>BRAND.name);
  await p.locator('#ws-brand').click();await p.evaluate(()=>{BR.applying=true;});await p.locator('#br-name').fill('WORKSPACE BRAND');await p.evaluate(()=>{BR.applying=false;});
  await p.evaluate(()=>historyStep());assert.equal(await p.evaluate(()=>BRAND.name),oldBrand);
  await p.evaluate(()=>historyStep(true));assert.equal(await p.evaluate(()=>BRAND.name),'WORKSPACE BRAND');
  await p.locator('#ws-back').click();
  // Applying a brief (including an explicit pack-size override) is reversible.
  const oldSize=await p.evaluate(()=>state.g.name);
  await p.locator('#ws-brief').click();await p.locator('#b-size-override').selectOption('Mini');await p.locator('#b-apply').click();
  assert.equal(await p.evaluate(()=>state.g.name),'Mini');await p.evaluate(()=>historyStep());assert.equal(await p.evaluate(()=>state.g.name),'Mini');await p.evaluate(()=>historyStep());assert.equal(await p.evaluate(()=>state.g.name),oldSize);assert.equal(await p.evaluate(()=>BRAND.name),'WORKSPACE BRAND');
  // A new edit after undo invalidates redo, and project switches reset history.
  await p.locator('#c-weight').fill('A');await p.evaluate(()=>historyStep());await p.locator('#c-weight').fill('B');
  await p.evaluate(()=>historyRecord());assert.equal(await p.evaluate(()=>HISTORY.future.length),0);
  const current=await p.evaluate(()=>SESSION.id);await p.evaluate(()=>sessionAutosave());
  await p.evaluate(()=>projectCreate('Other workspace'));assert.equal(await p.evaluate(()=>HISTORY.past.length),1);
  await p.evaluate(id=>projectOpen(id),current);assert.equal(await p.evaluate(()=>HISTORY.past.length),1);
  assert.equal(await p.evaluate(()=>state.images.at(-1).id),ids[0]);
  await p.screenshot({path:'/private/tmp/daybreak-stage3-workspace.png'});
  await p.reload();await p.waitForFunction(()=>SESSION.ready);
  assert.equal(await p.evaluate(()=>state.copy.weight),'B');assert.equal(await p.evaluate(()=>state.images.at(-1).id),ids[0]);
  assert.deepEqual(errors,[]);
  console.log('PASS: persistent preview, contextual panels, face picking, copy undo/redo, numeric geometry, image order/visibility/lock, snapping, asset undo/redo, redo invalidation, project isolation and reopen');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
