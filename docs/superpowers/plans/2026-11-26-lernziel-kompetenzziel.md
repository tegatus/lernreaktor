# Lernziel-Formular mit Pflicht-Kompetenzzielen – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lehrpersonen legen einzelne Lernziele per Formular an bzw. bearbeiten sie, mit mindestens einem
BiVo-Kompetenzziel; Änderungen werden an bestehende Aufgaben weitergegeben, der Import lehnt Einträge ohne
gültigen Code ab, und das Aufgabenformular kreuzt die Kompetenzziele gewählter Lernziele sofort an.

**Architecture:** Neue Modul-Funktionen in `app/lernziele.py` kapseln Nummernvergabe, Setzen der
Kompetenzziele inkl. Nachführen der Aufgaben (Variante A) und Löschen. `app/lp.py` bekommt eine Route
`lernziel_bearbeiten` (neu/bearbeiten/löschen) mit Template `lp/lernziel_form.html`. Die BiVo-Liste aus dem
`auswahl`-Makro wird als eigenes Makro `bivo_liste` herausgelöst und im Lernziel-Formular wiederverwendet.

**Tech Stack:** Flask, Flask-SQLAlchemy, Jinja2, Vanilla-JS, pytest.

**Spec:** `docs/superpowers/specs/2026-11-26-lernziel-kompetenzziel-design.md`

## Global Constraints

- Mindestens **ein** gültiges BiVo-Leistungsziel pro Lernziel; mehrere möglich.
- Thema + Bereich + Nummer eines Lernziels bleibt eindeutig.
- Nur Rolle «lp» (`@lp_required`). CSRF-Feld via `{{ csrf() }}` in jedem Formular.
- UI-Texte und Commit-Nachrichten auf Deutsch (Schweizer Schreibweise, «ss» statt «ß»).
- Keine absoluten Rechnerpfade in Code/Doku. Tests: `.venv/Scripts/python -m pytest -q` (Windows) bzw.
  `.venv/bin/python -m pytest -q`.

## Review Focus

- Lernziel löschen, das an einem Theoriekapitel hängt (`kapitel_lernziel`) → darf nicht mit FK-Fehler
  scheitern (PostgreSQL!), Kapitel-Verknüpfung wird entfernt. Test in Task 1.
- Code entfernen, den ein **anderes** Lernziel derselben Aufgabe auch mitbringt → bleibt an der Aufgabe. Test in Task 1.
- Bearbeiten auf Thema+Bereich+Nummer, die schon ein anderes Lernziel hat → Fehlermeldung, nichts gespeichert;
  das eigene Lernziel unverändert speichern ist kein Konflikt. Test in Task 2.
- Formular mit nur unbekannten/manipulierten BiVo-Codes → wie «keins gewählt» abgelehnt. Test in Task 2.
- Bestehender Test `test_lernziel_vorauswahl_im_editor` prüft den Teilstring
  `name="lernziel" value="{id}" checked` → neues `data-bivo`-Attribut **vor** `name=` setzen. Task 4.

---

### Task 1: Domänenfunktionen in `app/lernziele.py`

**Files:**
- Create: `app/lernziele.py`
- Modify: `app/importers.py:115-145` (`import_lernziele` nutzt `kompetenzziele_setzen`)
- Test: `tests/test_lernziele.py` (gleiche `app`-Fixture wie `tests/test_app.py` – Fixture und `login`
  nach `tests/conftest.py` verschieben, `tests/test_app.py` importiert/nutzt sie von dort)

