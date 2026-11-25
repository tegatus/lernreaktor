from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .models import User, db
from .sicherheit import login_gesperrt, login_protokollieren, sitzung_neu_beginnen

bp = Blueprint("auth", __name__)


def lp_required(f):
    @wraps(f)
    @login_required
    def wrapper(*a, **kw):
        if not current_user.ist_lp:
            abort(403)
        return f(*a, **kw)
    return wrapper


def lernende_required(f):
    @wraps(f)
    @login_required
    def wrapper(*a, **kw):
        if not current_user.ist_lernende:
            return redirect(url_for("auth.start"))
        return f(*a, **kw)
    return wrapper


def reviewer_required(f):
    @wraps(f)
    @login_required
    def wrapper(*a, **kw):
        if not current_user.ist_reviewer:
            abort(403)
        return f(*a, **kw)
    return wrapper


def startseite(u):
    return url_for("lp.dashboard" if u.ist_lp else "reviewer.dashboard" if u.ist_reviewer else "lernende.dashboard")


@bp.route("/")
def start():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return redirect(startseite(current_user))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("benutzername", "").strip().lower()[:80]
        sperre = login_gesperrt(name)
        if sperre:
            flash(f"Zu viele Fehlversuche. Bitte in {sperre} Minuten erneut versuchen.", "fehler")
            return render_template("auth/login.html"), 429
        u = User.query.filter_by(benutzername=name).first()
        if u and u.aktiv and u.check_passwort(request.form.get("passwort", "")):
            login_protokollieren(name, True)
            ziel = request.args.get("next")
            sitzung_neu_beginnen()
            login_user(u)
            if not ziel or not ziel.startswith("/") or ziel.startswith("//") or "\\" in ziel:
                ziel = url_for("auth.start")
            return redirect(ziel)
        login_protokollieren(name, False)
        flash("Benutzername oder Passwort falsch.", "fehler")
    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/passwort", methods=["GET", "POST"])
@login_required
def passwort():
    if request.method == "POST":
        alt, neu, neu2 = (request.form.get(k, "") for k in ("alt", "neu", "neu2"))
        if not current_user.check_passwort(alt):
            flash("Das bisherige Passwort stimmt nicht.", "fehler")
        elif len(neu) < 8:
            flash("Das neue Passwort muss mindestens 8 Zeichen lang sein.", "fehler")
        elif neu != neu2:
            flash("Die beiden neuen Passwörter stimmen nicht überein.", "fehler")
        elif neu == alt:
            flash("Das neue Passwort muss sich vom bisherigen unterscheiden.", "fehler")
        else:
            current_user.set_passwort(neu)
            current_user.passwort_aendern = False
            db.session.commit()
            flash("Passwort geändert.", "ok")
            return redirect(url_for("auth.start"))
    return render_template("auth/passwort.html")
