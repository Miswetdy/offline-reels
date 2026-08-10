FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        chromium \
        chromium-sandbox \
        openbox \
        python3 \
        tini \
        websockify \
        x11vnc \
        xvfb \
        novnc \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10002 loginbrowser \
    && useradd --uid 10002 --gid loginbrowser --create-home --home-dir /home/loginbrowser loginbrowser \
    && install --directory --owner loginbrowser --group loginbrowser --mode 0700 /login-profiles

COPY --chown=loginbrowser:loginbrowser browser_service.py /usr/local/lib/login-browser/browser_service.py
COPY --chown=loginbrowser:loginbrowser entrypoint.sh /usr/local/bin/login-browser
RUN chmod 0555 /usr/local/bin/login-browser

USER loginbrowser
EXPOSE 8081
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/login-browser"]
