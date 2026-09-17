/* Der Seiten-Editor: Auszeichnung, Suchtext und die erzeugte Seite.
 *
 * Die Funktionen werden aus index.html herausgeschnitten und hier gegen VON
 * HAND geschriebene Erwartungen geprueft (Regelblatt 13). Kein Wert unten ist
 * aus der Ausgabe des Codes uebernommen.
 *
 * Aufruf:  node tests/test_editor.mjs
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
  assert.ok(m, `${name} nicht in index.html gefunden - Test anpassen`);
  return m[0];
}
const quellen = [
  hol(/const EDITOR_WERKZEUG = [^\n]+/, 'EDITOR_WERKZEUG'),
  hol(/const ED_BAUSTEINE = \{[\s\S]*?\n\};/, 'ED_BAUSTEINE'),
  hol(/function edBaustein\(art, titel, zeilen\)\{[\s\S]*?\n\}/, 'edBaustein'),
  hol(/const ED_STIL_BAUSTEINE = \[[\s\S]*?\]\.join\('\\n'\);/, 'ED_STIL_BAUSTEINE'),
  hol(/const ED_RECHENWERK = \[[\s\S]*?\]\.join\('\\n'\);/, 'ED_RECHENWERK'),
  hol(/const ED_HALT = [^\n]+/, 'ED_HALT'),
  hol(/function edEscape\(s\)\{[\s\S]*?\n\}/, 'edEscape'),
  hol(/function edInline\(s\)\{[\s\S]*?\n\}/, 'edInline'),
  hol(/function edBloecke\(text\)\{[\s\S]*?\n\}/, 'edBloecke'),
  hol(/function edNurText\(text\)\{[\s\S]*?\n\}/, 'edNurText'),
  hol(/function edSlug\(s\)\{[\s\S]*?\n\}/, 'edSlug'),
  /* ED_STIL endet seit den Bausteinen nicht mehr mit join, sondern haengt
     ED_STIL_BAUSTEINE an - das Muster muss das treffen, sonst frisst es den
     naechsten Block mit und der wird doppelt erklaert. */
  hol(/const ED_STIL = \[[\s\S]*?ED_STIL_BAUSTEINE;/, 'ED_STIL'),
  hol(/const ED_PFLICHTTEIL = \[[\s\S]*?\]\.join\('\\n'\);/, 'ED_PFLICHTTEIL'),
  hol(/function edListe\(s\)\{[\s\S]*?\n\}/, 'edListe'),
  hol(/function edPfadListe\(s\)\{[\s\S]*?\n\}/, 'edPfadListe'),
  hol(/function edSeiteBauen\(e\)\{[\s\S]*?\n\}/, 'edSeiteBauen'),
].join('\n');

const { edEscape, edInline, edBloecke, edNurText, edSlug, edSeiteBauen,
        ED_STIL, ED_PFLICHTTEIL, EDITOR_WERKZEUG, ED_BAUSTEINE,
        edBaustein, ED_RECHENWERK, ED_STIL_BAUSTEINE } =
  new Function(quellen + `
    return {edEscape, edInline, edBloecke, edNurText, edSlug, edSeiteBauen,
            ED_STIL, ED_PFLICHTTEIL, EDITOR_WERKZEUG, ED_BAUSTEINE,
            edBaustein, ED_RECHENWERK, ED_STIL_BAUSTEINE};`)();

/* Das Rechenwerk der erzeugten Seite - hier einzeln herausgeholt, damit die
   Formelauswertung geprueft werden kann, ohne einen Browser zu starten. */
const { bkRechnen, bkZahl } =
  new Function(ED_RECHENWERK + '\nreturn {bkRechnen, bkZahl};')();

let gut = 0, schlecht = 0;
function pruefe(name, fn) {
  try { fn(); console.log('ok     ' + name); gut++; }
  catch (e) { console.log('FEHLER ' + name + '\n       ' + e.message); schlecht++; }
}

