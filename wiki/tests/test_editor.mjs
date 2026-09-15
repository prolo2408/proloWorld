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
  hol(/const ED_HALT = [^\n]+/, 'ED_HALT'),
  hol(/function edEscape\(s\)\{[\s\S]*?\n\}/, 'edEscape'),
  hol(/function edInline\(s\)\{[\s\S]*?\n\}/, 'edInline'),
  hol(/function edBloecke\(text\)\{[\s\S]*?\n\}/, 'edBloecke'),
  hol(/function edNurText\(text\)\{[\s\S]*?\n\}/, 'edNurText'),
  hol(/function edSlug\(s\)\{[\s\S]*?\n\}/, 'edSlug'),
  hol(/const ED_STIL = \[[\s\S]*?\]\.join\('\\n'\);/, 'ED_STIL'),
  hol(/const ED_PFLICHTTEIL = \[[\s\S]*?\]\.join\('\\n'\);/, 'ED_PFLICHTTEIL'),
  hol(/function edListe\(s\)\{[\s\S]*?\n\}/, 'edListe'),
  hol(/function edPfadListe\(s\)\{[\s\S]*?\n\}/, 'edPfadListe'),
  hol(/function edSeiteBauen\(e\)\{[\s\S]*?\n\}/, 'edSeiteBauen'),
].join('\n');

const { edEscape, edInline, edBloecke, edNurText, edSlug, edSeiteBauen,
        ED_STIL, ED_PFLICHTTEIL, EDITOR_WERKZEUG } =
  new Function(quellen + `
    return {edEscape, edInline, edBloecke, edNurText, edSlug, edSeiteBauen,
            ED_STIL, ED_PFLICHTTEIL, EDITOR_WERKZEUG};`)();

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

console.log('');
console.log(`${gut} ok, ${schlecht} Fehler`);
process.exit(schlecht ? 1 : 0);
