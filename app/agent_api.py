"""Agent-Schnittstelle für Claude Code (Befehl /reviews, z. B. als geplante Cloud-Routine).

Anmeldung: «Authorization: Bearer <AGENT_TOKEN>». Ohne konfigurierten Token ist die Schnittstelle aus (404).
Claude Code liest offene Review-Hinweise und schreibt Vorschläge oder Rückfragen zurück. Es kann Aufgaben und
Kapitel nie direkt ändern – das macht nur die Lehrperson. Daten von Lernenden sind hier nicht erreichbar.
"""
import hmac
import json

from flask import Blueprint, abort, current_app, jsonify, request

from .aufgabentypen import rendern
from .models import ReviewKommentar, db
from .review import AUFGABE_FELDER, KAPITEL_FELDER, pruefe_aufgabe, pruefe_kapitel

bp = Blueprint("agent_api", __name__, url_prefix="/api/agent")


@bp.before_request
def _anmelden():
    token = current_app.config.get("AGENT_TOKEN") or ""
    if not token:
        abort(404)
    angegeben = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(angegeben.encode(), token.encode()):
        return jsonify(fehler="Nicht angemeldet: gültigen Token als «Authorization: Bearer …» senden."), 401
    return None


@bp.errorhandler(404)
def _nicht_gefunden(e):
    return jsonify(fehler="Nicht gefunden."), 404


def _ziel(k):
    if k.aufgabe:
        a = k.aufgabe
        g = rendern(a, 1)
        return {"art": "aufgabe", "id": a.id, "felder": a.to_dict(), "aktiv": a.aktiv,
                "bilder": [{"nr": b.nr, "groesse": b.groesse, "nur_loesung": b.nur_loesung,
                            "beschriftung": b.beschriftung} for b in a.bilder],
                "beispiel_mit_zahlen": {"text": g.text, "loesung": g.loesung, "fehler": g.fehler},
                "theorie": [x.label for x in a.kapitel], "erlaubte_felder": list(AUFGABE_FELDER)}
    if k.kapitel:
        x = k.kapitel
        return {"art": "kapitel", "id": x.id, "dokument": x.dokument.titel, "nummer": x.nummer,
                "felder": {"titel": x.titel, "text": x.text},
                "bilder": [{"nr": b.nr, "groesse": b.groesse, "beschriftung": b.beschriftung} for b in x.bilder],
                "erlaubte_felder": list(KAPITEL_FELDER)}
    return None


def _als_json(k):
    return {"id": k.id, "status": k.status, "stelle": k.stelle, "zitat": k.zitat, "text": k.text,
            "erstellt_am": k.erstellt_am.isoformat(timespec="minutes"), "verlauf": k.eintraege, "ziel": _ziel(k)}


def _konflikt(meldung):
    antwort = jsonify(fehler=meldung)
    antwort.status_code = 409
    abort(antwort)


def _kommentar(kommentar_id, status=("offen",)):
    k = db.get_or_404(ReviewKommentar, kommentar_id)
    if k.status not in status:
        _konflikt(f"Hinweis {k.id} hat den Status «{k.status}» und kann nicht bearbeitet werden.")
    if not (k.aufgabe or k.kapitel):
        _konflikt("Das Ziel dieses Hinweises gibt es nicht mehr.")
    return k


@bp.route("/kommentare")
def kommentare():
    status = request.args.get("status", "offen")
    liste = ReviewKommentar.query.filter_by(status=status).order_by(ReviewKommentar.erstellt_am).limit(50).all()
    return jsonify(kommentare=[_als_json(k) for k in liste])


@bp.route("/kommentare/<int:kommentar_id>")
def kommentar(kommentar_id):
    return jsonify(_als_json(db.get_or_404(ReviewKommentar, kommentar_id)))


@bp.route("/kommentare/<int:kommentar_id>/vorschlag", methods=["POST"])
def vorschlag(kommentar_id):
    """{zusammenfassung, aenderungen}: aenderungen = nur die geänderten Felder; {} = keine Änderung nötig."""
    k = _kommentar(kommentar_id)
    d = request.get_json(silent=True) or {}
    zusammenfassung = str(d.get("zusammenfassung") or "").strip()[:4000]
    aenderungen = d.get("aenderungen")
    if not zusammenfassung or not isinstance(aenderungen, dict):
        return jsonify(fehler="Erwartet: {\"zusammenfassung\": Text, \"aenderungen\": {Feld: neuer Wert}}."), 422
    if aenderungen:
        bereinigt, fehler = (pruefe_aufgabe if k.aufgabe else pruefe_kapitel)(k.aufgabe or k.kapitel, aenderungen)
        if fehler:
            return jsonify(fehler="Vorschlag ungültig.", details=fehler), 422
        if not bereinigt:
            return jsonify(fehler="Der Vorschlag ändert nichts. Für «keine Änderung nötig» aenderungen = {} senden."), 422
        aenderungen = bereinigt
    k.vorschlag = json.dumps(aenderungen, ensure_ascii=False)
    k.zusammenfassung = zusammenfassung
    k.status = "vorschlag"
    k.eintrag("ki", "vorschlag", zusammenfassung)
    db.session.commit()
    return jsonify(ok=True, status=k.status, geaenderte_felder=list(aenderungen))


@bp.route("/kommentare/<int:kommentar_id>/rueckfrage", methods=["POST"])
def rueckfrage(kommentar_id):
    """{frage}: unklarer Hinweis – die Lehrperson beantwortet die Frage beim nächsten Anmelden."""
    k = _kommentar(kommentar_id)
    frage = str((request.get_json(silent=True) or {}).get("frage") or "").strip()[:4000]
    if not frage:
        return jsonify(fehler="Erwartet: {\"frage\": Text}."), 422
    k.status = "rueckfrage"
    k.eintrag("ki", "frage", frage)
    db.session.commit()
    return jsonify(ok=True, status=k.status)