/* ------------------------------------------------ getippter Text bleibt Text */
pruefe('HTML aus dem Text wird unschaedlich', () => {
  const h = edBloecke('Ein <script>alert(1)</script> im Satz.');
  assert.ok(!h.includes('<script>'), 'Skript-Tag steht roh im Ergebnis');
  assert.ok(h.includes('&lt;script&gt;'), 'Skript-Tag ist nicht geschuetzt');
});
pruefe('Auch im Codeblock bleibt HTML Text', () => {
  const h = edBloecke('```\n<img src=x onerror=boese()>\n```');
  assert.ok(h.startsWith('<pre><code>'));
  assert.ok(!h.includes('<img'), 'img-Tag steht roh im Codeblock');
  assert.ok(h.includes('&lt;img src=x onerror=boese()&gt;'));
});
pruefe('Anfuehrungszeichen in Attributnaehe sind geschuetzt', () => {
  assert.equal(edEscape('a"b<c>d&e'), 'a&quot;b&lt;c&gt;d&amp;e');
});

/* ------------------------------------------------ Auszeichnung */
pruefe('Fett und Code im Satz', () => {
  assert.equal(edInline('Ein **fetter** Satz mit `code`.'),
               'Ein <b>fetter</b> Satz mit <code>code</code>.');
});
pruefe('In Code gilt keine weitere Auszeichnung', () => {
  // Von Hand: die Sternchen stehen INNERHALB der Zaeune, bleiben also stehen.
  assert.equal(edInline('`**kein fett**`'), '<code>**kein fett**</code>');
});
pruefe('Verweis auf eine andere Seite wird ein Knopf, kein href', () => {
  const h = edInline('siehe [[git-und-github|die Git-Seite]]');
  assert.ok(h.includes('data-slug="git-und-github"'));
  assert.ok(h.includes('>die Git-Seite</button>'));
  assert.ok(!h.includes('href'), 'ein href waere ein Sprung im Rahmen');
});
pruefe('Verweis ohne Text nimmt die Kennung', () => {
  assert.ok(edInline('[[subnetze]]').includes('>subnetze</button>'));
});
pruefe('Absatz, Zwischentitel, Liste', () => {
  const h = edBloecke('Erster Absatz.\n\n## Titel\n- a\n- b');
  assert.ok(h.includes('<p>Erster Absatz.</p>'));
  assert.ok(h.includes('<h3>Titel</h3>'));
  assert.ok(h.includes('<ul><li>a</li><li>b</li></ul>'));
});
pruefe('Mehrzeiliger Absatz wird EIN p', () => {
  const h = edBloecke('Zeile eins\nZeile zwei\n\nNeuer Absatz');
  assert.equal((h.match(/<p>/g) || []).length, 2);
  assert.ok(h.includes('<p>Zeile eins Zeile zwei</p>'));
});
pruefe('Nummerierte Liste', () => {
  const h = edBloecke('1. eins\n2. zwei');
  assert.ok(h.includes('<ol><li>eins</li><li>zwei</li></ol>'));
});
pruefe('Die drei Kaesten', () => {
  assert.ok(edBloecke('> Hinweis').includes('<div class="merk">'));
  assert.ok(edBloecke('!> Warnung').includes('<div class="warn">'));
  assert.ok(edBloecke('?> Gut').includes('<div class="gut">'));
});
pruefe('Erste fette Zeile im Kasten wird die Ueberschrift', () => {
  const h = edBloecke('> **Merke**\n> Der Rest.');
  assert.ok(h.includes('<b>Merke</b>'));
  assert.ok(h.includes('Der Rest.'));
});
pruefe('Mehrzeiliger Kasten bleibt EIN Kasten', () => {
  const h = edBloecke('!> Erste Zeile\n!> Zweite Zeile');
  assert.equal((h.match(/class="warn"/g) || []).length, 1);
});
pruefe('Tabelle mit Trennzeile', () => {
  const h = edBloecke('| A | B |\n|---|---|\n| 1 | 2 |');
  assert.ok(h.includes('<div class="tabelle">'), 'Tabelle braucht den Scrollrahmen');
  assert.ok(h.includes('<th>A</th><th>B</th>'));
  assert.ok(h.includes('<td>1</td><td>2</td>'));
  assert.ok(!h.includes('---'), 'die Trennzeile ist keine Datenzeile');
});
pruefe('Tabelle ohne Trennzeile nimmt die erste Zeile als Kopf', () => {
  const h = edBloecke('| A | B |\n| 1 | 2 |');
  assert.ok(h.includes('<th>A</th>'));
  assert.ok(h.includes('<td>1</td>'));
});
pruefe('Codeblock behaelt Zeilenumbrueche', () => {
  const h = edBloecke('```\neins\nzwei\n```');
  assert.ok(h.includes('eins\nzwei'));
});
pruefe('Kein Sonderzeichen: einfach ein Absatz', () => {
  assert.equal(edBloecke('Nur ein Satz.'), '<p>Nur ein Satz.</p>');
});
pruefe('Leerer Text ergibt nichts', () => {
  assert.equal(edBloecke(''), '');
  assert.equal(edBloecke('   \n  \n'), '');
});

