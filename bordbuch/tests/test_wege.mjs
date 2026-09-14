/* Wege der Oberflaeche (B-10).
 *
 * Die Routentabelle und wegLesen() werden aus index.html herausgeschnitten und
 * hier gegen eine nachgebildete location geprueft - nicht nachgebaut, sonst
 * pruefte der Test eine Kopie und nicht den Code, der laeuft.
 *
 * Aufruf:  node tests/test_wege.mjs
 */
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
const HIER = dirname(fileURLToPath(import.meta.url));
const q = readFileSync(join(HIER, '..', 'index.html'), 'utf8');
const src = q.slice(q.indexOf('const WEGE={'), q.indexOf('function wegSetzen'));
// location nachbilden
let loc = { pathname:'/', search:'', protocol:'https:' };
const { WEGE, NACH_WEG, wegLesen } =
  new Function('location', src + '\nreturn {WEGE,NACH_WEG,wegLesen};')(loc);

let ok=0, bad=0;
const t=(n,f)=>{try{f();console.log('ok     '+n);ok++;}catch(e){console.log('FEHLER '+n+': '+e.message);bad++;}};

t('Wurzel ergibt die Uebersicht', ()=>{
  loc.pathname='/'; assert.equal(wegLesen(),'overview');
});
t('/einstellungen ergibt settings', ()=>{
  loc.pathname='/einstellungen'; assert.equal(wegLesen(),'settings');
});
t('Schraegstrich am Ende stoert nicht', ()=>{
  loc.pathname='/wartung/'; assert.equal(wegLesen(),'wartung');
});
t('Unbekannter Weg faellt auf die Uebersicht', ()=>{
  loc.pathname='/gibtsnicht'; assert.equal(wegLesen(),'overview');
});
t('Tiefere Ebene nimmt den ersten Teil', ()=>{
  loc.pathname='/bericht/2026'; assert.equal(wegLesen(),'report');
});
t('Jeder Weg fuehrt zurueck zu sich selbst', ()=>{
  for (const [weg,tab] of Object.entries(WEGE)) {
    assert.equal(NACH_WEG[tab], weg, 'Rueckweg fuer '+tab);
    loc.pathname='/'+weg;
    assert.equal(wegLesen(), tab, 'Weg '+weg);
  }
});
t('NACH_WEG deckt alle Reiter ab', ()=>{
  const ziele=new Set(Object.values(WEGE));
  assert.equal(ziele.size, Object.keys(WEGE).length, 'kein Ziel doppelt');
  assert.equal(Object.keys(NACH_WEG).length, ziele.size);
});
console.log('\n'+ok+' ok, '+bad+' Fehler');
process.exit(bad?1:0);
