# LernReaktor als Container – für Server, auf denen bereits ein Reverse-Proxy
# (z. B. Caddy) läuft und Dienste über ein Docker-Netzwerk anspricht, statt des
# bare-metal-Setups aus deploy/install.sh.
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
COPY deploy/requirements-server.txt deploy/requirements-server.txt
RUN pip install --no-cache-dir -r deploy/requirements-server.txt

COPY . .

RUN useradd --system --home /app --shell /usr/sbin/nologin lernreaktor \
    && mkdir -p /data \
    && chown -R lernreaktor:lernreaktor /app /data
USER lernreaktor

ENV LERNREAKTOR_INSTANCE=/data
EXPOSE 8000
CMD ["gunicorn", "-c", "deploy/docker/gunicorn.conf.py", "run:app"]