/* ------------------------------------------------ Suchstoff */
pruefe('Suchtext enthaelt keine Auszeichnungszeichen', () => {
  const t = edNurText('## Titel\n- **fett**\n- `code`\n\n| A | B |\n|---|---|\n| 1 | 2 |');
  assert.ok(!/[*`|#]/.test(t), 'Auszeichnung steht noch im Suchtext: ' + t);
  assert.ok(t.includes('Titel') && t.includes('fett') && t.includes('code'));
  assert.ok(t.includes('A') && t.includes('1'));
});
pruefe('Suchtext nimmt den sichtbaren Text eines Verweises', () => {
  assert.equal(edNurText('siehe [[subnetze|die Netzseite]]'), 'siehe die Netzseite');
});
pruefe('Trennzeile der Tabelle steht nicht im Suchtext', () => {
  assert.ok(!edNurText('| A |\n|---|\n| 1 |').includes('-'));
});

/* ------------------------------------------------ Kennungen */
pruefe('Kennung aus Titel: Umlaute ausgeschrieben', () => {
  // Von Hand: "Über Ölwechsel & Wartung!" -> ueber-oelwechsel-wartung
  assert.equal(edSlug('Über Ölwechsel & Wartung!'), 'ueber-oelwechsel-wartung');
});
pruefe('Kennung ohne Bindestrich am Rand', () => {
  assert.equal(edSlug('  !!! Hallo !!!  '), 'hallo');
});
pruefe('Kennung aus Ziffern bleibt erhalten', () => {
  assert.equal(edSlug('IPv6 in 2026'), 'ipv6-in-2026');
});
pruefe('Alle vier deutschen Sonderbuchstaben', () => {
  /* Die Gegenprobe hat gezeigt, dass ein Test mit nur U- und O-Umlaut die
     Zeile fuer den A-Umlaut nicht abdeckt: ohne sie wuerde aus "Zaehler"
     ein "Zahler", und der Test blieb gruen. */
  assert.equal(edSlug('Zählerstände'), 'zaehlerstaende');
  assert.equal(edSlug('Öltürme'), 'oeltuerme');
  assert.equal(edSlug('Straße'), 'strasse');
});

/* ------------------------------------------------ die erzeugte Seite */
const seite = edSeiteBauen({
  titel: 'Drucker im Büro', slug: 'drucker-im-buero',
  kurz: 'Wie der Drucker eingerichtet wird.',
  pfad: 'Technik / Geräte', gruppen: 'wiki-technik',
  stand: '2026-09-15',
  abschnitte: [
    {anker: 'anschliessen', titel: 'Anschließen', stichworte: 'Kabel, Strom',
     markup: 'Erst das **Netzkabel**.\n\n| A | B |\n|---|---|\n| 1 | 2 |'},
    {anker: 'treiber', titel: 'Treiber', stichworte: '',
     markup: 'Der Treiber kommt aus dem Netz.'}
  ]});

pruefe('Seite hat den Meta-Block mit allen Pflichtfeldern', () => {
  const m = seite.match(/<script type="application\/json" id="wiki-meta">([\s\S]*?)<\/script>/);
  assert.ok(m, 'kein Meta-Block');
  const meta = JSON.parse(m[1]);
  assert.equal(meta.slug, 'drucker-im-buero');
  assert.equal(meta.titel, 'Drucker im Büro');
  assert.deepEqual(meta.pfad, ['Technik', 'Geräte']);
  assert.deepEqual(meta.gruppen, ['wiki-technik']);
  assert.equal(meta.werkzeug, EDITOR_WERKZEUG);
  assert.equal(meta.abschnitte.length, 2);
});
pruefe('Jeder Anker hat ein Element mit derselben id', () => {
  const m = seite.match(/id="wiki-meta">([\s\S]*?)<\/script>/);
  const meta = JSON.parse(m[1]);
  for (const a of meta.abschnitte)
    assert.ok(seite.includes(`<section id="${a.anker}">`),
              `zum Anker ${a.anker} fehlt das Element`);
});
pruefe('Die Quelle steht im Meta-Block, der Suchtext ohne Auszeichnung', () => {
  const meta = JSON.parse(seite.match(/id="wiki-meta">([\s\S]*?)<\/script>/)[1]);
  const a = meta.abschnitte[0];
  assert.ok(a.markup.includes('**Netzkabel**'), 'ohne markup ist die Seite nicht editierbar');
  assert.ok(!a.text.includes('**'), 'der Suchtext darf keine Sternchen haben');
  assert.ok(a.text.includes('Netzkabel'));
});
pruefe('Pflichtangaben der Huelle: lang, viewport, focus-visible', () => {
  assert.ok(/<html lang="de">/.test(seite));
  assert.ok(/name="viewport"/.test(seite));
  assert.ok(seite.includes('focus-visible'), 'ohne das warnt die Importpruefung');
  assert.ok(seite.includes('prefers-reduced-motion'));
});
pruefe('Farben nur in :root und body[data-theme]', () => {
  /* Die Importpruefung sucht Farbwerte ausserhalb des Tokenblocks. Also darf
     im Stil hinter dem Tokenblock kein oklch(/#rgb mehr stehen. */
  const nachTokens = ED_STIL.split('body{margin:0')[1] || '';
  assert.ok(!/oklch\(|#[0-9a-fA-F]{3,6}\b/.test(nachTokens),
            'Farbwert ausserhalb des Tokenblocks im Stil');
});
pruefe('Pflichtteil hoert auf die Huelle', () => {
  assert.ok(ED_PFLICHTTEIL.includes("e.data.typ === 'wiki-springen'"));
  assert.ok(ED_PFLICHTTEIL.includes('e.source !== window.parent'),
            'ohne die Pruefung nimmt die Seite Nachrichten von jedem an');
  assert.ok(ED_PFLICHTTEIL.includes("typ:'wiki-bereit'"));
});
pruefe('Pflichtteil setzt das Thema vor dem ersten Anstrich (N-06)', () => {
  assert.ok(ED_PFLICHTTEIL.includes('prefers-color-scheme: dark'),
            'ohne das blitzt die dunkle Fassung auf');
});
pruefe('Pflichtteil laesst script und style aus (N-07)', () => {
  assert.ok(ED_PFLICHTTEIL.includes('FILTER_REJECT'),
            'ohne acceptNode markiert die Suche Skriptkommentare');
  assert.ok(ED_PFLICHTTEIL.includes("e.tagName === 'SCRIPT'"));
});
pruefe('Keine externen Verweise in der erzeugten Seite', () => {
  /* Die Importpruefung weist externe Verweise ab - eine erzeugte Seite darf
     also gar keine enthalten. */
  const extern = seite.match(/(?:src|href)=["'](\s*(?:https?:)?\/\/[^"']+|javascript:[^"']*)["']/gi);
  assert.equal(extern, null, 'externer Verweis: ' + extern);
});
pruefe('Ein Abschnitt ohne Text erzeugt trotzdem eine gueltige Seite', () => {
  const s = edSeiteBauen({titel: 'T', slug: 't', pfad: 'A',
                          abschnitte: [{anker: 'x', titel: 'X', markup: ''}]});
  assert.ok(s.includes('<section id="x">'));
  const meta = JSON.parse(s.match(/id="wiki-meta">([\s\S]*?)<\/script>/)[1]);
  assert.equal(meta.abschnitte[0].text, '');
});
pruefe('Titel mit Sonderzeichen bleibt im Titel-Tag geschuetzt', () => {
  const s = edSeiteBauen({titel: 'A < B & "C"', slug: 'a', pfad: 'A',
                          abschnitte: [{anker: 'x', titel: 'X', markup: 'y'}]});
  assert.ok(s.includes('<title>A &lt; B &amp; &quot;C&quot;</title>'));
});

/* ------------------------------------------------ Reihenfolge im Skript */
pruefe('Bausteinteile stehen VOR ihrer Verwendung (N-14)', () => {
  /* const wird nicht hochgezogen. Steht ED_STIL_BAUSTEINE hinter ED_STIL,
     stirbt beim Laden das ganze Skript ("Cannot access ... before
     initialization") und das Wiki zeigt gar nichts mehr. Der Browser hat das
     gefunden, die Tests nicht - weil sie die Stuecke in eigener Reihenfolge
     zusammensetzen. Darum diese Prueflinie auf die Datei selbst. */
  const paare = [['const ED_STIL_BAUSTEINE = [', 'const ED_STIL = ['],
                 ['const ED_RECHENWERK = [', 'const ED_PFLICHTTEIL = [']];
  for (const [zuerst, danach] of paare) {
    const a = quelle.indexOf(zuerst), b = quelle.indexOf(danach);
    assert.ok(a > -1, zuerst + ' fehlt');
    assert.ok(b > -1, danach + ' fehlt');
    assert.ok(a < b, zuerst + ' muss vor ' + danach + ' stehen');
  }
});

/* ------------------------------------------------ Bausteine */
pruefe('Jeder Baustein hat Name, Hilfe und Vorlage', () => {
  for (const [art, b] of Object.entries(ED_BAUSTEINE)) {
    assert.ok(b.name && b.hilfe && b.vorlage, art + ' unvollstaendig');
    // Die Vorlage muss das sein, was der Editor auch lesen kann.
    assert.ok(b.vorlage.startsWith(':::' + art), art + ': Vorlage passt nicht');
    assert.ok(b.vorlage.trimEnd().endsWith(':::'), art + ': Vorlage ohne Ende');
  }
});
pruefe('Baustein im Text wird erkannt und gerendert', () => {
  const h = edBloecke('Davor.\n\n:::klapp Warum?\nWeil.\n:::\n\nDanach.');
  assert.ok(h.includes('<p>Davor.</p>'));
  assert.ok(h.includes('<details class="bk bk-klapp">'));
  assert.ok(h.includes('<p>Danach.</p>'));
});
pruefe('Ein Absatz laeuft nicht in einen Baustein hinein', () => {
  const h = edBloecke('Satz eins\n:::klapp Titel\nInhalt\n:::');
  assert.ok(h.includes('<p>Satz eins</p>'), 'der Absatz muss vorher endeN: ' + h);
});
pruefe('Schritte werden nummeriert und aufgeteilt', () => {
  const h = edBaustein('schritte', 'Anschliessen', ['Strom | Kabel rein.', 'Netz | Dose links.']);
  assert.equal((h.match(/<li>/g) || []).length, 2);
  assert.ok(h.includes('<b>Strom</b>'));
  assert.ok(h.includes('Kabel rein.'));
});
pruefe('Kennzahlen: Wert gross, Name klein', () => {
  const h = edBaustein('kennzahlen', 'Blick', ['MTU | 1500 | Byte']);
  assert.ok(h.includes('<span class="bk-wert">1500</span>'));
  assert.ok(h.includes('<span class="bk-name">MTU</span>'));
  assert.ok(h.includes('Byte'));
});
pruefe('Gegenueberstellung nimmt hoechstens vier Seiten', () => {
  const h = edBaustein('gegenueber', 'X', ['a|1', 'b|2', 'c|3', 'd|4', 'e|5']);
  assert.equal((h.match(/class="bk-seite"/g) || []).length, 4);
});
pruefe('Begriffsliste wird eine Tabelle im Scrollrahmen', () => {
  const h = edBaustein('begriffe', 'Begriffe', ['MTU | Groesstes Paket.']);
  assert.ok(h.includes('<div class="tabelle">'));
  assert.ok(h.includes('<th scope="row">MTU</th>'));
});
pruefe('Unbekannter Baustein wird gezeigt, nicht verschluckt', () => {
  const h = edBaustein('flugzeug', 'Titel', ['Inhalt']);
  assert.ok(h.includes('Unbekannter Baustein'));
  assert.ok(h.includes('Inhalt'), 'der Text darf nicht verloren gehen');
});
pruefe('Baustein-Text bleibt im Suchstoff, die Zeichen nicht', () => {
  const t = edNurText(':::kennzahlen Auf einen Blick\nMTU | 1500 | Byte\n:::');
  assert.ok(!t.includes(':::'), 'Zaeune im Suchtext: ' + t);
  assert.ok(!t.includes('kennzahlen'), 'die Art ist kein Inhalt: ' + t);
  assert.ok(t.includes('Auf einen Blick') && t.includes('MTU') && t.includes('1500'));
});
pruefe('HTML im Baustein bleibt Text', () => {
  const h = edBaustein('schritte', '<script>x</script>', ['<img onerror=x> | y']);
  assert.ok(!h.includes('<script>'));
  assert.ok(!h.includes('<img'));
});

/* ------------------------------------------------ Rechner */
pruefe('Rechner: Felder, Formel und Einheit werden gelesen', () => {
  const h = edBaustein('rechner', 'Kosten', [
    'Verbrauch in kWh = 18', 'Preis je kWh = 0,32', '= Verbrauch * Preis',
    'Einheit: €', 'Ein Hinweis.']);
  assert.ok(h.includes('data-formel="Verbrauch * Preis"'));
  assert.ok(h.includes('data-einheit="€"'));
  assert.ok(h.includes('data-feld="Verbrauch"'));
  assert.ok(h.includes('data-feld="Preis"'));
  assert.ok(h.includes('value="18"'));
  assert.ok(h.includes('Ein Hinweis.'));
});
pruefe('Rechenwerk: Punkt vor Strich, von Hand gerechnet', () => {
  // 2 + 3 * 4 = 14, nicht 20.
  assert.equal(bkRechnen('2 + 3 * 4', {}), 14);
  assert.equal(bkRechnen('(2 + 3) * 4', {}), 20);
  assert.equal(bkRechnen('10 / 4', {}), 2.5);
  assert.equal(bkRechnen('-3 + 5', {}), 2);
});
pruefe('Rechenwerk: Feldnamen und deutsche Kommazahlen', () => {
  // 18 * 0,32 = 5,76 - von Hand.
  assert.equal(bkRechnen('a * b', {a: 18, b: 0.32}), 5.76);
  assert.equal(bkRechnen('18 * 0,32', {}), 5.76);
  assert.equal(bkRechnen('Verbrauch * Preis', {Verbrauch: 20, Preis: 0.45}), 9);
});
pruefe('Rechenwerk: fehlendes Feld ergibt keine Zahl', () => {
  assert.ok(Number.isNaN(bkRechnen('a * b', {a: 18})));
  assert.ok(Number.isNaN(bkRechnen('a * b', {a: 18, b: ''})));
});
pruefe('Rechenwerk: Teilen durch Null ergibt keine Zahl', () => {
  assert.ok(Number.isNaN(bkRechnen('a / b', {a: 5, b: 0})));
});
pruefe('Rechenwerk fuehrt keinen Code aus', () => {
  /* Der Kern: es ist kein eval. Alles, was nicht Zahl, Feld oder
     + - * / ( ) ist, muss zu "keine Zahl" fuehren - nicht zu einem
     Funktionsaufruf. */
  for (const formel of ['alert(1)', 'a.constructor', 'a; b', 'a ? 1 : 2',
                        'fetch("/")', '1 && 2', 'a**b', '[1,2]']) {
    const w = bkRechnen(formel, {a: 1, b: 2});
    assert.ok(Number.isNaN(w), formel + ' ergab ' + w);
  }
});
pruefe('Zahlenanzeige: deutsche Schreibweise, sinnvolle Stellen', () => {
  assert.equal(bkZahl(5.76), '5,76');
  assert.equal(bkZahl(0.3245), '0,325');       // unter 1: drei Stellen
  assert.equal(bkZahl(1234.5), '1.234,5');
  assert.equal(bkZahl(NaN), '\u2014');
  assert.equal(bkZahl(Infinity), '\u2014');
});
pruefe('Die erzeugte Seite bringt Stil und Rechenwerk mit', () => {
  const s = edSeiteBauen({titel:'T', slug:'t', pfad:'A', abschnitte:[
    {anker:'x', titel:'X', markup:':::rechner K\na = 2\n= a * 2\n:::'}]});
  assert.ok(s.includes('bkRechnen'), 'ohne Rechenwerk rechnet nichts');
  assert.ok(s.includes('bkRechnerStarten()'), 'das Rechenwerk wird nicht gestartet');
  assert.ok(s.includes('.bk-erg-wert'), 'der Stil der Bausteine fehlt');
});

console.log('');
console.log(`${gut} ok, ${schlecht} Fehler`);
process.exit(schlecht ? 1 : 0);
