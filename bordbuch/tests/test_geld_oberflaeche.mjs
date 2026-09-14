/* Geldrechnung der Oberflaeche (B-04).
 *
 * Die Helfer werden aus index.html herausgeschnitten und hier gegen VON HAND
 * gerechnete Erwartungswerte geprueft (Regelblatt 13). Kein Wert unten ist aus
 * der Ausgabe des Codes uebernommen.
 *
 * Aufruf:  node tests/test_geld_oberflaeche.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import assert from 'node:assert/strict';

const HIER = dirname(fileURLToPath(import.meta.url));
const quelle = readFileSync(join(HIER, '..', 'index.html'), 'utf8');

/* Genau die Zeilen aus index.html verwenden, nicht nachgebaut - sonst prueft
   der Test eine Kopie und nicht den Code, der laeuft. */
function hol(muster, name) {
  const m = quelle.match(muster);
  assert.ok(m, `Helfer ${name} nicht in index.html gefunden - Test anpassen`);
  return m[0];
}
const quellen = [
  hol(/const ct=v=>\{[\s\S]*?\};/, 'ct'),
  hol(/const cz=v=>\{[^\n]+/, 'cz'),
  hol(/const ctZahl=c=>[^\n]+/, 'ctZahl'),
  hol(/const summeCt=\(l,f\)=>[^\n]+/, 'summeCt'),
  hol(/function nettoCtAus\(bruttoCt\)\{[^\n]+/, 'nettoCtAus'),
  hol(/function sum\(l\)\{[\s\S]*?return \{\.\.\.a,cost:ctZahl\(a\.costCt\),net:ctZahl\(a\.netCt\),vat:ctZahl\(a\.vatCt\)\};\}/, 'sum'),
].join('\n');

const vatSatz = () => 19;
const { ct, cz, ctZahl, summeCt, nettoCtAus, sum } =
  new Function('vatSatz', quellen + '\nreturn {ct,cz,ctZahl,summeCt,nettoCtAus,sum};')(vatSatz);

let gut = 0, schlecht = 0;
function pruefe(name, fn) {
  try { fn(); console.log('ok     ' + name); gut++; }
  catch (e) { console.log('FEHLER ' + name + '\n       ' + e.message); schlecht++; }
}

pruefe('ct: Euro-Eingabe wird Cent-Ganzzahl', () => {
  // Von Hand: 12,34 EUR = 1234 Cent.
  assert.equal(ct(12.34), 1234);
  assert.equal(ct('12.34'), 1234);
  assert.equal(ct(0), 0);
  assert.equal(ct(8.72), 872);
});

pruefe('ct: kaufmaennisch aufwaerts', () => {
  // Von Hand: 8,995 EUR -> 900 Cent (Math.round rundet .5 aufwaerts).
  assert.equal(ct(8.995), 900);
  // Von Hand: 8,994 EUR -> 899 Cent.
  assert.equal(ct(8.994), 899);
});

pruefe('ct: Unsinn wird 0, nicht NaN', () => {
  // In der Oberflaeche darf kein NaN in eine Summe geraten - das faerbt die
  // ganze Summe auf NaN. Geprueft wird die Eingabe serverseitig (B-05).
  assert.equal(ct(undefined), 0);
  assert.equal(ct(null), 0);
  assert.equal(ct('abc'), 0);
});

pruefe('Summe: der Fall aus dem Bericht ist exakt', () => {
  // Von Hand: 0,10 + 0,10 + 0,10 + 8,72 = 9,02 EUR = 902 Cent.
  const liste = [{costCt: 10}, {costCt: 10}, {costCt: 10}, {costCt: 872}];
  assert.equal(summeCt(liste, x => x.costCt), 902);
  assert.equal(ctZahl(902), 9.02);
  // Der Gegenbeweis: dieselbe Summe als Fliesskomma ist nicht 9,02.
  assert.notEqual(0.10 + 0.10 + 0.10 + 8.72, 9.02);
});

pruefe('sum(): Geldfelder laufen ueber Cent', () => {
  // Von Hand: 3 Ladungen zu 10 Cent und eine zu 872 Cent = 902 Cent.
  // kWh: 1 + 1 + 1 + 1 = 4.
  const l = [10, 10, 10, 872].map(c => ({costCt: c, netCt: nettoCtAus(c),
    vatCt: c - nettoCtAus(c), kwh: 1, liters: 0, sec: 0, km: 0}));
  const t = sum(l);
  assert.equal(t.costCt, 902);
  assert.equal(t.cost, 9.02);
  assert.equal(t.kwh, 4);
  assert.equal(t.n, 4);
  // Netto + MwSt muss auch in der Summe genau Brutto ergeben.
  assert.equal(t.netCt + t.vatCt, t.costCt);
});

pruefe('sum(): leere Liste', () => {
  // Grenzfall: keine Daten.
  const t = sum([]);
  assert.equal(t.costCt, 0);
  assert.equal(t.cost, 0);
  assert.equal(t.n, 0);
});

pruefe('sum(): tausend kleine Betraege bleiben exakt', () => {
  // Von Hand: 1000 mal 1 Cent = 1000 Cent = 10,00 EUR.
  const l = Array.from({length: 1000}, () => ({costCt: 1}));
  assert.equal(sum(l).costCt, 1000);
  assert.equal(sum(l).cost, 10);
  // Als Fliesskomma driftet dieselbe Summe von 10 ab.
  let f = 0; for (let i = 0; i < 1000; i++) f += 0.01;
  assert.notEqual(f, 10);
});

pruefe('sum(): fehlende Cent-Felder zaehlen als 0, nicht als NaN', () => {
  // Grenzfall fehlende Daten: ein Satz ohne costCt darf die Summe nicht
  // auf NaN faerben.
  const t = sum([{costCt: 100}, {}, {costCt: 50}]);
  assert.equal(t.costCt, 150);
});

pruefe('nettoCtAus: 19 % von Hand', () => {
  // Von Hand: 499 Cent / 1,19 = 419,3277... -> 419 Cent netto.
  // MwSt = 499 - 419 = 80 Cent.
  assert.equal(nettoCtAus(499), 419);
  assert.equal(499 - nettoCtAus(499), 80);
});

pruefe('nettoCtAus: Netto plus MwSt ist immer Brutto', () => {
  for (let b = 0; b <= 5000; b++) {
    const n = nettoCtAus(b);
    assert.equal(n + (b - n), b, 'brutto=' + b);
  }
});

pruefe('Jahressumme aus vielen Belegen', () => {
  // Von Hand: 365 mal 4,99 EUR = 365 * 499 = 182135 Cent = 1821,35 EUR.
  const l = Array.from({length: 365}, () => ({costCt: 499}));
  assert.equal(sum(l).costCt, 182135);
  assert.equal(sum(l).cost, 1821.35);
});

console.log('\n' + gut + ' ok, ' + schlecht + ' Fehler');
process.exit(schlecht ? 1 : 0);
