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
  /* Das Rechenwerk steht seit der CSP-Probe als echte Funktion in der Huelle
     (kein new Function mehr, das verbietet die CSP). ED_RECHENWERK baut sich
     daraus mit toString() - also muessen hier beide Teile herausgeholt
     werden, sonst faellt die Auswertung auf eine leere Zeichenkette. */
  hol(/function bkRechnen\(formel, werte\)\{[\s\S]*?\n\}/, 'bkRechnen'),
  hol(/function bkZahl\(x\)\{[\s\S]*?\n\}/, 'bkZahl'),
  hol(/function bkRechnerStarten\(wurzel\)\{[\s\S]*?\n\}/, 'bkRechnerStarten'),
  hol(/const ED_RECHENWERK = \[[\s\S]*?\}\)\)\.join\('\\n'\);/, 'ED_RECHENWERK'),
  hol(/const ED_HALT = [^\n]+/, 'ED_HALT'),
  hol(/function edEscape\(s\)\{[\s\S]*?\n\}/, 'edEscape'),
  hol(/function edInline\(s\)\{[\s\S]*?\n\}/, 'edInline'),
  hol(/function edBloecke\(text\)\{[\s\S]*?\n\}/, 'edBloecke'),
  hol(/function edNurText\(text\)\{[\s\S]*?\n\}/, 'edNurText'),
  hol(/function edSlug\(s\)\{[\s\S]*?\n\}/, 'edSlug'),
  hol(/const ED_FORM = \{[\s\S]*?\n\};/, 'ED_FORM'),
  hol(/function edBlockNeu\(art\)\{[\s\S]*?\n\}/, 'edBlockNeu'),
  hol(/function edMarkupZuBloecken\(markup\)\{[\s\S]*?\n\}/, 'edMarkupZuBloecken'),
  hol(/function edBlockLesen\(art, titel, zeilen\)\{[\s\S]*?\n\}/, 'edBlockLesen'),
  hol(/function edBlockZuZeilen\(b\)\{[\s\S]*?\n\}/, 'edBlockZuZeilen'),
  hol(/function edBloeckeZuMarkup\(bloecke\)\{[\s\S]*?\n\}/, 'edBloeckeZuMarkup'),
  hol(/function edBlockHtml\(b\)\{[\s\S]*?\n\}/, 'edBlockHtml'),
  hol(/function edAbschnittNeu\(\)\{[\s\S]*?\n\}/, 'edAbschnittNeu'),
  hol(/function edAusHtml\(roh, slug, neu\)\{[\s\S]*?\n\}/, 'edAusHtml'),
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
        edBaustein, ED_RECHENWERK, ED_STIL_BAUSTEINE,
        ED_FORM, edBlockNeu, edMarkupZuBloecken, edBloeckeZuMarkup,
        edBlockZuZeilen, edBlockHtml, edAusHtml } =
  new Function(quellen + `
    return {edEscape, edInline, edBloecke, edNurText, edSlug, edSeiteBauen,
            ED_STIL, ED_PFLICHTTEIL, EDITOR_WERKZEUG, ED_BAUSTEINE,
            edBaustein, ED_RECHENWERK, ED_STIL_BAUSTEINE,
            ED_FORM, edBlockNeu, edMarkupZuBloecken, edBloeckeZuMarkup,
            edBlockZuZeilen, edBlockHtml, edAusHtml};`)();

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

/* ------------------------------------------------ Blockmodell des Editors
   Der Editor arbeitet blockweise, gespeichert wird weiter Markup. Beide
   Richtungen muessen stimmen, sonst ist "Bearbeiten" ein Datenverlust. */
