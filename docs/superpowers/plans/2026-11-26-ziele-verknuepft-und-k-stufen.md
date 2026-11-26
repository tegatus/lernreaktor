# Ziele verknüpft · K-Stufen-Filter als Admin-Option – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In Übungsblatt- und Prüfungsauswahl kreuzen sich Lernziele und Kompetenzziele gegenseitig an und zählen
als eine ODER-Gruppe; der K-Stufen-Filter erscheint nur, wenn ein Admin ihn einschaltet.

**Architecture:** `filter_aufgaben` verknüpft Lernziel- und Code-Bedingung mit ODER. Modell `Einstellung`
(Schlüssel/Wert) + Helfer `einstellung(name)` / `einstellung_setzen(name, wert)` in `app/einstellungen.py`, als
Jinja-Global registriert. `auswahl_aus_request` verwirft K-Stufen, wenn der Filter aus ist. Makro `auswahl`
bekommt `verknuepfen` = `none` | `"einseitig"` | `"beidseitig"`; JS in `auswahl.js`.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, Vanilla-JS, pytest.

**Spec:** `docs/superpowers/specs/2026-11-26-ziele-verknuepft-und-k-stufen-design.md`

## Global Constraints

- `k_stufen_filter` Standard **aus**. Einstellungsseite nur für Admins (`current_user.ist_admin`), sonst 403.
- Aufgabenformular bleibt einseitig. Prüfungslogik (`stelle_pruefung_zusammen`) unverändert.
- UI/Commits Deutsch (CH). Tests: `.venv/Scripts/python -m pytest -q`.

## Review Focus

- Bestehender Test `test_aufgabenformular_hat_bivo_daten` erwartet kein `data-bivo` auf `/lp/pruefungen/neu` →
  wird bewusst angepasst (Prüfung jetzt beidseitig). Task 2.
- Bestehende Prüfungsparameter mit `k_stufen` in gespeicherten Prüfungen (JSON) → Anzeige darf nicht brechen,
  wenn der Filter aus ist (nur neue Auswahl ignoriert K). Task 3.
- Student schickt `k=3` manuell, Filter aus → wird ignoriert (Trefferzahl und Blatt). Task 3.

---

### Task 1: ODER-Gruppe in `filter_aufgaben`
**Files:** `app/selection.py`, `app/templates/lernende/neu.html` (Erklärtext); Test `tests/test_auswahl.py`
- [ ] Failing tests: `test_lernziel_oder_kompetenzziel` (Aufgabe A nur mit Code e.3.1, Aufgabe B nur mit
  Lernziel b16 → `filter_aufgaben(leistungsziel_codes=["e.3.1"], lernziel_ids=[b16])` enthält beide),
  `test_thema_bleibt_und` (zusätzlich Thema, das A nicht hat → A fehlt).
- [ ] Implementieren (`or_` der beiden `in_`-Bedingungen), Text anpassen, Suite grün, Commit
  `Übungsauswahl: Lernziele und Kompetenzziele zählen als eine Gruppe`.

### Task 2: Gegenseitiges Ankreuzen
**Files:** `app/templates/_macros.html`, `app/templates/lp/aufgabe_form.html`, `lernende/neu.html`,
`lp/pruefung_neu.html`, `app/static/auswahl.js`; Test `tests/test_auswahl.py`, `tests/test_lernziele.py`
- [ ] Makro: `bivo_mitnehmen` ersetzt durch `verknuepfen=none`; bei gesetztem Wert tragen Lernziel-Boxen
  `data-bivo` (vor `name=`) und der Container `data-verknuepfen="einseitig|beidseitig"`.
- [ ] Failing tests: `/lernende/neu` und `/lp/pruefungen/neu` enthalten `data-verknuepfen="beidseitig"` und
  `data-bivo`; `/lp/aufgaben/neu` `data-verknuepfen="einseitig"`. Bestehenden Test anpassen.
- [ ] JS: beidseitig zusätzlich: Code an → Lernziele mit dem Code an; Code aus → diese aus; keine Kette.
  Browser-Check lokal. Commit `Auswahl: Lernziele und Kompetenzziele kreuzen sich gegenseitig an`.

### Task 3: Einstellungen und K-Stufen-Filter
**Files:** Create `app/einstellungen.py`; Modify `app/models.py` (Modell `Einstellung`), `app/__init__.py`
(Jinja-Global), `app/lernende.py` (`auswahl_aus_request`), `app/lp.py` (Route `einstellungen` GET/POST
`/lp/einstellungen`), `app/templates/lp/einstellungen.html`, `base.html` (Menü nur Admin), `_macros.html`
(`zeige_k` Standard = Einstellung); Test `tests/test_admin.py`
- [ ] Failing tests: Standard aus → `/lernende/neu` ohne `name="k"`; `/lernende/anzahl?lernziel=..&k=6` gleich
  wie ohne `k`; Nicht-Admin GET/POST `/lp/einstellungen` → 403; Admin schaltet ein → `name="k"` erscheint und
  `k` filtert; Menüeintrag «Einstellungen» nur für Admin; bestehende Prüfung mit `k_stufen` im JSON lädt (200).
- [ ] Implementieren, Suite grün, Commit `K-Stufen-Filter als Admin-Einstellung (Standard aus)`.

### Abschluss
- [ ] Unabhängiges Review, Befunde test-first beheben, dann Merge in main und Push.
