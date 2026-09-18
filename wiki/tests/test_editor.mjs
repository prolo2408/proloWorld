/* Der Seiten-Editor: Auszeichnung, Suchtext und die erzeugte Seite.
 *
 * Die Funktionen werden aus index.html herausgeschnitten und hier gegen VON
 * HAND geschriebene Erwartungen geprueft (Regelblatt 13). Kein Wert unten ist
 * aus der Ausgabe des Codes uebernommen.
 *
 * Aufruf:  node tests/test_editor.mjs
 */
import { readFileSync, readdirSync } from 'node:fs';
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
  /* edPruefbar liest im Normalfall die Felder der Seite. Hier laeuft es nur
     mit nurNachsehen=true - dann braucht es kein Dokument, nur ZUSTAND. */
  /* edPruefbar ist seit N-35 nur die Textsicht auf edBefunde - beide
     muessen herausgeholt werden, sonst ruft edPruefbar ins Leere. */
  hol(/function edBefunde\(nurNachsehen\)\{[\s\S]*?\n\}/, 'edBefunde'),
  hol(/function edPruefbar\(nurNachsehen\)\{[\s\S]*?\n\}/, 'edPruefbar'),
  hol(/function edGruppenWiederholt\(abschnitte\)\{[\s\S]*?\n\}/, 'edGruppenWiederholt'),
  hol(/function kiPrompt\(thema\)\{[\s\S]*?\n\}/, 'kiPrompt'),
  hol(/function edLeer\(\)\{[\s\S]*?\n\}/, 'edLeer'),
  hol(/function edVorlageBauen\(abschnitte\)\{[\s\S]*?\n\}/, 'edVorlageBauen'),
  hol(/const ED_VORLAGEN = \{[\s\S]*?\n\};/, 'ED_VORLAGEN'),
  hol(/const ED_GRUPPEN = \[[\s\S]*?\n\];/, 'ED_GRUPPEN'),
  'var ZUSTAND = {editor:null};',
].join('\n');

