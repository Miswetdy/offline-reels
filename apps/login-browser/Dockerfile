FROM debian:bookworm-slim

ARG LOGIN_BROWSER_UID=10002

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOGIN_BROWSER_CHROMIUM_EXECUTABLE=/opt/chrome-for-testing/chrome-linux64/chrome

RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        chromium \
        chromium-sandbox \
        curl \
        openbox \
        python3 \
        tini \
        websockify \
        x11vnc \
        xvfb \
        novnc \
        unzip \
        && rm -rf /var/lib/apt/lists/* \
    && curl --fail --location --retry 3 --output /tmp/chrome-for-testing.zip \
        https://cdn.playwright.dev/builds/cft/151.0.7922.34/linux64/chrome-linux64.zip \
    && unzip -q /tmp/chrome-for-testing.zip -d /opt/chrome-for-testing \
    && rm /tmp/chrome-for-testing.zip \
    && groupadd --gid "${LOGIN_BROWSER_UID}" loginbrowser \
    && useradd --uid "${LOGIN_BROWSER_UID}" --gid loginbrowser --create-home --home-dir /home/loginbrowser loginbrowser \
    && install --directory --owner loginbrowser --group loginbrowser --mode 0700 /login-profiles

COPY --chown=loginbrowser:loginbrowser browser_service.py /usr/local/lib/login-browser/browser_service.py
COPY --chown=loginbrowser:loginbrowser entrypoint.sh /usr/local/bin/login-browser
RUN chmod 0555 /usr/local/bin/login-browser

USER loginbrowser
EXPOSE 8081
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/login-browser"]