**Interfaces:**
- Produces:
  - `naechste_nummer(thema_id: int, bereich: str) -> int` – höchste Nummer im Thema+Bereich + 1, sonst 1.
  - `aufgaben_mit(lz: Lernziel) -> list[Aufgabe]` – alle Aufgaben (auch inaktive), die `lz` verwenden.
  - `kompetenzziele_setzen(lz: Lernziel, codes: Iterable[str]) -> int` – setzt `lz.leistungsziele` auf die
    existierenden Codes, führt Aufgaben nach, gibt Anzahl tatsächlich geänderter Aufgaben zurück. Kein Commit.
  - `lernziel_loeschen(lz: Lernziel) -> list[Aufgabe]` – gibt die verwendenden Aufgaben zurück; ist die Liste
    leer, werden Kapitel-Verknüpfungen entfernt und `lz` gelöscht (kein Commit), sonst passiert nichts.

- [ ] **Step 1: Fixture nach `tests/conftest.py` verschieben**, `tests/test_app.py` anpassen, Suite grün.

- [ ] **Step 2: Failing tests in `tests/test_lernziele.py`** (Lernziele aus Seed-Thema «qPCR»; neue Aufgaben direkt per Modell anlegen)

```python
def test_naechste_nummer(app):        # qPCR Bereich "a" hat 15 Lernziele (a1..a15) → 16; Bereich "z" → 1
def test_setzen_ergaenzt_und_entfernt(app):
    # lz mit codes {a.1.1}; Aufgabe A mit lernziele=[lz], leistungsziele=[a.1.1]
    # kompetenzziele_setzen(lz, ["a.1.2"]) == 1; A.codes == {"a.1.2"}
def test_setzen_behaelt_code_anderer_lernziele(app):
    # A hat lz1 (a.1.1) und lz2 (a.1.1, a.1.2); setzen(lz1, ["a.1.2"]) → A behält a.1.1
def test_setzen_ignoriert_unbekannte_codes(app):  # ["a.1.1", "x.9.9"] → lz.codes == {"a.1.1"}
def test_setzen_ohne_aenderung_zaehlt_null(app):  # gleiche Codes erneut → 0
def test_loeschen_blockiert_bei_aufgabe(app):     # lernziel_loeschen → [A], lz existiert noch
def test_loeschen_entfernt_kapitelverknuepfung(app):
    # TheorieKapitel mit lernziele=[lz], keine Aufgabe → [] ; nach commit: lz weg, Kapitel existiert, kapitel.lernziele == []
```

- [ ] **Step 3: Run** `.venv/Scripts/python -m pytest tests/test_lernziele.py -q` → FAIL (ImportError).

- [ ] **Step 4: Implementieren.** Nachführ-Regel pro Aufgabe `a`: `neu = (cur | new) - ((old - new) - andere)`,
  wobei `andere` = Codes aller übrigen Lernziele von `a`; geändert, wenn `neu != cur`.
  Aufgaben über `Aufgabe.query.filter(Aufgabe.lernziele.any(Lernziel.id == lz.id))`. Kapitel-Verknüpfung über
  `TheorieKapitel.query.filter(TheorieKapitel.lernziele.any(...))` und `.lernziele.remove(lz)`.
  In `import_lernziele` die Zeilen `lz.leistungsziele = [] …append` durch `kompetenzziele_setzen` ersetzen
  (fehlende Codes weiterhin sammeln).

- [ ] **Step 5: Run** ganze Suite → PASS.

- [ ] **Step 6: Commit** `git commit -m "Lernziele: Kompetenzziele setzen und an Aufgaben weitergeben"`

### Task 2: Formular zum Anlegen/Bearbeiten/Löschen

**Files:**
- Modify: `app/lp.py` (neue Route nach `lernziele_import`)
- Create: `app/templates/lp/lernziel_form.html`
- Modify: `app/templates/_macros.html` (Makro `bivo_liste` herauslösen, `auswahl` nutzt es)
- Modify: `app/templates/lp/lernziele.html` («+ Lernziel» je Thema, «Bearbeiten» je Zeile, rote Markierung)
- Test: `tests/test_lernziele.py`

