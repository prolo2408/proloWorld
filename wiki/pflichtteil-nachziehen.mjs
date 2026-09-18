/* Den Pflichtteil in allen mitgelieferten Seiten auf den Stand der Huelle
 * bringen.
 *
 * Jede Wiki-Seite traegt ihren Pflichtteil selbst - das ist Absicht: sie ist
 * eigenstaendig und laeuft in einem abgeschotteten Rahmen. Der Preis ist,
 * dass eine Korrektur am Pflichtteil die Seiten NICHT von selbst erreicht.
 * Eine gespeicherte Seite behaelt den Code, mit dem sie gebaut wurde, bis
 * jemand sie neu speichert.
 *
 * Fuer die Seiten im Repository macht das dieses Skript. Es ersetzt nur den
 * Pflichtteil und laesst Inhalt, Meta-Block und Stil in Ruhe - darum geht es
 * auch bei Seiten, die von Hand gebaut sind und kein "markup" im Meta-Block
 * haben.
 *
 * Aufruf:  node pflichtteil-nachziehen.mjs           (nur nachsehen)
 *          node pflichtteil-nachziehen.mjs --schreiben
 */
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HIER = dirname(fileURLToPath(import.meta.url));
const quelle = readFileSync(join(HIER, 'index.html'), 'utf8');

function hol(muster, name) {
  const m = quelle.match(muster);
  if (!m) throw new Error(name + ' nicht in index.html gefunden');
  return m[0];
}
/* Genau die Zeilen aus der Huelle verwenden - sonst zieht das Skript eine
   Kopie nach und nicht den Code, der laeuft. */
const teile = [
  hol(/function bkRechnen\(formel, werte\)\{[\s\S]*?\n\}/, 'bkRechnen'),
  hol(/function bkZahl\(x\)\{[\s\S]*?\n\}/, 'bkZahl'),
  hol(/function bkRechnerStarten\(wurzel\)\{[\s\S]*?\n\}/, 'bkRechnerStarten'),
  hol(/const ED_RECHENWERK = \[[\s\S]*?\}\)\)\.join\('\\n'\);/, 'ED_RECHENWERK'),
  hol(/const ED_PFLICHTTEIL = \[[\s\S]*?\]\.join\('\\n'\);/, 'ED_PFLICHTTEIL'),
].join('\n');
const { ED_PFLICHTTEIL } =
  new Function(teile + '\nreturn {ED_PFLICHTTEIL};')();

/* Der Pflichtteil einer Seite: von seinem Kommentar bis zum Ende des
   Skriptblocks. Der Kommentar steht in der ersten Zeile und ist die
   eindeutige Marke - ohne ihn wuerde das Muster auch andere Skripte der
   Seite treffen. */
/* "Shell" steht noch in den zwei aeltesten Seiten - beide Schreibweisen
   muessen treffen, sonst zieht das Skript genau die nicht nach, die es am
   noetigsten haben. */
const MARKE = /\/\* Pflichtteil jeder Wiki-Seite: auf die (?:Huelle|Shell) hoeren\. \*\//;
const MUSTER = /<script>\s*\/\* Pflichtteil jeder Wiki-Seite: auf die (?:Huelle|Shell) hoeren\. \*\/[\s\S]*?<\/script>/;

export function pflichtteilErsetzen(html) {
  if (!MUSTER.test(html)) return null;
  return html.replace(MUSTER, () => ED_PFLICHTTEIL);
}

function seiten() {
  const aus = [join(HIER, 'test-seite.html')];
  for (const n of readdirSync(join(HIER, 'vorlagen')).sort())
    if (n.endsWith('.html')) aus.push(join(HIER, 'vorlagen', n));
  return aus;
}

const schreiben = process.argv.includes('--schreiben');
let alt = 0;
for (const pfad of seiten()) {
  const html = readFileSync(pfad, 'utf8');
  const name = pfad.split('/').slice(-2).join('/');
  if (!MARKE.test(html)) { console.log('??  ' + name + ' — kein Pflichtteil gefunden'); alt++; continue; }
  const neu = pflichtteilErsetzen(html);
  if (neu === html) { console.log('ok  ' + name); continue; }
  alt++;
  if (schreiben) { writeFileSync(pfad, neu); console.log('neu ' + name); }
  else console.log('ALT ' + name + ' — Pflichtteil ist nicht auf dem Stand');
}
if (!schreiben && alt) {
  console.log('\n' + alt + ' Seite(n) nachzuziehen:  node pflichtteil-nachziehen.mjs --schreiben');
  process.exit(1);
}
console.log('\n' + (alt ? alt + ' Seite(n) nachgezogen.' : 'Alle Seiten auf dem Stand.'));
