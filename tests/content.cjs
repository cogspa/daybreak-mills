const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
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
  const spec=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../spec/boxes.json')));
  assert.deepEqual(await p.evaluate(()=>CONTENT_SPEC),{...spec.packaging_content,safe_mm:spec.safe_area_mm,nutrition_minimums:spec.nutrition_panel_minimums_pt});
  assert.equal(await p.evaluate(()=>contentEffective().calories),'');
  assert.ok(await p.evaluate(()=>contentReport().missing.includes('calories')));
  await p.locator('[data-ws-panel="BACK"]').click();
  await p.locator('#content-backBody').fill('A morning story.\nMade for a leisurely breakfast.');
  await p.evaluate(()=>historyStep());assert.equal(await p.evaluate(()=>contentEffective().backBody),'');assert.equal(await p.locator('#content-backBody').inputValue(),'');
  await p.evaluate(()=>historyStep(true));assert.equal(await p.evaluate(()=>contentEffective().backBody),'A morning story.\nMade for a leisurely breakfast.');
  assert.ok(await p.locator('#glCv').isVisible());
  const keys=await p.evaluate(()=>Object.keys(FLAVOURS).slice(0,2));
  await p.evaluate(()=>{state.spec.masthead=23;redraw();});
  await p.locator('#content-flavour').selectOption(keys[0]);await p.waitForFunction(k=>!SESSION.busy && state.rec.flavKey===k,keys[0]);
  assert.equal(await p.evaluate(()=>state.spec.masthead),23);
  await p.locator('#content-scope').selectOption('flavour');
  assert.ok(await p.locator('#content-backBody').isDisabled());
  await p.locator('#override-backBody').check();await p.locator('#content-backBody').fill('Only the first flavour.');
  await p.locator('#content-flavour').selectOption(keys[1]);await p.waitForFunction(k=>!SESSION.busy && state.rec.flavKey===k,keys[1]);
  assert.equal(await p.evaluate(()=>state.spec.masthead),23);
  assert.equal(await p.locator('#content-backBody').inputValue(),'A morning story.\nMade for a leisurely breakfast.');
  await p.locator('#override-backBody').check();await p.locator('#content-backBody').fill('');
  assert.equal(await p.evaluate(()=>contentEffective().backBody),'');
  await p.locator('#override-backBody').uncheck();assert.equal(await p.evaluate(()=>contentEffective().backBody),'A morning story.\nMade for a leisurely breakfast.');
  await p.locator('#content-scope').selectOption('shared');
  await p.locator('[data-ws-panel="RIGHT"]').click();
  for(const [key,value] of Object.entries({servings:'10',servingSize:'40 g',calories:'150',fat:'2',fatDV:'3',ingredients:'Whole grain oats, corn, salt.',allergens:'Contains oats.',nutritionNote:'Example test data only.'}))await p.locator('#content-'+key).fill(value);
  await p.locator('#content-calories').fill('-1');assert.equal(await p.evaluate(()=>contentEffective().calories),'150');
  await p.locator('#content-calories').fill('150');
  await p.locator('#content-scope').selectOption('flavour');await p.locator('#override-calories').check();await p.locator('#content-calories').fill('180');
  // Exports and textures use each flavour's resolved values, including explicit blanks.
  const exports=await p.evaluate(async keys=>{
   await projectSettle();const out=[];
   for(const k of keys)out.push(await withFlavour(k,'Family',()=>{const cv=document.createElement('canvas');drawNet(cv,1024,{guides:false});return {job:jobJSON(1024),texture:cv.toDataURL()};}));return out;
  },keys);
  assert.equal(exports[0].job.packaging_content.backBody,'Only the first flavour.');
  assert.equal(exports[1].job.packaging_content.calories,'180');assert.equal(exports[0].job.packaging_content.calories,'150');
  assert.notEqual(exports[0].texture,exports[1].texture);
  const range=await p.evaluate(async()=>{await projectSettle();$('e-res').value='2048';const pkg=await buildRange('range');return Array.from(new Uint8Array(await pkg.blob.arrayBuffer()));});
  fs.writeFileSync('/private/tmp/daybreak-stage4-content-range.zip',Buffer.from(range));
  // Read the app's stored ZIP records and check actual packaged jobs.
  const buffer=Buffer.from(range),jobs=[];let at=0;
  while(buffer.readUInt32LE(at)===0x04034b50){const size=buffer.readUInt32LE(at+18),n=buffer.readUInt16LE(at+26),extra=buffer.readUInt16LE(at+28),name=buffer.subarray(at+30,at+30+n).toString(),start=at+30+n+extra;
   if(name.endsWith('_job.json'))jobs.push(JSON.parse(buffer.subarray(start,start+size)));at=start+size;
  }
  assert.equal(jobs.find(j=>j.flavour.key===keys[0]).packaging_content.calories,'150');
  assert.equal(jobs.find(j=>j.flavour.key===keys[1]).packaging_content.calories,'180');
  assert.ok(jobs.every(j=>j.content_checks && j.packaging_content.ingredients==='Whole grain oats, corn, salt.'));
  // Dimensions and content checks agree for all pack sizes; long side copy is flagged.
  assert.ok(await p.evaluate(async()=>{const old=state.content.shared.sideBody;state.content.shared.sideBody='Long side story '.repeat(1000);try{for(const size of ['Mini','Regular','Family','Mega'])if(!await withFlavour(state.rec.flavKey,size,()=>jobJSON(1024).content_checks.overflow.some(w=>w.panel==='LEFT')))return false;return true;}finally{state.content.shared.sideBody=old;}}));
  // Capture actual canvas text, proving content is typeset rather than only in metadata.
  const text=await p.evaluate(()=>{const c=document.createElement('canvas').getContext('2d'),out=[];c.fillText=(s)=>out.push(s);contentLayout(c,'RIGHT',{x:0,y:0,w:80,h:340},1);return out.join(' ');});
  assert.ok(text.includes('180'));assert.ok(text.includes('Whole grain oats'));assert.ok(text.includes('Total Fat 2g'));
  await p.locator('[data-ws-panel="BACK"]').click();await p.locator('#content-scope').selectOption('shared');
  await p.locator('#content-backBody').fill('Long packaging story '.repeat(600));
  assert.ok(await p.evaluate(()=>contentReport().overflow.some(w=>w.panel==='BACK')));
  assert.ok((await p.locator('[data-ws-panel="BACK"]').textContent()).includes('!'));
  await p.evaluate(()=>historyStep());assert.equal(await p.evaluate(()=>contentReport().overflow.some(w=>w.panel==='BACK')),false);
  await p.locator('[data-ws-panel="LEFT"]').click();await p.locator('#content-sideBody').fill('Recipe\nServe with your favourite topping.');
  const id=await p.evaluate(()=>SESSION.id);await p.evaluate(()=>sessionAutosave());
  await p.evaluate(()=>projectCreate('Content isolation'));assert.equal(await p.evaluate(()=>contentEffective().ingredients),'');
  await p.evaluate(id=>projectOpen(id),id);
  assert.equal(await p.evaluate(()=>contentEffective().ingredients),'Whole grain oats, corn, salt.');
  await p.reload();await p.waitForFunction(()=>SESSION.ready);
  assert.equal(await p.evaluate(()=>contentEffective(Object.keys(FLAVOURS)[1]).calories),'180');
  assert.equal(await p.evaluate(()=>contentEffective().sideBody),'Recipe\nServe with your favourite topping.');
  // Old sessions migrate with no fabricated values; malformed content is rejected.
  assert.deepEqual(await p.evaluate(()=>contentValidate(undefined)),{shared:{},flavours:{}});
  assert.ok(await p.evaluate(()=>{try{contentValidate({shared:{calories:'-2'},flavours:{}});return false;}catch{return true;}}));
  await p.locator('[data-ws-panel="RIGHT"]').click();await p.screenshot({path:'/private/tmp/daybreak-stage4-content.png'});
  assert.deepEqual(errors,[]);
  console.log('PASS: packaging editing, inheritance/overrides, blank clearing, undo/redo, validation, typesetting, overflow, per-flavour export, project isolation and reopen');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