**Interfaces:**
- Consumes: Task 1 (`naechste_nummer`, `kompetenzziele_setzen`, `lernziel_loeschen`).
- Produces: Endpoint `lp.lernziel_bearbeiten` mit Routen `GET/POST /lp/lernziele/neu` (Query `thema=<id>`
  wählt das Thema vor) und `GET/POST /lp/lernziele/<int:lz_id>`. Formularfelder: `thema` (id), `bereich`,
  `nummer`, `text`, `k_stufe` (1–6 oder leer), `bivo` (mehrfach), `loeschen=1` zum Löschen.
  Makro `bivo_liste(bereiche, sel_bivo=[])` – exakt das bisherige Innere von `#t-bivo`.

- [ ] **Step 1: Failing tests** (login `lp`/`lp-demo-2026`):

```python
def test_lernziel_anlegen_mit_kompetenzziel(lp, app):
    # POST /lp/lernziele/neu thema=qPCR.id, text="Ich kann X.", bivo=["b.5.3","a.1.1"], bereich="", nummer=""
    # erwartet = naechste_nummer(qpcr.id, "b") vor dem POST ermitteln
    # → redirect /lp/lernziele; neues lz: bereich "b" (erster Code), nummer == erwartet, codes {b.5.3, a.1.1}
def test_lernziel_ohne_kompetenzziel_abgelehnt(lp, app):  # ohne bivo → 200, "mindestens ein" im HTML, Anzahl unverändert
def test_lernziel_nur_unbekannte_codes_abgelehnt(lp, app):  # bivo=["x.9.9"] → wie oben
def test_lernziel_bearbeiten_fuehrt_aufgaben_nach(lp, app):
    # lz mit Aufgabe; POST /lp/lernziele/<id> mit neuem Code → Aufgabe hat neuen Code; Flash enthält "1 Aufgabe"
def test_lernziel_nummer_konflikt(lp, app):
    # a1 auf bereich a / nummer 2 → "existiert bereits", unverändert; a1 mit eigener Nummer speichern → ok
def test_lernziel_loeschen_blockiert(lp, app):  # loeschen=1 bei verwendetem lz → Titel der Aufgabe im Flash, lz existiert
def test_lernziele_liste_markiert_ohne_bivo(lp, app):  # lz.leistungsziele=[] → "kein BiVo-Ziel" auf /lp/lernziele
```

- [ ] **Step 2: Run** → FAIL (404).

- [ ] **Step 3: Implementieren.** Leeres `bereich` → `codes[0].split(".")[0]`; leere `nummer` →
  `naechste_nummer`. Fehler (Text leer, kein gültiger Code, Nummer < 1/keine Zahl, Duplikat) → Formular mit
  eingegebenen Werten erneut rendern + `flash(…, "fehler")`. Erfolg → `flash("Lernziel gespeichert." +
  " {n} Aufgabe(n) angepasst." falls n, "ok")`, Redirect `lp.lernziele`. Löschen blockiert →
  `flash("Wird noch verwendet von: " + Titel, "fehler")`. Formular: Felder wie im Spec-Sketch,
  `bivo_liste` darunter, Platzhalter «automatisch» für Bereich/Nummer, Löschen-Knopf mit
  `data-bestaetigen` nur beim Bearbeiten. Liste: Zelle BiVo zeigt bei leerer Liste
  `<span class="luecke">kein BiVo-Ziel</span>`.

- [ ] **Step 4: Run** ganze Suite → PASS. Kurz im Browser/Testclient prüfen, dass Prüfungs- und
  Übungsauswahl (`auswahl`-Makro) unverändert rendert.

- [ ] **Step 5: Commit** `git commit -m "Lernziele einzeln anlegen, bearbeiten und löschen"`

### Task 3: Import lehnt Einträge ohne gültigen Code ab

**Files:**
- Modify: `app/importers.py` (`import_lernziele`), `app/lp.py` (`lernziele_import`),
  `app/templates/lp/lernziele_import.html`
- Test: `tests/test_lernziele.py`

