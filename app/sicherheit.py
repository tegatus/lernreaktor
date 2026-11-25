"""Sicherheitsfunktionen: Login-Sperre, Sicherheits-Header, Sitzungs-Timeout, erzwungener Passwortwechsel, CSRF.

Konfiguration (Umgebungsvariablen):
  LERNREAKTOR_HTTPS=1     Betrieb über HTTPS: Cookies nur über HTTPS (Secure) und HSTS-Header
  LERNREAKTOR_PROXY=1     hinter einem Reverse-Proxy (nginx/Caddy): X-Forwarded-* auswerten
  INAKTIV_MINUTEN       automatische Abmeldung nach Inaktivität (Standard 60)
"""
import hmac
import os
import secrets
import time
from datetime import timedelta

from flask import abort, flash, redirect, request, session, url_for
from flask_login import current_user, logout_user

from .models import LoginVersuch, db, now

# Login-Sperre: nach MAX_FEHLER Fehlversuchen innerhalb des Fensters wird gesperrt
SPERR_FENSTER = timedelta(minutes=15)
MAX_FEHLER_KONTO = 5      # pro Benutzername
MAX_FEHLER_IP = 20        # pro IP-Adresse (z. B. Ausprobieren vieler Benutzernamen)


# ---------------------------------------------------------------- CSRF

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def csrf_pruefen():
    token = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
    erwartet = session.get("_csrf") or ""
    # Vergleich in konstanter Zeit (kein Rückschluss über Antwortzeiten)
    if not erwartet or not hmac.compare_digest(token.encode(), erwartet.encode()):
        abort(400, "Ungültiges Formular-Token – bitte Seite neu laden.")


# ---------------------------------------------------------------- Login-Sperre

def _client_ip():
    return (request.remote_addr or "?")[:64]


def login_gesperrt(benutzername):
    """Gibt die verbleibenden Sperrminuten zurück (0 = nicht gesperrt)."""
    seit = now() - SPERR_FENSTER
    q = LoginVersuch.query.filter(LoginVersuch.zeit >= seit, LoginVersuch.erfolgreich.is_(False))
    konto = q.filter(LoginVersuch.benutzername == benutzername).order_by(LoginVersuch.zeit).all()
    ip = q.filter(LoginVersuch.ip == _client_ip()).order_by(LoginVersuch.zeit).all()
    for versuche, grenze in ((konto, MAX_FEHLER_KONTO), (ip, MAX_FEHLER_IP)):
        if len(versuche) >= grenze:
            frei_ab = versuche[-grenze].zeit + SPERR_FENSTER
            return max(1, int((frei_ab - now()).total_seconds() // 60) + 1)
    return 0


def login_protokollieren(benutzername, erfolgreich):
    db.session.add(LoginVersuch(benutzername=benutzername[:80], ip=_client_ip(), erfolgreich=erfolgreich))
    if erfolgreich:  # erfolgreiche Anmeldung setzt den Zähler des Kontos zurück
        LoginVersuch.query.filter_by(benutzername=benutzername, erfolgreich=False).delete()
    # alte Einträge aufräumen
    LoginVersuch.query.filter(LoginVersuch.zeit < now() - timedelta(days=1)).delete()
    db.session.commit()


def sitzung_neu_beginnen():
    """Vor dem Login: alte Sitzung verwerfen (Schutz vor Session Fixation), neues CSRF-Token."""
    session.clear()
    session.permanent = True
    session["zuletzt"] = time.time()


# ---------------------------------------------------------------- Registrierung in der App

def einrichten(app):
    https = os.environ.get("LERNREAKTOR_HTTPS") == "1" or app.config.get("LERNREAKTOR_HTTPS")
    app.config.setdefault("INAKTIV_MINUTEN", int(os.environ.get("INAKTIV_MINUTEN", 60)))
    app.config.update(
        SESSION_COOKIE_SECURE=bool(https),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),   # absolute Höchstdauer einer Sitzung
    )
    if os.environ.get("LERNREAKTOR_PROXY") == "1":
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    if not https and not app.debug and not app.testing:
        app.logger.warning("LERNREAKTOR_HTTPS ist nicht gesetzt: Cookies werden auch über HTTP gesendet. "
                           "Im Betrieb immer HTTPS verwenden und LERNREAKTOR_HTTPS=1 setzen.")

    @app.before_request
    def _vor_jeder_anfrage():
        if request.method == "POST" and not app.config.get("TESTING_NO_CSRF") and not request.path.startswith("/api/agent/"):
            csrf_pruefen()
        if request.endpoint == "static" or not current_user.is_authenticated:
            return None
        # Abmeldung nach Inaktivität
        limit = app.config["INAKTIV_MINUTEN"] * 60
        zuletzt = session.get("zuletzt", 0)
        if limit and time.time() - zuletzt > limit:
            logout_user()
            session.clear()
            flash("Du wurdest nach längerer Inaktivität abgemeldet.", "info")
            return redirect(url_for("auth.login", next=request.full_path if request.method == "GET" else None))
        session["zuletzt"] = time.time()
        # erzwungener Passwortwechsel (z. B. nach generiertem Startpasswort)
        if current_user.passwort_aendern and request.endpoint not in ("auth.passwort", "auth.logout"):
            if request.method == "GET":
                return redirect(url_for("auth.passwort"))
            abort(403)
        return None

    @app.after_request
    def _sicherheits_header(antwort):
        h = antwort.headers
        h.setdefault("Content-Security-Policy", "; ".join([
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",        # style-Attribute in Vorlagen
            "img-src 'self' data: blob:",              # Vorschau neuer Bilder (blob:), Canvas (data:)
            "font-src 'self'",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]))
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "same-origin")
        h.setdefault("Permissions-Policy", "geolocation=(), microphone=(), payment=(), usb=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if https:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if current_user.is_authenticated and request.endpoint != "static":
            h.setdefault("Cache-Control", "no-store")  # persönliche Seiten nicht im Browser-Cache ablegen
        return antwort
