import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium', args:['--allow-file-access-from-files','--use-gl=swiftshader','--enable-unsafe-swiftshader'] });
const p = await (await b.newContext({viewport:{width:1500,height:940}})).newPage();
p.on('console',m=>console.log('console:', m.type(), m.text().slice(0,200)));
await p.goto('file:///home/claude/daybreak-mills/app/daybreak-studio.html'); await p.waitForTimeout(500);
const r = await p.evaluate(async ()=>{
  try { const r = await fetch('http://127.0.0.1:8765/status'); return 'OK '+r.status+' '+(await r.text()).slice(0,80); }
  catch(e){ return 'ERR '+e.name+': '+e.message; }
});
console.log('direct fetch:', r);
const r2 = await p.evaluate(async ()=>{ try { await pingBridge(); return {bridge: !!bridge, pill: document.getElementById('bridge-pill').textContent.slice(0,50)}; } catch(e){ return 'THREW '+e.message; } });
console.log('pingBridge():', JSON.stringify(r2));
await b.close();