const { edEscape, edInline, edBloecke, edNurText, edSlug, edSeiteBauen,
        ED_STIL, ED_PFLICHTTEIL, EDITOR_WERKZEUG, ED_BAUSTEINE,
        edBaustein, ED_RECHENWERK, ED_STIL_BAUSTEINE,
        ED_FORM, edBlockNeu, edMarkupZuBloecken, edBloeckeZuMarkup,
        edBlockZuZeilen, edBlockHtml, edAusHtml, edPruefbar, edBefunde,
        edGruppenWiederholt,
        kiPrompt, ED_VORLAGEN, ED_GRUPPEN, edLeer, ZUSTAND } =
  new Function(quellen + `
    return {edEscape, edInline, edBloecke, edNurText, edSlug, edSeiteBauen,
            ED_STIL, ED_PFLICHTTEIL, EDITOR_WERKZEUG, ED_BAUSTEINE,
            edBaustein, ED_RECHENWERK, ED_STIL_BAUSTEINE,
            ED_FORM, edBlockNeu, edMarkupZuBloecken, edBloeckeZuMarkup,
            edBlockZuZeilen, edBlockHtml, edAusHtml, edPruefbar, edBefunde,
        edGruppenWiederholt,
            kiPrompt, ED_VORLAGEN, ED_GRUPPEN, edLeer, ZUSTAND};`)();

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
pruefe('Die Huelle ist ein Rahmen, kein Schriftstueck (N-34)', () => {
  /* Der Befund aus der Rueckmeldung: unter der Oberflaeche stand ein
     schwarzer Balken und der Kopf war weg. Gemessen im Browser: 520 Pixel
     Fremdhoehe im Koerper genuegen, dann laesst sich das ganze Dokument
     schieben - Huellenunterkante bei 48 % der Fensterhoehe, Kopf nicht mehr
     sichtbar. Gescrollt wird INNEN; die Wurzel scrollt nie. */
  const wurzel = quelle.match(/^html,body\{[^}]*\}/m);
  assert.ok(wurzel, 'keine Regel fuer html,body gefunden');
  assert.ok(/overflow:\s*hidden/.test(wurzel[0]),
    'ohne overflow:hidden an der Wurzel schiebt jede Fremdhoehe die Huelle aus dem Bild');
  assert.ok(/height:\s*100%/.test(wurzel[0]),
    'ohne height:100% ist die Huelle nicht so hoch wie das Fenster');
  const koerper = quelle.match(/\nbody\{\n([\s\S]*?)\n\}/);
  assert.ok(koerper, 'keine body-Regel gefunden');
  assert.ok(/background:\s*var\(--app\)/.test(koerper[1]),
    'der Koerper muss die Farbe der Huelle tragen - sonst ist jede Luecke ein Fremdkoerper');
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
  const gruppen = new Set(ED_GRUPPEN.map(g => g[0]));
  for (const [art, f] of Object.entries(ED_FORM)) {
    assert.ok(f.name && f.hilfe, art + ' unvollstaendig');
    /* Ohne Zeichen und Gruppe faellt der Baustein aus der Auswahl heraus -
       er waere im Editor nicht mehr zu finden, ohne dass etwas kaputt
       aussieht. */
    assert.ok(f.zeichen, art + ' ohne Zeichen');
    assert.ok(gruppen.has(f.gruppe),
              art + ': Gruppe "' + f.gruppe + '" gibt es nicht');
    /* Die ZEILENARTEN brauchen Spaltennamen, sonst steht im Formular nichts.
       Die anderen haben ein eigenes Formular: Text und Klapptext ein
       Textfeld, der Rechner seine Felder, Bild eine Dateiwahl. */
    if (!['text', 'klapp', 'rechner', 'bild'].includes(art))
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

/* ------------------------------------------------ N-22: PDF ohne Datei */
function nurPdfSeite(zusatz){
  /* Eine Seite mit genau einem PDF-Baustein. zusatz setzt daten64 oder
     dateiname - damit sich beide Richtungen pruefen lassen. */
  const markup = ':::pdf Das Handbuch\ndatei: handbuch\nInstallation | 4\n:::';
  const bloecke = edMarkupZuBloecken(markup);
  Object.assign(bloecke[0], zusatz || {});
  return {neu:true, slug:'probe', titel:'Probe', kurz:'', pfad:'Technik',
          gruppen:'', abschnitte:[{anker:'a', titel:'A', stichworte:'',
          gruppe:'', markup:markup, bloecke:bloecke}]};
}
pruefe('Ein PDF-Baustein ohne Datei wird nicht gespeichert', () => {
  ZUSTAND.editor = nurPdfSeite(null);
  const m = edPruefbar(true);
  /* Genau ein Mangel, und der nennt den Baustein - nicht "Abschnitt leer". */
  assert.equal(m.length, 1, 'erwartet genau einen Mangel, bekommen: ' + m.join(' / '));
  assert.ok(/PDF-Baustein 1 in „A"/.test(m[0]), 'Mangel benennt den Baustein nicht: ' + m[0]);
  assert.ok(/keine Datei/.test(m[0]), 'Mangel sagt nicht, dass die Datei fehlt: ' + m[0]);
});
pruefe('Ein PDF-Baustein mit Datei auf dem Server ist in Ordnung', () => {
  ZUSTAND.editor = nurPdfSeite({dateiname:'handbuch.pdf'});
  assert.deepEqual(edPruefbar(true), [], 'ein beiliegendes PDF wird beanstandet');
  ZUSTAND.editor = nurPdfSeite({daten64:'JVBERi0x'});
  assert.deepEqual(edPruefbar(true), [], 'ein neu gewaehltes PDF wird beanstandet');
});
pruefe('Die fertige Seite sagt, wenn zu einem PDF-Knopf nichts beiliegt', () => {
  /* Gebaut wird eine Seite, deren PDF-Knopf auf eine Kennung zeigt, zu der
     kein Anhangsblock im HTML steht. Vorher tat dieser Knopf gar nichts. */
  const html = edSeiteBauen(nurPdfSeite(null));
  assert.ok(html.includes('data-wiki-pdf="handbuch"'), 'kein PDF-Knopf gebaut');
  assert.ok(!/id="handbuch"/.test(html), 'unerwartet doch ein Anhangsblock dabei');
  assert.ok(html.includes('bk-pdf-fehlt'),
            'die Seite hat keinen Hinweis fuer den Fall ohne Anhang');
  assert.ok(!html.includes('if(!name || window.parent === window) return;'),
            'der Pflichtteil bricht noch still ab');
  /* Der Hinweis muss beim Leser lesbar ankommen: die Anfuehrung steht im
     Pflichtteil als \u-Escape, nicht roh. */
  const zeile = html.split('\n').find(z => z.includes('liegt kein PDF bei'));
  assert.ok(zeile, 'der Hinweistext steht nicht in der Seite');
  assert.ok(zeile.includes('\\u201e'),
            'die Anfuehrung ist nicht als Escape gesetzt: ' + zeile);
});

/* ------------------------------------------------ N-24: geteilte Gruppen */
function gr(namen){ return namen.map(g => ({gruppe: g})); }
pruefe('Eine Gruppe, die getrennt wieder anfaengt, wird gemeldet', () => {
  /* Reihenfolge Grundlagen, Anleitung, Grundlagen: das Verzeichnis fasst nur
     aufeinanderfolgende Abschnitte, also stuende "Grundlagen" zweimal da.
     Gemeldet wird Abschnitt 3 - Nummer 2, von null gezaehlt. */
  const w = edGruppenWiederholt(gr(['Grundlagen', 'Anleitung', 'Grundlagen']));
  assert.deepEqual([...w], [2]);
});
pruefe('Der erste Abschnitt einer Gruppe wird nie gemeldet', () => {
  /* Sonst stuende an Abschnitt 1 "kommt weiter oben schon vor" - und
     darueber steht nichts. */
  const w = edGruppenWiederholt(gr(['Grundlagen', 'Anleitung', 'Grundlagen']));
  assert.ok(!w.has(0), 'der erste Abschnitt wurde angemahnt');
});
pruefe('Zwei Abschnitte nebeneinander sind in Ordnung', () => {
  const w = edGruppenWiederholt(gr(['Grundlagen', 'Grundlagen', 'Anleitung']));
  assert.deepEqual([...w], [], 'nebeneinander ist genau der richtige Aufbau');
});
pruefe('Ohne Gruppen gibt es nichts zu melden', () => {
  assert.deepEqual([...edGruppenWiederholt(gr(['', '', '']))], []);
  assert.deepEqual([...edGruppenWiederholt([])], []);
  /* Eine Luecke zwischen zwei gleichen Gruppen zaehlt: dazwischen steht dann
     ein Abschnitt ohne Ueberschrift, und die Ueberschrift kommt wieder. */
  assert.deepEqual([...edGruppenWiederholt(gr(['A', '', 'A']))], [2]);
});
pruefe('Mehrere Wiederholungen werden alle gemeldet', () => {
  const w = edGruppenWiederholt(gr(['A', 'B', 'A', 'B', 'A']));
  assert.deepEqual([...w], [2, 3, 4]);
});

/* ------------------------------------------------ Der Prompt fuer eine KI */
pruefe('Das Geruest aus dem Prompt laesst sich wirklich in den Editor laden', () => {
  /* Der wichtigste Test am Prompt: Was er einer KI vorgibt, muss der Editor
     hinterher lesen koennen. Also wird das Geruest aus dem Prompt
     herausgeschnitten und genau durch die Funktion geschickt, die auch
     "In den Editor laden" benutzt. */
  const p = kiPrompt('Drucker einrichten');
  const von = p.indexOf('<!DOCTYPE html>');
  const bis = p.indexOf('</html>');
  assert.ok(von >= 0 && bis > von, 'im Prompt steht kein vollstaendiges Geruest');
  const geruest = p.slice(von, bis + 7);
  const e = edAusHtml(geruest, '', true);
  assert.ok(e, 'edAusHtml kommt mit dem Geruest aus dem Prompt nicht zurecht');
  assert.equal(e.titel, 'Drucker einrichten');
  assert.equal(e.slug, 'drucker-einrichten');
  assert.equal(e.pfad, 'Technik / Geraete');
  assert.equal(e.quelle, 'editor',
               'das Geruest nennt ein anderes Werkzeug - dann warnt der Editor');
  assert.equal(e.abschnitte.length, 1);
  assert.equal(e.abschnitte[0].anker, 'vorbereitung');
  assert.equal(e.abschnitte[0].gruppe, 'Grundlagen');
  assert.equal(e.abschnitte[0].stichworte, 'drucker, netzwerk, treiber');
  /* Das Markup im Geruest ist ein Absatz und zwei Listenpunkte. Der Editor
     macht daraus EINEN Textblock - Absaetze zerfallen nicht. */
  assert.equal(e.abschnitte[0].bloecke.length, 1);
  assert.equal(e.abschnitte[0].bloecke[0].art, 'text');
  assert.equal(e.abschnitte[0].bloecke[0].text,
               'Erster Absatz.\n\n- Punkt eins\n- Punkt zwei');
});
pruefe('Der Prompt nennt genau das Werkzeug, auf das der Editor hoert', () => {
  /* Steht dort ein anderer Wert, halten der Editor und der Server jede
     Antwort der KI fuer eine fremde Seite und werfen ihr Markup weg. */
  const p = kiPrompt('');
  assert.ok(p.includes('"werkzeug": "' + EDITOR_WERKZEUG + '"'),
            'der Prompt nennt nicht ' + EDITOR_WERKZEUG);
});
pruefe('Jeder Baustein des Editors steht im Prompt', () => {
  /* Sonst kennt die KI ihn nicht und schreibt Text, wo ein Baustein
     gehoert hat. "text" ist kein :::-Baustein, sondern der Normalfall. */
  const p = kiPrompt('');
  const fehlen = Object.keys(ED_FORM)
    .filter(k => k !== 'text' && !p.includes(':::' + k));
  assert.deepEqual(fehlen, [], 'nicht im Prompt erklaert: ' + fehlen.join(', '));
});
pruefe('Ohne Thema bleibt eine Stelle zum Ausfuellen', () => {
  const p = kiPrompt('   ');
  assert.ok(p.includes('THEMA: <HIER DEIN THEMA EINTRAGEN>'),
            'ohne Thema steht keine Stelle zum Ausfuellen im Prompt');
});
pruefe('Das Thema kommt unveraendert in den Prompt', () => {
  const p = kiPrompt('  Drucker im 2. Stock  ');
  assert.ok(p.includes('THEMA: Drucker im 2. Stock'), 'Thema fehlt oder ist entstellt');
});

/* --------------------------------- N-26 und der Stand des Pflichtteils */
pruefe('Das Fundmuster wird vor jedem Test zurueckgesetzt', () => {
  /* Ein Muster mit /g merkt sich, wo es zuletzt getroffen hat; test() sucht
     dann erst dahinter. Zwei benachbarte Textknoten mit demselben Wort
     verlieren so den zweiten Treffer (N-26). Im Browser gemessen: zwei
     Vorkommen, eine Marke. */
  assert.ok(ED_PFLICHTTEIL.includes('re.lastIndex = 0'),
            'der Pflichtteil setzt lastIndex nicht zurueck');
  assert.ok(!/while\(\(n = lauf\.nextNode\(\)\)\) if\(re\.test/.test(ED_PFLICHTTEIL),
            'die alte, zustandsbehaftete Zeile steht noch drin');
});
pruefe('Die Marken kommen ohne zusaetzliche Huelle in den Text', () => {
  /* Ein <span> um jede Fundstelle bliebe nach dem Aufraeumen stehen und
     zerschnitte den Text dauerhaft - der naechste Lauf faende ein Wort
     ueber die Schnittstelle hinweg nicht mehr. */
  assert.ok(ED_PFLICHTTEIL.includes('createDocumentFragment'),
            'die Fundstellen werden noch in ein Element gehuellt');
  assert.ok(ED_PFLICHTTEIL.includes('eltern.normalize()'),
            'nach dem Aufraeumen werden die Textknoten nicht zusammengelegt');
});
pruefe('Jede mitgelieferte Seite traegt den Pflichtteil der Huelle', () => {
  /* Eine Seite behaelt den Code, mit dem sie gebaut wurde - eine Korrektur
     am Pflichtteil erreicht sie nicht von selbst. Dieser Test ist die
     Bremse dagegen; nachziehen: node pflichtteil-nachziehen.mjs
     --schreiben */
  const namen = [join(HIER, '..', 'test-seite.html')].concat(
    readdirSync(join(HIER, '..', 'vorlagen')).sort()
      .filter(n => n.endsWith('.html'))
      .map(n => join(HIER, '..', 'vorlagen', n)));
  assert.ok(namen.length >= 3, 'keine Seiten gefunden - der Test waere leer gruen');
  const alt = [];
  for(const pfad of namen){
    const html = readFileSync(pfad, 'utf8');
    if(!html.includes(ED_PFLICHTTEIL)) alt.push(pfad.split('/').slice(-2).join('/'));
  }
  assert.deepEqual(alt, [], 'Pflichtteil nicht auf dem Stand: ' + alt.join(', '));
});

/* ------------------------------ Suche in der Seite: beide Haelften */
pruefe('Huelle und Seite reden ueber dieselben Nachrichten', () => {
  /* Die zwei Haelften stehen an verschiedenen Stellen derselben Datei: die
     Huelle als gewoehnliches Skript, die Seite als Zeichenkette im
     Pflichtteil. Ein Tippfehler in einem der Namen faellt sonst erst im
     Browser auf - und auch dort nur, wenn man genau hinsieht. */
  /* Ohne den Pflichtteil - sonst bestaetigt sich der Test mit derselben
     Zeichenkette selbst. Und geprueft wird die AUSWERTUNG, nicht das
     Vorkommen des Namens: in den Kommentaren steht er auch, und ein
     geloeschter Empfaenger waere sonst unentdeckt geblieben. */
  const huelle = quelle.replace(ED_PFLICHTTEIL, ' ');
  assert.ok(/postMessage\(\{typ:'wiki-finden'/.test(huelle),
            'die Huelle schickt kein wiki-finden');
  assert.ok(/e\.data\.typ === 'wiki-funde'\) findenStandZeigen\(/.test(huelle),
            'die Huelle wertet wiki-funde nicht aus');
  assert.ok(ED_PFLICHTTEIL.includes("e.data.typ === 'wiki-finden'"),
            'die Seite wertet wiki-finden nicht aus');
  assert.ok(ED_PFLICHTTEIL.includes("typ:'wiki-funde'"),
            'die Seite schickt kein wiki-funde zurueck');
});
pruefe('Die Seite schickt jedes Feld, das die Huelle liest', () => {
  /* findenStandZeigen liest anzahl, nr, abschnitt und anker. Fehlt eines
     im Pflichtteil, steht in der Leiste "undefined von 4". */
  for(const feld of ['anzahl:', 'nr:', 'anker:', 'abschnitt:', 'begriff:']){
    assert.ok(ED_PFLICHTTEIL.includes(feld),
              'die Rueckmeldung der Seite hat kein Feld ' + feld);
  }
});
pruefe('Eine Fundstelle in einem zugeklappten Klapptext wird aufgeklappt', () => {
  /* Ohne das hat die Marke kein Layout, scrollIntoView tut nichts, und der
     Sprung landet irgendwo. Im Browser gemessen: Klapptext vorher zu,
     nachher offen, Marke mit Hoehe > 0. */
  /* Geprueft wird die Zuweisung, nicht bloss das Vorkommen der
     Zeichenkette: die Schleife darueber nennt denselben Selektor noch
     einmal, und ein "var d = null" waere sonst unentdeckt geblieben. */
  assert.ok(/var d = m\.closest \? m\.closest\('details:not\(\[open\]\)'\)/
            .test(ED_PFLICHTTEIL),
            'die Seite sucht keinen zugeklappten Klapptext um die Fundstelle');
  assert.ok(ED_PFLICHTTEIL.includes('d.open = true;'),
            'die Seite klappt den Klapptext nicht auf');
});

/* ------------------------------------------------ Die Vorlagen */
pruefe('Jede Vorlage baut einen Zustand, den der Editor kennt', () => {
  for(const [name, v] of Object.entries(ED_VORLAGEN)){
    const e = v.bauen();
    assert.ok(e && Array.isArray(e.abschnitte) && e.abschnitte.length,
              name + ': keine Abschnitte');
    assert.equal(e.neu, true, name + ': die Vorlage gilt nicht als neue Seite');
    for(const a of e.abschnitte){
      assert.ok(Array.isArray(a.bloecke) && a.bloecke.length,
                name + ': ein Abschnitt ohne Bloecke');
      /* Die leere Vorlage ist genau das: ein leerer Abschnitt, den der
         Mensch benennt. Alle anderen bringen ihr Geruest mit. */
      if(name === 'leer') continue;
      assert.ok(String(a.titel || '').trim(), name + ': ein Abschnitt ohne Titel');
      assert.ok(String(a.anker || '').trim(), name + ': ein Abschnitt ohne Anker');
      assert.ok(/^[a-z0-9]+(-[a-z0-9]+)*$/.test(a.anker),
                name + ': Anker "' + a.anker + '" ist nicht erlaubt');
      assert.ok(String(a.markup || '').trim(),
                name + ': ein Abschnitt ohne Inhalt');
    }
  }
});
pruefe('Jede Vorlage bringt genau die Bausteine mit, die sie meint', () => {
  /* Von Hand aufgeschrieben, aus dem Markup der Vorlagen gelesen. Nicht
     "irgendein bekannter Baustein": ein Tippfehler wie ":::schritt" statt
     ":::schritte" wird vom Editor stillschweigend zu einem TEXTBLOCK - die
     Zeilen bleiben stehen, der Baustein ist weg, und niemand merkt es,
     bevor die Seite beim Leser liegt. */
  const ERWARTET = {
    leer:         ['text'],
    anleitung:    ['text', 'schritte', 'text', 'klapp'],
    vergleich:    ['text', 'gegenueber', 'kennzahlen', 'text'],
    nachschlagen: ['text', 'begriffe', 'text'],
    rechnen:      ['text', 'rechner', 'text']
  };
  assert.deepEqual(Object.keys(ED_VORLAGEN).sort(), Object.keys(ERWARTET).sort(),
                   'es gibt eine Vorlage, die hier nicht aufgeschrieben ist');
  for(const [name, v] of Object.entries(ED_VORLAGEN)){
    const arten = v.bauen().abschnitte.flatMap(a => a.bloecke.map(b => b.art));
    assert.deepEqual(arten, ERWARTET[name], name);
    for(const art of arten) assert.ok(ED_FORM[art], name + ': "' + art + '" gibt es nicht');
  }
});
pruefe('Das Markup einer Vorlage uebersteht den Rundlauf', () => {
  /* Bloecke -> Markup -> Bloecke muss dasselbe ergeben. Sonst veraendert
     sich die Seite beim ersten Speichern, ohne dass jemand etwas getan
     hat. */
  for(const [name, v] of Object.entries(ED_VORLAGEN)){
    for(const a of v.bauen().abschnitte){
      const zurueck = edMarkupZuBloecken(edBloeckeZuMarkup(a.bloecke));
      assert.equal(zurueck.length, a.bloecke.length,
                   name + ' / ' + a.titel + ': andere Anzahl Bloecke');
      zurueck.forEach((b, i) => assert.equal(b.art, a.bloecke[i].art,
        name + ' / ' + a.titel + ': Baustein ' + (i + 1) + ' wurde zu ' + b.art));
    }
  }
});
pruefe('Eine Vorlage bringt Titel und Pfad NICHT mit', () => {
  /* Der Titel ist die Aussage des Menschen. Stuende dort ein Vorschlag,
     hiesse die erste Seite "Neue Seite" - und keiner merkt es. */
  for(const [name, v] of Object.entries(ED_VORLAGEN)){
    const e = v.bauen();
    assert.equal(String(e.titel || ''), '', name + ': die Vorlage setzt einen Titel');
    assert.equal(String(e.pfad || ''), '', name + ': die Vorlage setzt einen Pfad');
  }
});
pruefe('Die leere Vorlage ist wirklich leer', () => {
  const e = ED_VORLAGEN.leer.bauen();
  assert.equal(e.abschnitte.length, 1);
  assert.equal(String(e.abschnitte[0].markup || '').trim(), '');
});

/* ------------------------------------------------ Die drei neuen Bausteine */
pruefe('Ein Bild holt seine Adresse aus der Marke, nicht aus dem HTML', () => {
  /* Im HTML steht nur die Kennung. Die Adresse setzt der Pflichtteil beim
     Laden - so ueberlebt sie eine Umbenennung des Anhangs (N-18). */
  const h = edBaustein('bild', 'Der Schrank von hinten',
                       ['datei: bild-schrank', 'Die Anschluesse liegen links.']);
  assert.ok(h.includes('data-wiki-bild="bild-schrank"'), h);
  assert.ok(!/src=/.test(h), 'die Adresse steht schon im HTML: ' + h);
  assert.ok(h.includes('<figcaption>Der Schrank von hinten</figcaption>'), h);
  assert.ok(h.includes('Die Anschluesse liegen links.'), h);
});
pruefe('Ein Bild ohne Datei sagt das, statt leer zu bleiben', () => {
  const h = edBaustein('bild', 'Ohne alles', []);
  assert.ok(h.includes('Bild-Baustein ohne Datei'), h);
  assert.ok(!h.includes('data-wiki-bild'), h);
});
pruefe('Verweise werden Knoepfe, keine Adressen', () => {
  /* Eine Seite im Rahmen darf nicht selbst navigieren - sie bittet die
     Huelle. Ein href waere ein Ausbruch aus genau dieser Regel. */
  const h = edBaustein('verweise', 'Weiterlesen',
                       ['netzwerk-grundlagen | Netzwerk-Grundlagen',
                        'drucker-einrichten | Drucker einrichten']);
  assert.ok(!/href=/.test(h), 'da steht ein href: ' + h);
  assert.equal((h.match(/class="verweis"/g) || []).length, 2);
  assert.ok(h.includes('data-slug="netzwerk-grundlagen"'), h);
  assert.ok(h.includes('>Netzwerk-Grundlagen</button>'), h);
});
pruefe('Eine erfundene Kennung im Verweis wird entschaerft', () => {
  /* Was keine Kennung sein kann, darf auch keine werden. */
  const h = edBaustein('verweise', '', ['../../etc/passwd | Boese']);
  assert.ok(!h.includes('..'), h);
  assert.ok(h.includes('data-slug="etcpasswd"'), h);
});
pruefe('Die Checkliste zaehlt von Hand nachgerechnet', () => {
  const h = edBaustein('checkliste', 'Vor dem Losfahren',
                       ['Ladekabel dabei', 'Reifendruck geprueft',
                        '', 'Papiere dabei | Gruene Mappe']);
  /* Drei nicht leere Zeilen - die leere zaehlt nicht mit. */
  assert.equal((h.match(/type="checkbox"/g) || []).length, 3);
  assert.ok(h.includes('<span class="bk-stand-zahl">0</span> von 3'), h);
  assert.ok(h.includes('Gruene Mappe'), h);
  assert.ok(h.includes('nichts davon wird gespeichert'),
            'der Leser erfaehrt nicht, dass die Haken nirgends landen');
});
pruefe('Die neuen Bausteine ueberstehen den Rundlauf', () => {
  const markup = [
    ':::bild Der Schrank\ndatei: bild-schrank\nVon hinten.\n:::',
    ':::verweise Weiterlesen\nnetzwerk-grundlagen | Netzwerke\n:::',
    ':::checkliste Vorher\nEins\nZwei | dazu\n:::'
  ].join('\n\n');
  const bloecke = edMarkupZuBloecken(markup);
  assert.deepEqual(bloecke.map(b => b.art), ['bild', 'verweise', 'checkliste']);
  assert.equal(bloecke[0].kennung, 'bild-schrank');
  assert.equal(bloecke[0].titel, 'Der Schrank');
  assert.equal(bloecke[0].hinweis, 'Von hinten.');
  assert.deepEqual(bloecke[1].zeilen, [['netzwerk-grundlagen', 'Netzwerke']]);
  assert.deepEqual(bloecke[2].zeilen, [['Eins', ''], ['Zwei', 'dazu']]);
  /* Und wieder zurueck: derselbe Text, Zeichen fuer Zeichen. */
  assert.equal(edBloeckeZuMarkup(bloecke), markup);
});
pruefe('Ein Bild wird beim Speichern als Anhang genannt', () => {
  const markup = ':::bild Der Schrank\ndatei: bild-schrank\n:::';
  const bloecke = edMarkupZuBloecken(markup);
  bloecke[0].daten64 = 'iVBORw0KGgo=';
  const html = edSeiteBauen({slug:'probe', titel:'Probe', kurz:'', pfad:'Technik',
    gruppen:'', abschnitte:[{anker:'a', titel:'A', stichworte:'', gruppe:'',
    markup:markup, bloecke:bloecke}]});
  assert.ok(html.includes('id="bild-schrank" data-wiki-anhang=""'), html.slice(0, 400));
  assert.ok(html.includes('iVBORw0KGgo='), 'die Daten fehlen');
});
pruefe('Ein Bild ohne Datei kommt nicht durch die Pruefung', () => {
  const markup = ':::bild Der Schrank\ndatei: bild-schrank\n:::';
  ZUSTAND.editor = {neu:true, slug:'probe', titel:'Probe', kurz:'',
    pfad:'Technik', gruppen:'', abschnitte:[{anker:'a', titel:'A',
    stichworte:'', gruppe:'', markup:markup,
    bloecke:edMarkupZuBloecken(markup)}]};
  const m = edPruefbar(true);
  assert.equal(m.length, 1, m.join(' / '));
  assert.ok(/Bild-Baustein 1/.test(m[0]), m[0]);
});

pruefe('Jede Gruppe der Auswahl hat mindestens einen Baustein', () => {
  /* Eine leere Ueberschrift in der Auswahl waere ein Versprechen ohne
     Inhalt. */
  for(const [g, name] of ED_GRUPPEN){
    const drin = Object.values(ED_FORM).filter(f => f.gruppe === g);
    assert.ok(drin.length, 'Gruppe "' + name + '" ist leer');
  }
});

/* ------------------------------------------- Sicherheit: jede Blockart */
function tagsUndAttribute(html){
  /* Ein winziger Abtaster: er findet nur ECHTE Marken. Geschuetzter Text
     traegt &lt; und wird darum gar nicht erst gefunden - genau das ist die
     Trennung, auf die es ankommt. Ein Test, der stattdessen nach dem Wort
     "onerror" sucht, faellt auf harmlosen Text herein: &lt;img src=x
     onerror=... ist Text und keine Marke. */
  const marken = [];
  const attribute = [];
  const re = /<([a-zA-Z][\w-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>/g;
  let m;
  while((m = re.exec(html))){
    marken.push(m[1].toLowerCase());
    const ra = /([a-zA-Z_:][-\w:.]*)\s*(?:=\s*("[^"]*"|'[^']*'|[^\s>]*))?/g;
    let a;
    while((a = ra.exec(m[2]))){
      attribute.push([a[1].toLowerCase(),
                      (a[2] || '').replace(/^["']|["']$/g, '')]);
    }
  }
  return {marken, attribute};
}
pruefe('Kein Baustein laesst getippten Text zu HTML werden', () => {
  /* Der Reihe nach durch ALLE Bausteine, mit demselben boesartigen Text in
     Titel und Zeilen. Geprueft wird nicht, wie das Ergebnis aussieht,
     sondern dass daraus nirgends Auszeichnung wird. Ein neuer Baustein,
     der das Schuetzen vergisst, faellt hier auf und nicht beim Leser. */
  const boese = '"><img src=x onerror=alert(1)><script>alert(2)</scr' + 'ipt>';
  const fuer = new Set();
  for(const art of Object.keys(ED_FORM)){
    const spalten = (ED_FORM[art].spalten || ['Inhalt']).map(() => boese);
    const zeilen = art === 'pdf' || art === 'bild'
      ? ['datei: ' + boese, spalten.join(' | ')]
      : art === 'rechner'
        ? [boese + '=' + boese, '=' + boese, 'Einheit: ' + boese, boese]
        : [spalten.join(' | ')];
    const h = edBaustein(art, boese, zeilen);
    fuer.add(art);
    const {marken, attribute} = tagsUndAttribute(h);
    assert.ok(!marken.includes('script'), art + ': ein script-Element');
    for(const [name, wert] of attribute){
      assert.ok(!/^on/.test(name),
                art + ': Attribut "' + name + '" - da haengt Verhalten dran');
      if(name === 'src' || name === 'href')
        assert.ok(!/^\s*javascript:/i.test(wert),
                  art + ': ' + name + '="' + wert + '"');
    }
    /* Ein img gibt es nur im Bild-Baustein, und dort ohne Adresse im HTML. */
    if(marken.includes('img'))
      assert.equal(art, 'bild', art + ': ein img-Element');
    /* Gegenprobe, damit der Test nicht nur bestaetigt, dass ueberhaupt
       nichts drinsteht: der geschuetzte Text muss da sein. */
    assert.ok(h.includes('&lt;') || h.includes('&quot;') ||
              /Baustein ohne Datei/.test(h),
              art + ': vom Text ist gar nichts uebrig - ' + h.slice(0, 120));
  }
  assert.equal(fuer.size, Object.keys(ED_FORM).length);
});
pruefe('Eine ganze Seite mit boesem Text bleibt harmlos', () => {
  /* Derselbe Text durch den ganzen Erzeuger - Titel, Satz, Pfad, Gruppen,
     Anker, Stichworte und Markup. Der Meta-Block ist JSON und muss die
     Zeichen ebenfalls halten. */
  const boese = '</scr' + 'ipt><img src=x onerror=alert(1)>';
  const html = edSeiteBauen({
    slug: 'probe', titel: boese, kurz: boese, pfad: boese, gruppen: boese,
    abschnitte: [{anker: 'a', titel: boese, stichworte: boese,
                  gruppe: boese, markup: boese}]
  });
  const koerper = html.slice(html.indexOf('<body'),
                             html.indexOf('<' + 'script>'));
  const {marken, attribute} = tagsUndAttribute(koerper);
  assert.ok(!marken.includes('script'), 'ein script-Element im Koerper');
  assert.ok(!marken.includes('img'), 'ein img-Element im Koerper');
  for(const [name, wert] of attribute){
    assert.ok(!/^on/.test(name), 'Attribut "' + name + '" im Koerper');
    if(name === 'src' || name === 'href')
      assert.ok(!/^\s*javascript:/i.test(wert), name + '="' + wert + '"');
  }
  /* Der Meta-Block darf sich nicht selbst aufbrechen. Geprueft wird das
     so, wie ein Browser es sieht: alles bis zum ERSTEN Skript-Ende ist der
     Block - und das muss lesbares JSON sein, aus dem der Titel Zeichen fuer
     Zeichen zurueckkommt.
     (Die erste Fassung dieses Tests suchte nach "</scr"+"ipt>" im Bereich
     bis zum <style> - darin steht aber auch das richtige Ende des Blocks.
     Der Test war damit immer rot, auch bei harmlosen Titeln.) */
  const auf = html.indexOf('id="wiki-meta"');
  const anfang = html.indexOf('>', auf) + 1;
  const ende = html.indexOf('</scr' + 'ipt>', anfang);
  const roh = html.slice(anfang, ende);
  let gelesen = null;
  try { gelesen = JSON.parse(roh); } catch(err){
    assert.fail('der Meta-Block ist kein lesbares JSON: ' + err.message);
  }
  assert.equal(gelesen.titel, boese,
               'der Titel kommt nicht unveraendert zurueck');
  assert.equal(gelesen.kurz, boese);
});

/* ------------------------------------------- Die Huelle als Ganzes */
pruefe('Die Huelle bricht ihren eigenen Skriptblock nicht auf', () => {
  /* Ein Browser beendet ein <script> beim ERSTEN Skript-Ende - auch wenn
     es in einer Zeichenkette oder in einem Kommentar steht. Passiert das,
     ist der Rest der Datei kein Programm mehr, sondern Text: die Huelle
     laedt, zeigt aber nichts und kann nichts.
     Gemessen ist das einmal passiert, an einem Kommentar, der die
     Zeichenfolge als Beispiel nannte (N-33). Die Funktionstests liefen
     dabei alle gruen - sie schneiden sich ihre Funktionen mit regulaeren
     Ausdruecken heraus und sehen die Datei nie als Ganzes.

     Hier wird genau das geprueft, was der Browser tut: von der ersten
     oeffnenden Marke bis zum ersten Ende schneiden, und das Ergebnis
     uebersetzen lassen. */
  const auf = quelle.indexOf('<' + 'script>');
  assert.ok(auf > 0, 'kein Skriptblock in index.html gefunden');
  const anfang = auf + ('<' + 'script>').length;
  const ende = quelle.indexOf('<' + '/script>', anfang);
  assert.ok(ende > anfang, 'der Skriptblock wird nie geschlossen');
  const koerper = quelle.slice(anfang, ende);
  /* new Function wirft bei einem abgeschnittenen Programm - genau das
     wollen wir wissen. Ausgefuehrt wird nichts. */
  try {
    new Function(koerper);
  } catch(err){
    assert.fail('was der Browser vom Skript sieht, ist kein Programm: ' +
                err.message);
  }
  /* Und die Gegenprobe: hinter diesem Ende darf nur noch der Abspann der
     Seite stehen, kein weiterer Code. */
  const rest = quelle.slice(ende + ('<' + '/script>').length).trim();
  assert.ok(rest.length < 200,
            'hinter dem Skriptende stehen noch ' + rest.length + ' Zeichen');
});

/* ---------------------------------------------------------------- N-35
   "Eine Sache fehlt noch" war ein Satz ohne Weg: die Zeile liess sich
   anklicken, markierte aber nur den Text, und markiert wurden ohnehin nur
   drei der Faelle. Fehlte etwas anderes, passierte beim Speichern sichtbar
   nichts. Also: JEDER Befund nennt seine Stelle, und jede Stelle muss es
   wirklich geben. */
pruefe('Jeder Befund nennt seine Stelle (N-35)', () => {
  ZUSTAND.editor = {
    titel: 'x'.repeat(121), kurz: 'y'.repeat(301), pfad: '', slug: 'Falsch Slug',
    abschnitte: [
      {titel: '',  anker: '',  markup: '',  bloecke: [{art: 'pdf'}]},
      {titel: 'A', anker: 'a', markup: 't', bloecke: []},
      {titel: 'B', anker: 'a', markup: '',  bloecke: [{art: 'bild'}]}
    ]};
  const liste = edBefunde(true);
  /* Von Hand ausgezaehlt, in der Reihenfolge, in der die Pruefung laeuft:
     Titel zu lang, Satz zu lang, Adresse falsch, Pfad fehlt,
     Abschnitt 1 ohne Titel, Abschnitt 1 leer, PDF ohne Datei,
     Abschnitt 3 mit doppeltem Anker, Abschnitt 3 leer, Bild ohne Datei. */
  assert.deepEqual(liste.map(b => b.ziel), [
    'ed-titel', 'ed-kurz', 'ed-slug', 'ed-pfad',
    'ed-a-titel-0', 'ed-abschnitt-0', 'ed-block-0-0',
    'ed-a-anker-2', 'ed-abschnitt-2', 'ed-block-2-0']);
  liste.forEach(b => assert.ok(b.text && b.text.length > 10,
    'ein Befund ohne Satz: ' + JSON.stringify(b)));
});
pruefe('Jede genannte Stelle gibt es wirklich (N-35)', () => {
  /* Der eigentliche Zahn: ein Ziel, das kein Feld ist, waere ein Sprung ins
     Leere - und der sieht genauso aus wie der Fehler aus der Rueckmeldung. */
  ZUSTAND.editor = {
    titel: '', kurz: '', pfad: '', slug: '',
    abschnitte: [{titel: '', anker: '', markup: '', bloecke: [{art: 'pdf'}]}]};
  const ziele = edBefunde(true).map(b => b.ziel);
  assert.ok(ziele.length >= 4, 'zu wenige Befunde fuer diese Probe');
  ziele.forEach(z => {
    const muster = z.replace(/-\d+-\d+$/, '-${i}-${j}').replace(/-\d+$/, '-${i}');
    assert.ok(quelle.includes('id="' + muster + '"'),
      'kein Feld mit id="' + muster + '" in index.html - der Sprung ginge ins Leere');
  });
});
pruefe('Der leere Editor meldet genau vier Sachen (N-35)', () => {
  /* Die Zahl aus der Rueckmeldung. Von Hand: Titel, Pfad, Abschnittstitel,
     leerer Abschnitt. Die Adresse zaehlt NICHT mit - sie entsteht aus dem
     Titel, und zwei Punkte fuer dieselbe Aufgabe schrecken ab. */
  ZUSTAND.editor = edLeer();
  const liste = edBefunde(true);
  assert.equal(liste.length, 4, liste.map(b => b.text).join(' | '));
  assert.deepEqual(liste.map(b => b.ziel),
    ['ed-titel', 'ed-pfad', 'ed-a-titel-0', 'ed-abschnitt-0']);
});
pruefe('edPruefbar ist genau die Textsicht auf edBefunde (N-35)', () => {
  /* Zwei Pruefungen waeren zwei Wahrheiten. */
  ZUSTAND.editor = edLeer();
  assert.deepEqual(edPruefbar(true), edBefunde(true).map(b => b.text));
});
pruefe('Die Standzeile ist ein Knopf, der zur Stelle fuehrt (N-35)', () => {
  const zeile = quelle.match(/id="ed-stand"[\s\S]{0,120}/);
  assert.ok(zeile, 'ed-stand nicht gefunden');
  assert.ok(/<button[^>]*id="ed-stand"|id="ed-stand"[\s\S]{0,60}data-ed="zumfehler"/
              .test(quelle),
    'die Standzeile muss ein Knopf mit data-ed="zumfehler" sein - als <span> ' +
    'markiert ein Klick nur den Text');
  assert.ok(quelle.includes("if(was === 'zumfehler')"),
    'ohne Fall im Verteiler tut der Knopf nichts');
  assert.ok(/z\.disabled = !fehlt\.length/.test(quelle),
    'solange nichts fehlt, muss die Zeile gesperrt sein');
});

pruefe('Die Huelle scrollt nur ihre eigenen Kaesten (N-36)', () => {
  /* Der Befund: "eine HTML anfuegen" fuehrte auf eine schwarze Seite.
     scrollIntoView scrollt JEDEN scrollbaren Vorfahren - auch den Koerper.
     Der hat seit N-34 overflow:hidden und darum keine Leiste, laesst sich
     vom Programm aber sehr wohl schieben: gemessen stand die Huelle danach
     mit der Unterkante bei -122 px, also vollstaendig ausserhalb des
     Fensters, und es gab keinen Weg zurueck.

     Im Pflichtteil der SEITE ist das Dokument der richtige Scrollbereich -
     die Seite laeuft in ihrem eigenen Rahmen. Der Block wird darum
     herausgenommen. */
  const pflicht = quelle.match(/const ED_PFLICHTTEIL = \[[\s\S]*?\]\.join\('\\n'\);/);
  assert.ok(pflicht, 'ED_PFLICHTTEIL nicht gefunden - Test anpassen');
  const huelle = quelle.replace(pflicht[0], '');
  /* Gesucht ist der AUFRUF, nicht das Wort: der Kommentar in hinscrollen()
     nennt scrollIntoView absichtlich, damit der naechste Leser weiss, warum
     es hier nicht steht. Genau diese Falle war N-33. */
  assert.ok(!/\.scrollIntoView\s*\(/.test(huelle),
    'ein scrollIntoView-Aufruf in der Huelle - das scrollt auch den ' +
    'Koerper, hinscrollen() nehmen');
  assert.ok(/function hinscrollen\(el, mitte\)\{/.test(quelle),
    'ohne hinscrollen() gibt es keinen Ersatz');
  assert.ok(/function scrollKasten\(el\)\{/.test(quelle));
  const app = quelle.match(/^\.app\{[^}]*\}/m);
  assert.ok(app, 'keine Regel fuer .app gefunden');
  assert.ok(/position:\s*fixed/.test(app[0]),
    'ohne position:fixed haengt die Huelle am Koerper und laesst sich ' +
    'aus dem Fenster schieben');
  assert.ok(/inset:\s*0/.test(app[0]), 'die Huelle muss das ganze Fenster fuellen');
});

console.log('');
console.log(`${gut} ok, ${schlecht} Fehler`);
process.exit(schlecht ? 1 : 0);
