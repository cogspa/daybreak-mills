import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium', args:['--allow-file-access-from-files','--use-gl=swiftshader','--enable-unsafe-swiftshader'] });
const p = await (await b.newContext({viewport:{width:1500,height:940}})).newPage();
await p.goto('file:///home/claude/daybreak-mills/app/daybreak-studio.html'); await p.waitForTimeout(500);
await p.click('#b-apply'); await p.waitForTimeout(300); await p.click('[data-tab="out"]'); await p.waitForTimeout(2000);
console.log('pill:', (await p.textContent('#bridge-pill')).trim().slice(0,70));
console.log('deploy enabled:', !(await p.isDisabled('#deploy-range')));
await b.close();
