"""Review-Hinweise aus Sicht der Lehrperson: Aufgabenliste, Vorschläge übernehmen, Rückfragen beantworten,
Reviewer-Zugänge verwalten."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .auth import lp_required
from .models import REVIEW_STATUS, ReviewKommentar, User, db
from .review import unterschiede, uebernehmen

bp = Blueprint("lp_review", __name__, url_prefix="/lp/review")

FUER_LP = ("vorschlag", "rueckfrage")


def offene_aufgaben():
    """Hinweise, bei denen die Lehrperson etwas tun muss (für Übersicht und Navigation)."""
    return (ReviewKommentar.query.filter(ReviewKommentar.status.in_(FUER_LP))
            .order_by(ReviewKommentar.geaendert_am).all())


@bp.route("/")
@lp_required
def liste():
    status = request.args.get("status")
    abfrage = ReviewKommentar.query
    if status in REVIEW_STATUS:
        abfrage = abfrage.filter_by(status=status)
    else:
        abfrage = abfrage.filter(ReviewKommentar.status.in_(FUER_LP + ("offen",)))
    zaehler = {s: ReviewKommentar.query.filter_by(status=s).count() for s in REVIEW_STATUS}
    return render_template("lp/review_liste.html", kommentare=abfrage.order_by(ReviewKommentar.erstellt_am).all(),
                           status=status, zaehler=zaehler, namen=REVIEW_STATUS)


@bp.route("/<int:kommentar_id>", methods=["GET", "POST"])
@lp_required
def hinweis(kommentar_id):
    k = db.get_or_404(ReviewKommentar, kommentar_id)
    if request.method == "POST":
        aktion = request.form.get("aktion")
        notiz = request.form.get("notiz", "").strip()[:4000]
        if aktion in ("uebernehmen", "editor") and k.status == "vorschlag" and (k.aufgabe or k.kapitel):
            uebernehmen(k)
            k.status = "erledigt"
            k.eintrag("lp", "notiz", notiz or ("Vorschlag übernommen." if k.vorschlag_dict else "Erledigt, keine Änderung nötig."))
            db.session.commit()
            if aktion == "editor":
                flash("Vorschlag übernommen – jetzt bei Bedarf anpassen.", "ok")
                return redirect(url_for("lp.aufgabe_bearbeiten", aufgabe_id=k.aufgabe_id) if k.aufgabe
                                else url_for("theorie.kapitel_bearbeiten", kapitel_id=k.kapitel_id))
            flash("Vorschlag übernommen.", "ok")
        elif aktion == "antworten" and k.status in ("rueckfrage", "vorschlag") and notiz:
            k.eintrag("lp", "antwort", notiz)
            k.status = "offen"  # Claude Code nimmt den Hinweis mit der Antwort erneut auf
            k.vorschlag = None
            db.session.commit()
            flash("Antwort gespeichert. Der Hinweis wird beim nächsten Lauf erneut bearbeitet.", "ok")
        elif aktion == "ablehnen" and k.status not in ("erledigt", "abgelehnt"):
            k.status = "abgelehnt"
            k.eintrag("lp", "notiz", notiz or "Nicht übernommen.")
            db.session.commit()
            flash("Hinweis abgeschlossen (nicht übernommen).", "ok")
        elif aktion == "erledigt" and k.status not in ("erledigt", "abgelehnt"):
            k.status = "erledigt"
            k.eintrag("lp", "notiz", notiz or "Selbst erledigt.")
            db.session.commit()
            flash("Hinweis als erledigt markiert.", "ok")
        else:
            flash("Diese Aktion ist im aktuellen Status nicht möglich (oder die Antwort fehlt).", "fehler")
            return redirect(url_for(".hinweis", kommentar_id=k.id))
        naechster = next((x for x in offene_aufgaben() if x.id != k.id), None)
        return redirect(url_for(".hinweis", kommentar_id=naechster.id) if naechster else url_for(".liste"))
    return render_template("lp/review_hinweis.html", k=k, diff=unterschiede(k) if k.status == "vorschlag" else [],
                           namen=REVIEW_STATUS)


# ---------------------------------------------------------------- Reviewer-Zugänge

@bp.route("/zugaenge", methods=["GET", "POST"])
@lp_required
def zugaenge():
    from .lp import _benutzername, _passwort
    neu = None
    if request.method == "POST":
        aktion = request.form.get("aktion")
        if aktion == "neu" and request.form.get("name", "").strip():
            name = request.form["name"].strip()[:120]
            pw = _passwort()
            u = User(benutzername=_benutzername(name), anzeigename=name, rolle="reviewer", passwort_aendern=True)
            u.set_passwort(pw)
            db.session.add(u)
            db.session.commit()
            neu = (name, u.benutzername, pw)
            flash("Zugang erstellt. Passwort jetzt weitergeben – es wird nicht erneut angezeigt.", "ok")
        else:
            u = db.session.get(User, request.form.get("user_id", type=int) or 0)
            if not u or not u.ist_reviewer:
                flash("Unbekannter Zugang.", "fehler")
            elif aktion == "passwort":
                pw = _passwort()
                u.set_passwort(pw)
                u.passwort_aendern = True
                db.session.commit()
                neu = (u.anzeigename, u.benutzername, pw)
                flash("Neues Passwort erzeugt.", "ok")
            elif aktion == "aktiv":
                u.aktiv = not u.aktiv
                db.session.commit()
                flash(f"Zugang {'aktiviert' if u.aktiv else 'deaktiviert'}.", "ok")
    reviewer = User.query.filter_by(rolle="reviewer").order_by(User.anzeigename).all()
    anzahl = {u.id: ReviewKommentar.query.filter_by(autor_id=u.id).count() for u in reviewer}
    return render_template("lp/review_zugaenge.html", reviewer=reviewer, neu=neu, anzahl=anzahl)


@bp.app_context_processor
def _anzahl_fuer_navigation():
    """Anzahl offener Review-Aufgaben als Badge in der Navigation der Lehrperson."""
    if current_user.is_authenticated and current_user.ist_lp:
        return {"review_aufgaben": ReviewKommentar.query.filter(ReviewKommentar.status.in_(FUER_LP)).count()}
    return {"review_aufgaben": 0}

