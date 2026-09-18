/* Darstellung, drei Zustaende (B-11).
 *
 * themaAnwenden() wird aus index.html herausgeschnitten und gegen ein
 * nachgebildetes matchMedia geprueft - beide Systemzustaende, alle drei
 * Wahlmoeglichkeiten.
 *
 * Aufruf:  node tests/test_thema.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import assert from 'node:assert/strict';
const HIER = dirname(fileURLToPath(import.meta.url));
const q = readFileSync(join(HIER, '..', 'index.html'), 'utf8');
const src = q.slice(q.indexOf('const SYSTEM_DUNKEL=window.matchMedia'),
                    q.indexOf('/* Folgt der Systemeinstellung'));
let ok=0,bad=0;
const t=(n,f)=>{try{f();console.log('ok     '+n);ok++;}catch(e){console.log('FEHLER '+n+': '+e.message);bad++;}};

function bauen(systemDunkel){
  const body={dataset:{}};
  const store={};
  const window={matchMedia:()=>({matches:systemDunkel})};
  const localStorage={setItem:(k,v)=>{store[k]=v;},getItem:k=>store[k]};
  const fn=new Function('window','document','localStorage',
    src+'\nreturn {themaAnwenden,SYSTEM_DUNKEL,THEMA_SCHLUESSEL};');
  const api=fn(window,{body},localStorage);
  return {...api, body, store};
}

t('Dunkel gewaehlt -> dark, unabhaengig vom System', ()=>{
  for (const sys of [true,false]) {
    const a=bauen(sys); a.themaAnwenden('dunkel');
    assert.equal(a.body.dataset.theme,'dark');
  }
});
t('Hell gewaehlt -> light, unabhaengig vom System', ()=>{
  for (const sys of [true,false]) {
    const a=bauen(sys); a.themaAnwenden('hell');
    assert.equal(a.body.dataset.theme,'light');
  }
});
t('System bei dunklem Geraet -> dark', ()=>{
  const a=bauen(true); a.themaAnwenden('system');
  assert.equal(a.body.dataset.theme,'dark');
});
t('System bei hellem Geraet -> light', ()=>{
  const a=bauen(false); a.themaAnwenden('system');
  assert.equal(a.body.dataset.theme,'light');
});
t('Voreinstellung ist System (CLAUDE.md §6a)', ()=>{
  const a=bauen(false);
  assert.equal(a.themaAnwenden(undefined),'system');
  assert.equal(a.body.dataset.theme,'light');
  assert.equal(a.themaAnwenden('quatsch'),'system');
});
t('Die Wahl landet im Zwischenspeicher', ()=>{
  const a=bauen(true); a.themaAnwenden('hell');
  assert.equal(a.store[a.THEMA_SCHLUESSEL],'hell');
});
t('Drei Zustaende, nicht zwei', ()=>{
  const a=bauen(true);
  assert.deepEqual(['system','hell','dunkel'].map(w=>a.themaAnwenden(w)),
                   ['system','hell','dunkel']);
});
console.log('\n'+ok+' ok, '+bad+' Fehler');
process.exit(bad?1:0);
