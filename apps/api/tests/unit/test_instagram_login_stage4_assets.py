from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_stage4_compose_exposes_only_tailscale_https_edge_and_no_collector_pipeline() -> None:
    compose = (ROOT / "deploy" / "docker-compose.instagram-login-stage4.yml").read_text(
        encoding="utf-8"
    )
    assert "tailscale-funnel:" in compose
    assert "TAILSCALE_AUTHKEY" in compose
    assert "tailscale_egress" in compose
    assert "cap_drop: [ALL]" in compose
    assert "ports:" not in compose
    assert "login-browser:" in compose
    browser = compose.split("  login-browser:", 1)[1].split("  login-gateway:", 1)[0]
    assert "seccomp=unconfined" in browser
    assert "no-new-privileges:true" not in browser
    assert "SYS_ADMIN" not in browser
    assert "ports:" not in browser
    assert "seccomp=./seccomp/" not in compose
    assert compose.count("seccomp=unconfined") == 1
    assert "\n  minio:" not in compose.lower()
    assert "\n  collector:" not in compose.lower()
    assert "\n  normalizer:" not in compose.lower()
    gateway = compose.split("  login-gateway:", 1)[1].split("  profile-reset:", 1)[0]
    assert "stage4_login_profile" not in gateway
    reset = compose.split("  profile-reset:", 1)[1].split("  tailscale-funnel:", 1)[0]
    assert 'user: "10002:10002"' in reset
    assert "stage4_login_profile" in reset


def test_login_browser_is_non_root_and_keeps_cdp_and_vnc_loopback_only() -> None:
    dockerfile = (ROOT / "apps" / "login-browser" / "Dockerfile").read_text(encoding="utf-8")
    service = (ROOT / "apps" / "login-browser" / "browser_service.py").read_text(encoding="utf-8")
    assert "USER loginbrowser" in dockerfile
    assert "chromium-sandbox" in dockerfile
    assert (
        "LOGIN_BROWSER_CHROMIUM_EXECUTABLE=/opt/chrome-for-testing/chrome-linux64/chrome"
        in dockerfile
    )
    assert "151.0.7922.34/linux64/chrome-linux64.zip" in dockerfile
    assert "--remote-debugging-address=127.0.0.1" in service
    assert '"0.0.0.0:6080"' in service
    assert '"-localhost"' in service
    assert "430x800x24" in service
    assert "--window-size=430,800" in service
    assert "--window-position=0,0" in service
    assert "--force-device-scale-factor=0.9" in service
    assert "CHROMIUM_EXECUTABLE" in service
    assert 'Browser.close' in service
    assert "--disable-setuid-sandbox" not in service
    assert '"--no-sandbox"' not in service
    assert "Mobile Safari/537.36" in service
    assert '"--kiosk", "about:blank"' in service
    assert '"SingletonLock", "SingletonSocket", "SingletonCookie"' in service
    assert 'lock_path = PROFILE / ".collector.lock"' in service
    assert "fcntl.LOCK_EX | fcntl.LOCK_NB" in service
    assert "LOGIN_BROWSER_EXPECTED_APPARMOR_PROFILE" in service
    assert "password" not in service.lower().replace("input[name=password]", "")
    # Instagram can retain a valid session behind its one-tap account page.
    # Keep that page visible for a human decision instead of treating it as a
    # completed profile check.
    assert "accounts\\\\/(?:login|onetap)" in service


def test_stage4_has_explicit_profile_cleanup_and_no_windows_profile_reference() -> None:
    scripts = (ROOT / "scripts" / "cleanup-instagram-login-stage4.ps1").read_text(
        encoding="utf-8"
    ) + (ROOT / "scripts" / "prepare-instagram-login-stage4.ps1").read_text(encoding="utf-8")
    assert "offline-reels-instagram-login-stage4" in scripts
    assert "offline-reels-collector-smoke" not in scripts
    assert "LOCALAPPDATA" not in scripts
    reset = (ROOT / "scripts" / "reset-instagram-login-stage4-profile.ps1").read_text(
        encoding="utf-8"
    )
    assert "ConfirmDeleteProfile" in reset
    assert "profile-reset" in reset
