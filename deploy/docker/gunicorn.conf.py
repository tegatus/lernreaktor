# Gunicorn-Konfiguration für den Container-Betrieb (hinter Caddy im Docker-Netz "web").
import multiprocessing

bind = "0.0.0.0:8000"
workers = min(4, multiprocessing.cpu_count() * 2 + 1)
timeout = 180                                 # KI-Anfragen und grosse PDFs dürfen etwas dauern
graceful_timeout = 30
max_requests = 1000                           # Worker regelmässig erneuern
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
forwarded_allow_ips = "*"                     # Proxy kommt aus dem Docker-Netzwerk, nicht von 127.0.0.1