pruefe('Text ohne Baustein wird ein Textblock', () => {
  const b = edMarkupZuBloecken('Satz eins.\n\nSatz zwei.');
  assert.equal(b.length, 1);
  assert.equal(b[0].art, 'text');
  assert.equal(b[0].text, 'Satz eins.\n\nSatz zwei.');
});
pruefe('Leeres Markup ergibt trotzdem einen Block', () => {
  // Sonst stuende der Editor ohne Eingabefeld da.
  const b = edMarkupZuBloecken('');
  assert.equal(b.length, 1);
  assert.equal(b[0].art, 'text');
  assert.equal(b[0].text, '');
});
pruefe('Text und Baustein werden getrennt', () => {
  const b = edMarkupZuBloecken('Davor.\n\n:::klapp Warum?\nWeil.\n:::\n\nDanach.');
  assert.deepEqual(b.map(x => x.art), ['text', 'klapp', 'text']);
  assert.equal(b[0].text, 'Davor.');
  assert.equal(b[1].titel, 'Warum?');
  assert.equal(b[1].text, 'Weil.');
  assert.equal(b[2].text, 'Danach.');
});
pruefe('Schritte werden Zeilen mit zwei Spalten', () => {
  const b = edMarkupZuBloecken(
    ':::schritte Anschliessen\nStrom | Kabel rein.\nNetz | Dose links.\n:::');
  assert.equal(b[0].art, 'schritte');
  assert.deepEqual(b[0].zeilen, [['Strom', 'Kabel rein.'], ['Netz', 'Dose links.']]);
});
pruefe('Kennzahlen haben drei Spalten, fehlende werden leer', () => {
  const b = edMarkupZuBloecken(':::kennzahlen Blick\nMTU | 1500\n:::');
  assert.deepEqual(b[0].zeilen, [['MTU', '1500', '']]);
});
pruefe('Rechner wird in Felder, Formel und Einheit zerlegt', () => {
  const b = edMarkupZuBloecken(':::rechner Kosten\nVerbrauch in kWh = 18\n' +
    'Preis je kWh = 0,32\n= Verbrauch * Preis\nEinheit: \u20ac\nEin Hinweis.\n:::');
  assert.equal(b[0].art, 'rechner');
  assert.deepEqual(b[0].felder, [{name: 'Verbrauch in kWh', wert: '18'},
                                 {name: 'Preis je kWh', wert: '0,32'}]);
  assert.equal(b[0].formel, 'Verbrauch * Preis');
  assert.equal(b[0].einheit, '\u20ac');
  assert.equal(b[0].hinweis, 'Ein Hinweis.');
});
pruefe('Unbekannte Art bleibt als Text erhalten', () => {
  // Nichts darf beim Bearbeiten verschluckt werden.
  const b = edMarkupZuBloecken(':::flugzeug Titel\nInhalt\n:::');
  assert.equal(b[0].art, 'text');
  assert.ok(b[0].text.includes('Inhalt'), b[0].text);
  assert.ok(b[0].text.includes(':::flugzeug Titel'), b[0].text);
});
pruefe('Rundlauf: Markup bleibt Markup', () => {
  const m = 'Davor.\n\n:::schritte Anschliessen\nStrom | Kabel rein.\n' +
            'Netz | Dose links.\n:::\n\n:::rechner Kosten\nkWh = 18\n' +
            '= kWh * 2\nEinheit: \u20ac\n:::\n\nDanach.';
  assert.equal(edBloeckeZuMarkup(edMarkupZuBloecken(m)), m);
});
pruefe('Leere Zeilen und Felder fallen beim Speichern weg', () => {
  const b = edBlockNeu('schritte');          // zwei leere Zeilen
  b.titel = 'Titel';
  b.zeilen[0] = ['Strom', 'Kabel rein.'];
  const m = edBloeckeZuMarkup([b]);
  assert.equal(m, ':::schritte Titel\nStrom | Kabel rein.\n:::');
});
pruefe('Ein leerer Block erzeugt kein leeres Markup', () => {
  assert.equal(edBloeckeZuMarkup([edBlockNeu('text')]), '');
});
pruefe('Ein leerer Block zwischen zwei vollen hinterlaesst keine Luecke', () => {
  /* Die Mutationsprobe hat gezeigt, dass der Test oben allein nichts
     beweist: ein einzelner leerer Block ergibt so oder so eine leere
     Zeichenkette. Erst in der Mitte faellt auf, ob er wirklich wegfaellt. */
  const a = edBlockNeu('text'); a.text = 'Davor.';
  const c = edBlockNeu('text'); c.text = 'Danach.';
  assert.equal(edBloeckeZuMarkup([a, edBlockNeu('text'), c]), 'Davor.\n\nDanach.');
});
pruefe('Jede Blockart im Kasten hat Name und Hilfe', () => {
  for (const [art, f] of Object.entries(ED_FORM)) {
    assert.ok(f.name && f.hilfe, art + ' unvollstaendig');
    // Die Zeilenarten brauchen Spaltennamen, sonst steht im Formular nichts.
    if (!['text', 'klapp', 'rechner'].includes(art))
      assert.ok((f.spalten || []).length >= 2, art + ' ohne Spalten');
  }
});
pruefe('Die Vorschau benutzt denselben Erzeuger wie die Seite', () => {
  const b = edBlockNeu('schritte');
  b.zeilen = [['Strom', 'Kabel rein.'], ['Netz', 'Dose links.']];
  const h = edBlockHtml(b);
  assert.equal(h, edBaustein('schritte', '', ['Strom | Kabel rein.', 'Netz | Dose links.']));
  assert.equal((h.match(/<li>/g) || []).length, 2);
  /* Ein Satz allein taugt als Beweis nicht: den bekommt auch ein
     selbstgebautes <p> hin (Mutationsprobe). Also Text, bei dem sich der
     echte Erzeuger zeigen MUSS - Titel, Auszeichnung, und ein <b>, das
     Text bleiben muss. */
  const t = edBlockNeu('text');
  t.text = '## Titel\n\nEin <b>Satz</b> mit **fett**.';
  const ht = edBlockHtml(t);
  assert.equal(ht, edBloecke(t.text));
  assert.ok(ht.includes('<h3'), 'kein Titel: ' + ht);
  assert.ok(ht.includes('<b>fett</b>'), 'nicht ausgezeichnet: ' + ht);
  assert.ok(ht.includes('&lt;b&gt;Satz&lt;/b&gt;'), 'HTML nicht geschuetzt: ' + ht);
});
pruefe('Das Rechenwerk der Seite ist dasselbe wie hier', () => {
  /* ED_RECHENWERK entsteht aus toString() der echten Funktionen. Waere es
     eine zweite, abgeschriebene Fassung, koennte die Vorschau anders
     rechnen als die Seite. */
  assert.ok(ED_RECHENWERK.includes('function bkRechnen'), 'bkRechnen fehlt');
  assert.ok(ED_RECHENWERK.includes('function bkZahl'), 'bkZahl fehlt');
  assert.ok(ED_RECHENWERK.includes('function bkRechnerStarten'), 'Starter fehlt');
  const zweit = new Function(ED_RECHENWERK + '\nreturn bkRechnen;')();
  assert.equal(zweit('18 * 0,32', {}), bkRechnen('18 * 0,32', {}));
  assert.equal(zweit('18 * 0,32', {}), 5.76);
});
pruefe('Die Huelle wertet nichts mit eval oder new Function aus', () => {
  /* Der Browser hat genau das abgelehnt: die CSP der Huelle hat kein
     "unsafe-eval", und das soll so bleiben. Eine Vorschau ist kein Grund,
     sie aufzuweichen. Geprueft wird die Datei, nicht der Gedanke. */
  const ohneKommentare = quelle
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/^\s*\/\/.*$/gm, ' ');
  const treffer = ohneKommentare.match(/new Function\s*\(|[^.\w]eval\s*\(/g) || [];
  assert.deepEqual(treffer, [], 'in der Huelle steht: ' + treffer.join(', '));
});

/* ------------------------------------------------ PDF-Baustein */
pruefe('PDF: Datei und Sprungziele gehen durch das Markup', () => {
  const m = ':::pdf Kompendium\ndatei: anhang-kompendium\n' +
            'Kapitel 1 | 10\nAnhang A | 88\n:::';
  const b = edMarkupZuBloecken(m);
  assert.equal(b[0].art, 'pdf');
  assert.equal(b[0].kennung, 'anhang-kompendium');
  assert.deepEqual(b[0].zeilen, [['Kapitel 1', '10'], ['Anhang A', '88']]);
  assert.equal(edBloeckeZuMarkup(b), m);
});
pruefe('PDF: die Knoepfe nennen Kennung und Seite', () => {
  const h = edBaustein('pdf', 'Kompendium',
                       ['datei: anhang-kompendium', 'Kapitel 1 | 10']);
  // Der Dateiname steht NICHT im HTML - er kommt zur Laufzeit aus der Marke.
  assert.ok(!h.includes('.pdf'), 'der Dateiname darf nicht hier stehen: ' + h);
  assert.ok(h.includes('data-wiki-pdf="anhang-kompendium"'));
  assert.ok(h.includes('data-wiki-seite="10"'));
  assert.ok(h.includes('Ganzes PDF'), 'der Knopf fuer das ganze PDF fehlt');
  assert.equal((h.match(/data-wiki-pdf=/g) || []).length, 2);  // ganz + ein Ziel
});
pruefe('PDF: ohne Datei gibt es einen Hinweis, keine Stille', () => {
  const h = edBaustein('pdf', 'Titel', ['Kapitel 1 | 10']);
  assert.ok(h.includes('ohne Datei'), h);
});
pruefe('PDF: Text in Beschriftung und Kennung bleibt Text', () => {
  const h = edBaustein('pdf', 'T', ['datei: a"><script>x</script>',
                                    '<img onerror=x> | 1']);
  assert.ok(!h.includes('<script>'), h);
  assert.ok(!h.includes('<img'), h);
});
pruefe('PDF: die neue Datei geht als markierter Anhang in die Seite', () => {
  const b = edBlockNeu('pdf');
  b.kennung = 'anhang-kompendium'; b.daten64 = 'QUJD'; b.titel = 'K';
  b.zeilen = [['Kapitel 1', '10']];
  const seite = edSeiteBauen({titel:'T', slug:'t', pfad:'A', abschnitte:[
    {anker:'x', titel:'X', markup:edBloeckeZuMarkup([b]), bloecke:[b]}]});
  assert.ok(seite.includes('id="anhang-kompendium" data-wiki-anhang=""'),
            'die Marke fehlt - der Server gliedert dann nichts aus');
  assert.ok(seite.includes('>QUJD<'), 'die Daten fehlen');
});
pruefe('PDF: ein vorhandener Anhang wird weiter genannt (N-18)', () => {
  /* Beim zweiten Speichern liegt die Datei schon auf dem Server. Die Seite
     muss sie trotzdem NENNEN, sonst verliert der Anhang seine Zeile. */
  const b = edBlockNeu('pdf');
  b.kennung = 'anhang-kompendium'; b.dateiname = 'anhang-kompendium.pdf';
  b.zeilen = [['Kapitel 1', '10']];
  const seite = edSeiteBauen({titel:'T', slug:'t', pfad:'A', abschnitte:[
    {anker:'x', titel:'X', markup:edBloeckeZuMarkup([b]), bloecke:[b]}]});
  assert.ok(seite.includes('data-wiki-anhang="anhang-kompendium.pdf"'), seite.slice(-600));
  assert.ok(!seite.includes('QUJD'));
});
pruefe('PDF: die Seite bittet die Huelle, sie zeigt nichts selbst', () => {
  const b = edBlockNeu('pdf');
  b.kennung = 'anhang-kompendium'; b.dateiname = 'anhang-kompendium.pdf';
  const seite = edSeiteBauen({titel:'T', slug:'t', pfad:'A', abschnitte:[
    {anker:'x', titel:'X', markup:edBloeckeZuMarkup([b]), bloecke:[b]}]});
  assert.ok(seite.includes("typ:'wiki-pdf'"), 'die Nachricht an die Huelle fehlt');
  /* Nicht nur, DASS beide Zeilen vorkommen, sondern dass sie zusammenhaengen:
     der Name muss von dem Element kommen, das der Knopf nennt. Die
     Mutationsprobe hat gezeigt, dass zwei getrennte includes() genau das
     nicht sehen. */
  assert.match(seite, /getElementById\(b\.dataset\.wikiPdf\)[\s\S]{0,240}getAttribute\('data-wiki-anhang'\)/,
               'der Name wird nicht aus der Marke DIESES Anhangs gelesen');
  // Kein iframe, kein embed, kein object: die CSP der Seite verbietet das,
  // und die Seite soll es auch nicht versuchen.
  assert.ok(!/<iframe|<embed|<object/i.test(seite), 'die Seite versucht es selbst');
});

/* ------------------------------------------------ Eine Datei in den Editor */
pruefe('Eine erzeugte Seite laesst sich wieder in den Editor lesen', () => {
  const b1 = edBlockNeu('text'); b1.text = 'Ein Satz mit **fett**.';
  const b2 = edBlockNeu('schritte'); b2.titel = 'So gehts';
  b2.zeilen = [['Strom', 'Kabel rein.'], ['Netz', 'Dose links.']];
  const seite = edSeiteBauen({
    titel:'Drucker', slug:'drucker', pfad:'Technik / Geräte',
    kurz:'Kurz gesagt.', gruppen:'wiki-technik',
    abschnitte:[{anker:'los', titel:'Loslegen', stichworte:'Drucker, Papier',
                 markup:edBloeckeZuMarkup([b1, b2]), bloecke:[b1, b2]}]});
  const e = edAusHtml(seite, '', false);
  assert.ok(e, 'kein Zustand gelesen');
  assert.equal(e.titel, 'Drucker');
  assert.equal(e.slug, 'drucker');
  assert.equal(e.pfad, 'Technik / Geräte');
  assert.equal(e.kurz, 'Kurz gesagt.');
  assert.equal(e.gruppen, 'wiki-technik');
  assert.equal(e.quelle, 'editor');
  assert.equal(e.abschnitte.length, 1);
  assert.equal(e.abschnitte[0].titel, 'Loslegen');
  assert.equal(e.abschnitte[0].stichworte, 'Drucker, Papier');
  assert.deepEqual(e.abschnitte[0].bloecke.map(x => x.art), ['text', 'schritte']);
  assert.deepEqual(e.abschnitte[0].bloecke[1].zeilen,
                   [['Strom', 'Kabel rein.'], ['Netz', 'Dose links.']]);
});
pruefe('Ohne Meta-Block gibt es kein Ergebnis, keine halbe Seite', () => {
  assert.equal(edAusHtml('<html><body>Nur Text</body></html>', '', true), null);
  assert.equal(edAusHtml('', '', true), null);
});
pruefe('Kaputter Meta-Block wird nicht geraten', () => {
  const h = '<script type="application/json" id="wiki-meta">{kaputt</' + 'script>';
  assert.equal(edAusHtml(h, '', true), null);
});
pruefe('Eine Seite von Hand: Suchtext wird Anfangstext, Quelle ist fremd', () => {
  const meta = {slug:'handarbeit', titel:'Handarbeit', pfad:['Technik'],
                gruppen:[], stand:'2026-09-17',
                abschnitte:[{anker:'a', titel:'A', text:'Der sichtbare Text.'}]};
  const h = '<script type="application/json" id="wiki-meta">' +
            JSON.stringify(meta) + '</' + 'script>';
  const e = edAusHtml(h, '', false);
  assert.equal(e.quelle, 'fremd', 'sonst fehlt die Warnung vor dem Ersetzen');
  assert.equal(e.abschnitte[0].bloecke[0].art, 'text');
  assert.equal(e.abschnitte[0].bloecke[0].text, 'Der sichtbare Text.');
});
pruefe('Der Name eines vorhandenen Anhangs kommt aus der Marke', () => {
  const b = edBlockNeu('pdf');
  b.kennung = 'anhang-handbuch'; b.dateiname = 'anhang-handbuch.pdf';
  b.zeilen = [['Kapitel 1', '7']];
  const seite = edSeiteBauen({titel:'T', slug:'t', pfad:'A', abschnitte:[
    {anker:'x', titel:'X', markup:edBloeckeZuMarkup([b]), bloecke:[b]}]});
  const e = edAusHtml(seite, '', false);
  const pdf = e.abschnitte[0].bloecke.find(x => x.art === 'pdf');
  assert.equal(pdf.kennung, 'anhang-handbuch');
  assert.equal(pdf.dateiname, 'anhang-handbuch.pdf',
               'ohne das wuerde die Seite den Anhang beim Speichern vergessen (N-18)');
  assert.deepEqual(pdf.zeilen, [['Kapitel 1', '7']]);
});
pruefe('Ein Anhang, den kein Block kennt, wird trotzdem weiter genannt', () => {
  /* Eine von Hand gebaute Seite mit einem Bild: der Editor kennt dafuer
     keinen Block, darf den Anhang aber nicht verlieren (N-18). */
  const meta = {slug:'mitbild', titel:'Mit Bild', pfad:['Technik'], gruppen:[],
                stand:'2026-09-17',
                abschnitte:[{anker:'a', titel:'A', text:'Text', markup:'Text'}]};
  const h = '<script type="application/json" id="wiki-meta">' + JSON.stringify(meta) +
            '</' + 'script><script id="bild-eins" data-wiki-anhang="bild-eins.png"></' +
            'script>';
  const e = edAusHtml(h, '', false);
  assert.deepEqual(e.fremdeAnhaenge, [{kennung:'bild-eins', name:'bild-eins.png'}]);
  const wieder = edSeiteBauen(e);
  assert.ok(wieder.includes('data-wiki-anhang="bild-eins.png"'),
            'der Anhang wird nicht mehr genannt');
});

console.log('');
console.log(`${gut} ok, ${schlecht} Fehler`);
process.exit(schlecht ? 1 : 0);