**Interfaces:**
- Produces: `import_lernziele(thema_name, eintraege, ersetzen=False) -> (thema, neu, akt, fehlende_codes, abgelehnt)`
  – `abgelehnt`: Liste der Einträge (dicts) ohne einen einzigen existierenden Code; diese werden nicht angelegt
  und bestehende nicht verändert. Aufrufer `app/seed.py` ignoriert den Rückgabewert (unverändert).

- [ ] **Step 1: Failing tests**

```python
def test_import_ohne_gueltigen_code_abgelehnt(app):
    # eintraege = parse_lernziele("1. Ich kann A. (x.9.9, K2) 2. Ich kann B. (a.1.1, x.9.9, K2)")
    # → neu == 1, abgelehnt[0]["nummer"] == 1, fehlende == ["x.9.9"]
def test_import_vorschau_warnt(lp, app):  # POST ohne bestaetigt → HTML enthält "wird nicht importiert"
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implementieren.** Route übergibt dem Template `bekannte` = Set existierender Codes; Vorschau
  markiert Zeilen ohne bekannten Code mit `<span class="luecke">kein gültiger BiVo-Code – wird nicht importiert</span>`.
  Nach Import: `flash(f"{len(abgelehnt)} Einträge ohne gültigen BiVo-Code nicht importiert: …Nummern", "fehler")`.
- [ ] **Step 4: Run** ganze Suite → PASS.
- [ ] **Step 5: Commit** `git commit -m "Lernziel-Import: Einträge ohne gültigen BiVo-Code ablehnen"`

### Task 4: Aufgabenformular kreuzt Kompetenzziele live an

**Files:**
- Modify: `app/templates/_macros.html` (`auswahl` erhält Parameter `bivo_mitnehmen=false`)
- Modify: `app/templates/lp/aufgabe_form.html:153` (`bivo_mitnehmen=true`)
- Modify: `app/static/auswahl.js`
- Test: `tests/test_lernziele.py`

**Interfaces:**
- Produces: bei `bivo_mitnehmen` trägt jede Lernziel-Checkbox `data-bivo="a.1.1 a.1.2"` (Leerzeichen-getrennt),
  **vor** dem `name`-Attribut. Prüfungs-/Übungsauswahl rendern ohne das Attribut (Auswahl-Semantik unverändert).

- [ ] **Step 1: Failing test**

```python
def test_aufgabenformular_hat_bivo_daten(lp, app):
    # GET /lp/aufgaben/neu → 'data-bivo="b.5.3 b.5.4" name="lernziel" value="{b16.id}"' im HTML
    # GET /lp/pruefungen/neu (bzw. Route von pruefung_neu.html) → "data-bivo" nicht im HTML
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implementieren** in `auswahl.js`: bei `change` einer `input[data-bivo]` in derselben `.auswahl`:
  angekreuzt → zugehörige `input[name=bivo]` ankreuzen; abgewählt → Codes abwählen, die kein anderes
  angekreuztes Lernziel mitbringt. Danach `change`-Event wie beim «alle»-Knopf auslösen. Den «alle»-Knopf
  im Lernziel-Panel ebenso behandeln (nach dem Umschalten für jede Box die Logik anwenden).
- [ ] **Step 4: Run** ganze Suite → PASS; im Browser lokal (`flask --app run run`, Demo-Login) prüfen:
  Lernziel ankreuzen → Tab «Kompetenzziele BiVo» zeigt die Codes angekreuzt; abwählen → wieder weg.
- [ ] **Step 5: Commit** `git commit -m "Aufgabenformular: Kompetenzziele gewählter Lernziele sofort ankreuzen"`

### Abschluss

- [ ] Ganze Suite grün; Spec-Abgleich; nach Rückfrage `git push`. Deploy auf den Server (Docker-Container neu
  bauen) nur nach ausdrücklicher Bestätigung – keine Migration nötig (keine Schemaänderung).
