# BiVo-Import nur für Admins · Themen zuerst – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nur Admin-Lehrpersonen dürfen die BiVo-Kompetenzliste neu einlesen; Lernziele werden nur in vorher
angelegte Themen importiert (Auswahlliste statt Freitext).

**Architecture:** Spalte `User.ist_admin` (+ `SPALTEN_NACHTRAG`), CLI `set-admin` in `app/seed.py`,
Prüfung in `lp.kompetenzen`. Neue Route `lp.thema_neu`; `lp.lernziele_import` liest `thema_id` statt Namen.

**Tech Stack:** Flask, Flask-SQLAlchemy, click, Jinja2, pytest.

**Spec:** `docs/superpowers/specs/2026-11-26-admin-und-themen-design.md`

## Global Constraints

- Demo-Lehrperson `lp` ist kein Admin. `set-admin` nur für Rolle «lp».
- UI-Texte/Commits Deutsch (CH, «ss»). Tests: `.venv/Scripts/python -m pytest -q`.
- Feld «Neues Thema anlegen» im Aufgabenformular bleibt unverändert.

## Review Focus

- Bestehende Datenbank ohne Spalte `ist_admin` (Server, PostgreSQL, Tabelle `"user"` reserviert) → wird beim Start
  ergänzt, kein Absturz. Test in Task 1 (Spalte per ALTER entfernen geht in SQLite nicht → Test prüft, dass der
  Eintrag in `SPALTEN_NACHTRAG` steht und `spalten_ergaenzen()` auf frischer DB idempotent läuft).
- Manipulierter POST an den Import mit `thema_id` eines nicht existierenden Themas → Fehlermeldung, kein neues Thema. Task 2.
- Neues Thema mit Namen, der schon existiert (auch mit Leerzeichen drumherum) → Fehlermeldung, kein Duplikat. Task 2.

---

### Task 1: Admin-Flag, `set-admin`, BiVo-Upload nur für Admins

**Files:** Modify `app/models.py` (User + `SPALTEN_NACHTRAG`), `app/seed.py` (CLI), `app/lp.py` (`kompetenzen`),
`app/templates/lp/kompetenzen.html`; Test: `tests/test_admin.py`

**Interfaces:** Produces `User.ist_admin: bool` (Spalte), CLI `set-admin BENUTZERNAME [--entziehen]`.

- [ ] **Step 1: Failing tests**
```python
def test_lp_sieht_kein_bivo_upload(lp):        # GET /lp/kompetenzen → 200, 'name="datei"' nicht im HTML
def test_lp_darf_bivo_nicht_importieren(lp):   # POST /lp/kompetenzen (Datei) → 403
def test_admin_sieht_upload_und_importiert(app, lp):  # lp.ist_admin=True → 'name="datei"' im HTML; POST seed-xlsx → Flash "Importiert:"
def test_set_admin_cli(app):                   # runner.invoke(args=["set-admin","lp"]) → ist_admin True; "--entziehen" → False
def test_set_admin_nur_lp(app):                # "set-admin lea" → exit_code != 0, lea.ist_admin False; unbekannter Name ebenso
def test_spalte_nachgeruestet():               # ("user","ist_admin",…) in SPALTEN_NACHTRAG
```
- [ ] **Step 2: Run** → FAIL. **Step 3: Implementieren.** **Step 4: Suite** → PASS.
- [ ] **Step 5: Commit** `BiVo-Kompetenzliste nur noch für Admins einlesbar`

### Task 2: Thema anlegen; Import mit Themen-Auswahl

**Files:** Modify `app/lp.py` (neue Route `thema_neu` `POST /lp/themen/neu`, `lernziele_import`),
`app/templates/lp/lernziele.html`, `app/templates/lp/lernziele_import.html`; Tests: `tests/test_lernziele.py`
(bestehende Import-Tests auf `thema_id` umstellen)

**Interfaces:** Formularfelder `thema_neu`: `name`, `beschreibung`. Import: `thema_id` (statt `thema`),
GET-Vorwahl `?thema=<id>`. `importers.import_lernziele` unverändert (bekommt den Namen des gewählten Themas).

- [ ] **Step 1: Failing tests**
```python
def test_thema_anlegen(lp, app):               # POST name="  Gelelektrophorese " → Thema "Gelelektrophorese" existiert, Redirect /lp/lernziele
def test_thema_anlegen_doppelt(lp, app):       # name="qPCR" → "existiert bereits", 1 Thema qPCR
def test_import_hat_themen_auswahl(lp, app):   # GET /lp/lernziele/import?thema=<qpcr> → '<select name="thema_id"' und 'value="<id>" selected'
def test_import_ohne_themen_hinweis(lp, app):  # alle Themen gelöscht → "zuerst ein Thema" im HTML, kein '<select name="thema_id"'
def test_import_unbekanntes_thema(lp, app):    # POST thema_id=9999 + Text → Fehlermeldung, Anzahl Themen unverändert
def test_lernziele_seite_hat_thema_formular(lp):  # GET /lp/lernziele → action=".../lp/themen/neu" und "/lp/lernziele/import?thema="
```
- [ ] **Step 2: Run** → FAIL. **Step 3: Implementieren.** **Step 4: Suite** → PASS; kurzer Browser-Check lokal.
- [ ] **Step 5: Commit** `Lernziele: Thema zuerst anlegen, Import mit Themen-Auswahl`

### Abschluss
- [ ] Unabhängiges Review der Änderungen, Befunde test-first beheben, Merge/Push nach Rückfrage.
