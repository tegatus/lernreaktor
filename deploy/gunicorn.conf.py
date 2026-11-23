# Gunicorn-Konfiguration für LernReaktor (wird vom systemd-Dienst verwendet)
import multiprocessing

bind = "127.0.0.1:8000"                       # nur lokal; nach aussen über nginx
workers = min(4, multiprocessing.cpu_count() * 2 + 1)
timeout = 180                                 # KI-Anfragen und grosse PDFs dürfen etwas dauern
graceful_timeout = 30
max_requests = 1000                           # Worker regelmässig erneuern
max_requests_jitter = 100
accesslog = "-"                               # ins Journal (journalctl -u lernreaktor)
errorlog = "-"
forwarded_allow_ips = "127.0.0.1"
