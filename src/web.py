"""Web UI for icloud-docker.

Goal — give the user a single page they can hit from any device to:
  1) (primary) authenticate / re-authenticate Apple ID + 2FA;
  2) (secondary) confirm config paths, mount markers, and last-sync status;
  3) (tertiary) tail the recent log lines.

The web server runs in a daemon thread spawned from ``main.py`` alongside
the existing ``sync.sync()`` loop. The two share state through the
filesystem (keyring, session cookies, log file). No new persistence layer.

Designed for **LAN- or proxy-trusted** exposure. There is no built-in
login on this UI — put Cloudflare Access / Authelia / Tailscale in front
when exposing publicly. Opt-out via ``app.web_ui.enabled: false`` in
``config.yaml``.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import threading

from flask import Flask, jsonify

from src import (
    DEFAULT_CONFIG_FILE_PATH,
    ENV_CONFIG_FILE_PATH_KEY,
    get_logger,
)

LOGGER = get_logger()


def _current_config_path() -> str:
    """Resolve the active config path the same way sync.py does."""
    return os.environ.get(ENV_CONFIG_FILE_PATH_KEY, DEFAULT_CONFIG_FILE_PATH)


def create_app(testing: bool = False) -> Flask:
    """Construct the Flask app.

    Splitting this out keeps ``tests/`` able to build the app under
    ``TESTING=True`` without spawning a thread.
    """
    app = Flask(__name__)
    app.config["TESTING"] = testing

    @app.route("/api/health")
    def health():
        """Tiny endpoint for external monitors.

        - 200 ``{"state": "ok"}`` when the config file is readable.
        - 503 ``{"state": "config_missing"}`` when it isn't.

        ``2fa_required`` is *not* a 503 — Apple sessions expire all the time
        and the dashboard must stay reachable so the user can re-auth.
        """
        if not os.path.isfile(_current_config_path()):
            return jsonify({"state": "config_missing"}), 503
        return jsonify({"state": "ok"})

    return app


def start_in_thread(host: str = "0.0.0.0", port: int = 8080) -> threading.Thread:  # noqa: S104
    """Launch the Flask app on a daemon thread.

    The main sync loop owns the process; the web thread dies when the
    parent process exits.
    """
    app = create_app()

    def _serve():
        try:
            # Werkzeug dev server — single user, behind a proxy.
            # Zero extra runtime deps (no gunicorn).
            app.run(host=host, port=port, debug=False, use_reloader=False)
        except OSError as e:
            LOGGER.error(f"Web UI failed to bind {host}:{port} — {e!s}")

    thread = threading.Thread(target=_serve, name="icloud-web-ui", daemon=True)
    thread.start()
    LOGGER.info(f"Web UI listening on http://{host}:{port}/")
    return thread
