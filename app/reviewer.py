"""Reviewer: lesen alle Aufgaben (inkl. Lösungen und Prüfungsaufgaben) und Theoriekapitel und melden Probleme.

Reviewer sehen keine Daten von Lernenden. Schreiben dürfen sie nur Kommentare.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user
from sqlalchemy import or_

from . import storage
from .aufgabentypen import rendern
from .auth import reviewer_required
from .markup import angehaengte_bilder, markup_html, sichtbare_bilder
from .models import (REVIEW_STATUS, REVIEW_STELLEN, Aufgabe, AufgabeBild, ReviewKommentar, TheorieKapitel, Thema,
                     db)
from .theorie import kapitel_html

bp = Blueprint("reviewer", __name__, url_prefix="/review")


def aufgabe_html(a, seed=1):
    """Aufgabentext und Lösung wie auf den Blättern (Beispielwerte mit festem Seed)."""
    g = rendern(a, seed)
    url = lambda b: url_for("reviewer.bild", bild_id=b.id)  # noqa: E731
    frei_a, frei_l = angehaengte_bilder(a)
    return (markup_html(g.text, sichtbare_bilder(a, "aufgabe"), url, frei_a),
            markup_html(g.loesung, sichtbare_bilder(a, "loesung"), url, frei_l), g.fehler)


@bp.route("/")
@reviewer_required
def dashboard():
    q = request.args.get("q", "").strip()
    thema = request.args.get("thema", type=int)
    abfrage = Aufgabe.query.filter_by(aktiv=True)
    if thema:
        abfrage = abfrage.filter(Aufgabe.themen.any(Thema.id == thema))
    if q:
        abfrage = abfrage.filter(or_(Aufgabe.titel.ilike(f"%{q}%"), Aufgabe.text.ilike(f"%{q}%")))
    aufgaben = abfrage.order_by(Aufgabe.titel).all()
    meine = ReviewKommentar.query.filter_by(autor_id=current_user.id)
    offen = {k.aufgabe_id for k in meine if k.aufgabe_id and k.status not in ("erledigt", "abgelehnt")}
    return render_template("reviewer/dashboard.html", aufgaben=aufgaben, themen=Thema.query.order_by(Thema.name).all(),
                           q=q, thema=thema, offen=offen, anzahl_meine=meine.count())


@bp.route("/aufgabe/<int:aufgabe_id>", methods=["GET", "POST"])
@reviewer_required
def aufgabe(aufgabe_id):
    a = db.get_or_404(Aufgabe, aufgabe_id)
    if request.method == "POST":
        return _kommentar_speichern(ReviewKommentar(aufgabe=a), url_for(".aufgabe", aufgabe_id=a.id))
    text, loesung, fehler = aufgabe_html(a)
    return render_template("reviewer/aufgabe.html", a=a, text=text, loesung=loesung, fehler=fehler,
                           kommentare=a.review_kommentare, stellen=REVIEW_STELLEN)


@bp.route("/kapitel/<int:kapitel_id>", methods=["GET", "POST"])
@reviewer_required
def kapitel(kapitel_id):
    k = db.get_or_404(TheorieKapitel, kapitel_id)
    if not k.sichtbar:
        abort(404)
    if request.method == "POST":
        return _kommentar_speichern(ReviewKommentar(kapitel=k), url_for(".kapitel", kapitel_id=k.id))
    return render_template("reviewer/kapitel.html", k=k, inhalt=kapitel_html(k), kommentare=k.review_kommentare,
                           stellen={"text": "Text", "bild": "Grafik", "zuordnung": "Lernziele",
                                    "sonstiges": "Sonstiges"})


def _kommentar_speichern(kommentar, zurueck):
    text = request.form.get("text", "").strip()
    if not text:
        flash("Bitte beschreibe das Problem.", "fehler")
        return redirect(zurueck)
    kommentar.autor = current_user
    kommentar.text = text[:5000]
    kommentar.zitat = request.form.get("zitat", "").strip()[:2000]
    stelle = request.form.get("stelle")
    kommentar.stelle = stelle if stelle in REVIEW_STELLEN else "sonstiges"
    db.session.add(kommentar)
    db.session.commit()
    flash("Danke! Dein Hinweis ist gespeichert und wird bearbeitet.", "ok")
    return redirect(zurueck + "#kommentare")


@bp.route("/kommentare")
@reviewer_required
def kommentare():
    liste = (ReviewKommentar.query.filter_by(autor_id=current_user.id)
             .order_by(ReviewKommentar.erstellt_am.desc()).all())
    return render_template("reviewer/kommentare.html", kommentare=liste, status=REVIEW_STATUS, stellen=REVIEW_STELLEN)


@bp.route("/bild/<int:bild_id>")
@reviewer_required
def bild(bild_id):
    b = db.get_or_404(AufgabeBild, bild_id)
    return send_file(storage.absolut(b.datei))
