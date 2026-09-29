"""Tests for the security-key (FIDO2/WebAuthn) re-auth ceremony.

Apple disables every other second factor once security keys are enrolled
on an Apple ID: each 2FA endpoint answers with an ``fsaChallenge`` instead
of pushing a 6-digit code, so the code-entry paths can never complete.
These cover the split ceremony that replaces them -- the container obtains
and submits the challenge, while the signing happens natively on whichever
machine physically holds the key.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import base64
import json
import os
import re
import shutil
import struct
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests

import tests  # noqa: F401  — sets ENV_CONFIG_FILE_PATH via tests/__init__
from src import web
from tests.test_web import _csrf_post, _reset_pending_auth

# A realistically-shaped challenge: 32-byte challenge, two 48-byte handles,
# base64 with the standard alphabet and no padding, exactly as Apple emits.
_FSA = {
    "challenge": base64.b64encode(b"c" * 32).decode().rstrip("="),
    "rpId": "apple.com",
    "keyHandles": [
        base64.b64encode(b"h" * 48).decode().rstrip("="),
        base64.b64encode(b"k" * 48).decode().rstrip("="),
    ],
}




def _api(requires_2fa=True, challenge=None, accepts=True):
    api = MagicMock()
    api.requires_2fa = requires_2fa
    api.security_key_challenge = _FSA if challenge is None else challenge
    api.confirm_security_key.return_value = accepts
    api.session_data = {"scnt": "s", "session_id": "i"}
    api.auth_endpoint = "https://idmsa.apple.com/appleauth/auth"
    return api


class TestPackChallenge(unittest.TestCase):
    """``_pack_challenge`` — raw bytes with length prefixes, not
    base64-of-JSON, because the operator copies this inside a one-line
    shell command."""

    def _unpack(self, blob: str):
        raw = base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))
        (length,) = struct.unpack_from("!H", raw, 0)
        offset = 2
        challenge = raw[offset : offset + length]
        offset += length
        handles = []
        while offset < len(raw):
            (size,) = struct.unpack_from("!H", raw, offset)
            offset += 2
            handles.append(raw[offset : offset + size])
            offset += size
        return challenge, handles

    def test_round_trips_challenge_and_handles(self):
        challenge, handles = self._unpack(web._pack_challenge(_FSA))  # noqa: SLF001
        self.assertEqual(challenge, b"c" * 32)
        self.assertEqual(handles, [b"h" * 48, b"k" * 48])

    def test_is_shorter_than_base64_json(self):
        """The whole point of the packing — keep the copied command short."""
        packed = web._pack_challenge(_FSA)  # noqa: SLF001
        naive = base64.b64encode(json.dumps(_FSA).encode()).decode()
        self.assertLess(len(packed), len(naive))

    def test_handles_unpadded_standard_alphabet(self):
        """Apple emits ``+`` and ``/`` and omits padding; decoding must
        cope with both rather than assuming urlsafe input."""
        fsa = dict(
            _FSA,
            challenge=base64.b64encode(b"\xfb\xff" * 16).decode().rstrip("="),
        )
        challenge, _ = self._unpack(web._pack_challenge(fsa))  # noqa: SLF001
        self.assertEqual(challenge, b"\xfb\xff" * 16)


class TestBuildSignerCommand(unittest.TestCase):
    """``_build_signer_command`` — one self-contained shell command."""

    def test_pipes_source_on_stdin_and_writes_nothing(self):
        command = web._build_signer_command("BLOB")  # noqa: SLF001
        self.assertIn("uv run", command)
        self.assertIn("BLOB", command)
        self.assertNotIn("cat >", command)
        self.assertNotIn("/tmp/icloud_sign.py", command)

    def test_embeds_the_signer_source(self):
        """Delivered inline so the machine holding the key needs no route
        back to the container."""
        command = web._build_signer_command("BLOB")  # noqa: SLF001
        self.assertIn("CtapHidDevice", command)
        self.assertIn("ICLOUDSIGN", command)

    def test_missing_signer_degrades_to_a_message(self):
        with patch("builtins.open", side_effect=OSError("not in image")):
            command = web._build_signer_command("BLOB")  # noqa: SLF001
        self.assertIn("missing", command)


class TestShortSignerCommand(unittest.TestCase):
    """One line pointing at the signer in the public repo, at the release
    tag this image was built from -- in place of a 5 KB paste."""

    def test_one_line_pinned_to_the_release_tag(self):
        with patch.dict(os.environ, {"APP_VERSION": "1.29.0"}):
            command = web._build_short_signer_command("BLOB")  # noqa: SLF001
        self.assertEqual(
            command,
            "uv run --quiet https://raw.githubusercontent.com/mandarons/icloud-docker/v1.29.0/src/icloud_sign.py BLOB",
        )
        self.assertNotIn("\n", command)

    def test_a_build_that_is_not_a_release_gets_no_short_form(self):
        """dev and PR builds have no tag to point at, so the offline form
        stands alone."""
        for value in ("", "dev", "pr-123", "1.29", "v1.29.0"):
            with self.subTest(value=value), patch.dict(os.environ, {"APP_VERSION": value}):
                self.assertIsNone(web._build_short_signer_command("BLOB"))  # noqa: SLF001

    def test_offline_form_needs_no_separate_dependency_flag(self):
        """The signer declares fido2 inline (PEP 723), so both forms resolve
        it without --with."""
        command = web._build_signer_command("BLOB")  # noqa: SLF001
        self.assertIn("# /// script", command)
        self.assertIn('dependencies = ["fido2"]', command)


class TestAuthMethodHelpers(unittest.TestCase):
    """``_record_auth_method`` / ``_lookup_auth_method`` — bookkeeping that
    must never break the auth flow it annotates."""

    def test_record_delegates_to_web_signals(self):
        with patch("src.web_signals.record_auth_method") as recorder:
            web._record_auth_method("a@icloud.com", "security_key")  # noqa: SLF001
        recorder.assert_called_once_with(
            username="a@icloud.com",
            method="security_key",
        )

    def test_record_swallows_storage_failure(self):
        with patch(
            "src.web_signals.record_auth_method",
            side_effect=OSError("read-only"),
        ):
            web._record_auth_method("a@icloud.com", "security_key")  # noqa: SLF001

    def test_lookup_returns_none_without_username(self):
        self.assertIsNone(web._lookup_auth_method({}))  # noqa: SLF001
        self.assertIsNone(web._lookup_auth_method(None))  # noqa: SLF001

    def test_lookup_returns_recorded_method(self):
        with patch("src.web_signals.get_auth_method", return_value="security_key"):
            self.assertEqual(
                web._lookup_auth_method({"username": "a@icloud.com"}),  # noqa: SLF001
                "security_key",
            )

    def test_lookup_swallows_read_failure(self):
        with patch(
            "src.web_signals.get_auth_method",
            side_effect=RuntimeError("corrupt"),
        ):
            lookup = web._lookup_auth_method  # noqa: SLF001
            self.assertIsNone(lookup({"username": "a"}))


class TestSecurityKeyGet(unittest.TestCase):
    """``GET /auth/security-key`` — obtain Apple's challenge and render it."""

    def setUp(self):
        _reset_pending_auth()

    def tearDown(self):
        _reset_pending_auth()

    def _client(self):
        return web.create_app(testing=True).test_client()

    def test_plain_load_never_contacts_apple(self):
        """A reload or a browser prefetch must not spend a sign-in against
        Apple's rate limit, so the GET signs in for nobody."""
        with patch("icloudpy.ICloudPyService") as service:
            response = self._client().get("/auth/security-key")
        service.assert_not_called()
        self.assertEqual(response.status_code, 302)

    def test_400_without_username(self):
        with patch.object(web, "_load_current_config", return_value={"app": {}}):
            response = _csrf_post(self._client(), "/auth/security-key/start")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"No app.credentials.username", response.data)

    def test_400_when_config_is_malformed(self):
        """A hand-mangled config whose credentials block isn't a mapping
        raises inside the parser; treat it as "no username" rather than
        letting it 500. Only the handler's own lookup raises -- the status
        payload rendered afterwards still needs a working parser."""
        real = web.config_parser.get_username
        calls = {"n": 0}

        def _flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                message = "not a mapping"
                raise TypeError(message)
            return real(*args, **kwargs)

        with patch.object(web.config_parser, "get_username", side_effect=_flaky):
            response = _csrf_post(self._client(), "/auth/security-key/start")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"No app.credentials.username", response.data)

    def test_400_without_keyring_password(self):
        with patch("icloudpy.utils.get_password_from_keyring", return_value=None):
            response = _csrf_post(self._client(), "/auth/security-key/start")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"No password in keyring", response.data)

    def test_500_when_keyring_raises(self):
        with patch(
            "icloudpy.utils.get_password_from_keyring",
            side_effect=RuntimeError("keyring boom"),
        ):
            response = _csrf_post(self._client(), "/auth/security-key/start")
        self.assertEqual(response.status_code, 500)

    def test_400_when_signin_raises(self):
        with (
            patch("icloudpy.utils.get_password_from_keyring", return_value="pw"),
            patch("icloudpy.ICloudPyService", side_effect=RuntimeError("ctor")),
        ):
            response = _csrf_post(self._client(), "/auth/security-key/start")
        self.assertEqual(response.status_code, 400)

    def test_redirects_when_session_already_trusted(self):
        with (
            patch("icloudpy.utils.get_password_from_keyring", return_value="pw"),
            patch("icloudpy.ICloudPyService", return_value=_api(requires_2fa=False)),
            patch.object(web, "_wake_sync_loop") as woke,
        ):
            response = _csrf_post(self._client(), "/auth/security-key/start")
        self.assertEqual(response.status_code, 302)
        woke.assert_called_once_with()

    def test_400_when_apple_offers_no_challenge(self):
        """A code-based account landing here should be sent back to the
        form rather than shown an impossible ceremony."""
        with (
            patch("icloudpy.utils.get_password_from_keyring", return_value="pw"),
            patch("icloudpy.ICloudPyService", return_value=_api(challenge=False)),
        ):
            response = _csrf_post(self._client(), "/auth/security-key/start")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"did not offer a security-key challenge", response.data)

    def test_renders_ceremony_and_stashes_session(self):
        api = _api()
        with (
            patch("icloudpy.utils.get_password_from_keyring", return_value="pw"),
            patch("icloudpy.ICloudPyService", return_value=api),
            patch.object(web, "_record_auth_method") as recorder,
        ):
            response = _csrf_post(self._client(), "/auth/security-key/start")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"uv run", response.data)
        recorder.assert_called_once()
        with web._AUTH_LOCK:  # noqa: SLF001
            self.assertIs(web._PENDING_AUTH.get("api"), api)  # noqa: SLF001


class TestSecurityKeyReuse(unittest.TestCase):
    """A pending challenge is re-rendered rather than replaced.

    Every fresh sign-in invalidates a command the user may already have
    copied, pushes an Apple prompt at their devices, and moves the account
    closer to being throttled."""

    def setUp(self):
        _reset_pending_auth()

    def tearDown(self):
        _reset_pending_auth()

    def _client(self):
        return web.create_app(testing=True).test_client()

    def test_reuses_pending_challenge_without_signing_in(self):
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH.update(  # noqa: SLF001
                {
                    "api": _api(),
                    "username": "a@icloud.com",
                    "password": "pw",
                    "stashed_at": __import__("time").monotonic(),
                    "fsa_challenge": _FSA,
                },
            )
        with patch("icloudpy.ICloudPyService") as service:
            response = self._client().get("/auth/security-key")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"uv run", response.data)
        service.assert_not_called()

    def test_start_also_reuses_rather_than_signing_in_again(self):
        """Pressing the button twice must not spend a second sign-in."""
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH.update(  # noqa: SLF001
                {
                    "api": _api(),
                    "username": "a@icloud.com",
                    "password": "pw",
                    "stashed_at": __import__("time").monotonic(),
                    "fsa_challenge": _FSA,
                },
            )
        with patch("icloudpy.ICloudPyService") as service:
            response = _csrf_post(self._client(), "/auth/security-key/start")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"uv run", response.data)
        service.assert_not_called()


class TestChallengeMismatch(unittest.TestCase):
    """A signature for a superseded challenge must be named as such.

    Substituting the pending challenge would produce an assertion whose
    clientData disagrees with its challenge field, which Apple rejects with
    an opaque 409 -- the user would have no idea their page was stale."""

    def setUp(self):
        _reset_pending_auth()

    def tearDown(self):
        _reset_pending_auth()

    def _client(self):
        return web.create_app(testing=True).test_client()

    def test_mismatched_challenge_is_reported_not_masked(self):
        api = _api()
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH.update(  # noqa: SLF001
                {
                    "api": api,
                    "username": "a@icloud.com",
                    "password": "pw",
                    "stashed_at": __import__("time").monotonic(),
                    "fsa_challenge": _FSA,
                },
            )
        stale = base64.b64encode(
            json.dumps({"challenge": base64.b64encode(b"z" * 32).decode()}).encode(),
        ).decode()
        response = _csrf_post(self._client(), "/auth/security-key", {"assertion": stale})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"older challenge", response.data)
        api.session.post.assert_not_called()

    def test_padding_difference_is_not_a_mismatch(self):
        """The signer re-encodes with padding Apple did not send; that is
        the same challenge, not a stale one."""
        self.assertTrue(
            web._same_challenge(_FSA["challenge"] + "=", _FSA["challenge"]),  # noqa: SLF001
        )

    def test_undecodable_challenge_is_a_mismatch(self):
        self.assertFalse(web._same_challenge("!!!not base64", _FSA["challenge"]))  # noqa: SLF001


class TestSecurityKeyPost(unittest.TestCase):
    """``POST /auth/security-key`` — submit the signed assertion.

    The assertion is bound to the ``scnt``/session id of the stashed
    session, which is why the signer never needs the password and never
    talks to Apple itself."""

    def setUp(self):
        _reset_pending_auth()

    def tearDown(self):
        _reset_pending_auth()

    def _client(self):
        return web.create_app(testing=True).test_client()

    def _assertion(self, challenge=None):
        """Signer output. Defaults to the pending challenge, re-encoded with
        padding the way the signer actually emits it."""
        payload = {
            "credentialID": "x",
            "challenge": challenge or (_FSA["challenge"] + "="),
        }
        return base64.b64encode(json.dumps(payload).encode()).decode()

    def _stash(self, api):
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH.update(  # noqa: SLF001
                {
                    "api": api,
                    "username": "a@icloud.com",
                    "password": "pw",
                    "stashed_at": __import__("time").monotonic(),
                    "fsa_challenge": _FSA,
                },
            )

    def test_requires_csrf(self):
        response = self._client().post("/auth/security-key", data={"assertion": "x"})
        self.assertIn(response.status_code, (400, 403))

    def test_400_on_empty_assertion(self):
        response = _csrf_post(self._client(), "/auth/security-key", {"assertion": " "})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Paste the signer output", response.data)

    def test_400_on_unparseable_assertion(self):
        response = _csrf_post(
            self._client(),
            "/auth/security-key",
            {"assertion": "not-base64!!"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"does not look like signer output", response.data)

    def test_400_on_json_that_is_not_signer_output(self):
        """Valid base64 of valid JSON can still be the wrong thing -- an
        empty list, or a list of strings. It gets the same answer as
        garbage, not a 500."""
        self._stash(_api())
        for payload in ([], ["x"]):
            with self.subTest(payload=payload):
                blob = base64.b64encode(json.dumps(payload).encode()).decode()
                response = _csrf_post(self._client(), "/auth/security-key", {"assertion": blob})
                self.assertEqual(response.status_code, 400)
                self.assertIn(b"does not look like signer output", response.data)

    def test_400_when_challenge_expired(self):
        """The stashed Apple session is gone — a stale signature cannot be
        submitted against a session that no longer exists."""
        response = _csrf_post(
            self._client(),
            "/auth/security-key",
            {"assertion": self._assertion()},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Challenge expired", response.data)


    def test_400_when_apple_rejects_the_assertion(self):
        api = _api(accepts=False)
        self._stash(api)
        response = _csrf_post(
            self._client(),
            "/auth/security-key",
            {"assertion": self._assertion()},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"refused that signature", response.data)

    def test_success_trusts_persists_and_signals_resume(self):
        api = _api()
        self._stash(api)
        with (
            patch.object(web, "_session_authenticates", return_value=True),
            patch("icloudpy.utils.store_password_in_keyring") as keyring,
            patch.object(web, "_wake_sync_loop") as woke,
        ):
            response = _csrf_post(
                self._client(),
                "/auth/security-key",
                {"assertion": self._assertion()},
            )
        self.assertEqual(response.status_code, 302)
        # Resuming immediately is the point: the sync loop deliberately
        # stops retrying on a timer for these accounts.
        keyring.assert_called_once()
        api.confirm_security_key.assert_called_once()
        # Without the wake the loop sleeps out the rest of its retry interval
        # and the dashboard keeps saying "sync is stopped" after a success.
        woke.assert_called_once_with()

    def test_success_survives_trust_and_keyring_failures(self):
        """Apple already accepted the assertion; bookkeeping failures after
        that must not turn a successful sign-in into an error."""
        api = _api()
        self._stash(api)
        with (
            patch.object(web, "_session_authenticates", return_value=True),
            patch(
                "icloudpy.utils.store_password_in_keyring",
                side_effect=RuntimeError("keyring boom"),
            ),
        ):
            response = _csrf_post(
                self._client(),
                "/auth/security-key",
                {"assertion": self._assertion()},
            )
        self.assertEqual(response.status_code, 302)


    def test_400_when_the_submit_raises(self):
        """A transport fault reaches the operator rather than a traceback."""
        api = _api()
        api.confirm_security_key.side_effect = RuntimeError("network")
        self._stash(api)
        response = _csrf_post(
            self._client(),
            "/auth/security-key",
            {"assertion": self._assertion()},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Assertion submit failed", response.data)

    def test_pending_is_always_cleared(self):
        """Every exit path clears the stash so a password never lingers in
        process memory after the ceremony ends."""
        api = _api()
        self._stash(api)
        with (
            patch("icloudpy.utils.store_password_in_keyring"),
        ):
            _csrf_post(
                self._client(),
                "/auth/security-key",
                {"assertion": self._assertion()},
            )
        with web._AUTH_LOCK:  # noqa: SLF001
            self.assertEqual(web._PENDING_AUTH, {})  # noqa: SLF001


class TestAuthStateReflectsSyncLoop(unittest.TestCase):
    """``_detect_auth_state`` must not report health the sync loop is
    contradicting -- a green dashboard over a sync that stopped weeks ago
    is worse than no dashboard."""

    def test_reauth_needed_when_loop_reports_blocked(self):
        with (
            patch("icloudpy.utils.password_exists_in_keyring", return_value=True),
            patch("src.web_signals.get_auth_blocked", return_value={"blocked": True}),
        ):
            self.assertEqual(
                web._detect_auth_state(username="a@icloud.com"),  # noqa: SLF001
                "reauth_needed",
            )

    def test_ready_when_loop_reports_healthy(self):
        with (
            patch("icloudpy.utils.password_exists_in_keyring", return_value=True),
            patch("src.web_signals.get_auth_blocked", return_value={"blocked": False}),
        ):
            self.assertEqual(
                web._detect_auth_state(username="a@icloud.com"),  # noqa: SLF001
                "ready",
            )

    def test_setup_needed_still_wins_without_keyring(self):
        with patch("icloudpy.utils.password_exists_in_keyring", return_value=False):
            self.assertEqual(
                web._detect_auth_state(username="a@icloud.com"),  # noqa: SLF001
                "setup_needed",
            )


class TestSyncPublishesAuthState(unittest.TestCase):
    """``sync._publish_auth_blocked`` is advisory and must never raise."""

    def test_publishes_blocked(self):
        from src import sync

        with patch("src.web_signals.record_auth_blocked") as recorder:
            sync._publish_auth_blocked(True, reason="2fa_required")  # noqa: SLF001
        recorder.assert_called_once_with(blocked=True, reason="2fa_required")

    def test_swallows_failure(self):
        from src import sync

        with patch(
            "src.web_signals.record_auth_blocked",
            side_effect=OSError("read-only"),
        ):
            sync._publish_auth_blocked(False)  # noqa: SLF001


class TestCeremonyCookieIsolation(unittest.TestCase):
    """The ceremony signs in against its own empty cookie jar.

    icloudpy loads its jar with ignore_expires=True, so a dead session's
    cookies -- an expired X-APPLE-WEBAUTH-TOKEN among them -- are replayed
    alongside a fresh SRP handshake. Apple answers that contradiction with
    409 Conflict, which is what the assertion submit kept receiving."""

    def setUp(self):
        _reset_pending_auth()

    def tearDown(self):
        _reset_pending_auth()

    def _client(self):
        return web.create_app(testing=True).test_client()

    def test_signin_uses_a_private_empty_jar(self):
        api = _api()
        with (
            patch("icloudpy.utils.get_password_from_keyring", return_value="pw"),
            patch("icloudpy.ICloudPyService", return_value=api) as service,
            patch.object(web, "_record_auth_method"),
        ):
            _csrf_post(self._client(), "/auth/security-key/start")
        used = service.call_args.kwargs["cookie_directory"]
        self.assertNotEqual(used, web.DEFAULT_COOKIE_DIRECTORY)
        self.assertEqual(os.listdir(used), [])

    def test_failed_signin_leaves_no_directory_behind(self):
        with (
            patch("icloudpy.utils.get_password_from_keyring", return_value="pw"),
            patch("icloudpy.ICloudPyService", side_effect=RuntimeError("nope")),
            patch.object(web, "_ceremony_cookie_dir") as maker,
        ):
            maker.return_value = tempfile.mkdtemp()
            created = maker.return_value
            _csrf_post(self._client(), "/auth/security-key/start")
        self.assertFalse(os.path.exists(created))

    def test_success_publishes_the_ceremony_session(self):
        """The sync loop reads the real directory, so an accepted ceremony
        has to land there -- and only once Apple has accepted it."""
        api = _api()
        ceremony = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, ceremony, True)
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH.update(  # noqa: SLF001
                {
                    "api": api,
                    "username": "a@icloud.com",
                    "password": "pw",
                    "stashed_at": __import__("time").monotonic(),
                    "fsa_challenge": _FSA,
                    "cookie_dir": ceremony,
                },
            )
        assertion = base64.b64encode(
            json.dumps(
                {"credentialID": "x", "challenge": _FSA["challenge"] + "="},
            ).encode(),
        ).decode()
        with (
            patch.object(web, "_session_authenticates", return_value=True),
            patch("icloudpy.utils.store_password_in_keyring"),
            patch.object(web, "_publish_ceremony_session") as publish,
        ):
            response = _csrf_post(
                self._client(),
                "/auth/security-key",
                {"assertion": assertion},
            )
        self.assertEqual(response.status_code, 302)
        publish.assert_called_once_with(ceremony)

    def test_publish_copies_session_and_backs_up_the_previous(self):
        source = tempfile.mkdtemp()
        target = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, source, True)
        self.addCleanup(shutil.rmtree, target, True)
        with open(os.path.join(target, "userexamplecom"), "w") as fh:
            fh.write("old")
        with open(os.path.join(source, "userexamplecom"), "w") as fh:
            fh.write("new")
        with patch.object(web, "DEFAULT_COOKIE_DIRECTORY", target):
            web._publish_ceremony_session(source)  # noqa: SLF001
        with open(os.path.join(target, "userexamplecom")) as fh:
            self.assertEqual(fh.read(), "new")
        with open(os.path.join(target, "userexamplecom.bak")) as fh:
            self.assertEqual(fh.read(), "old")

    def test_publish_never_raises(self):
        with patch("os.listdir", side_effect=OSError("gone")):
            web._publish_ceremony_session("/nonexistent")  # noqa: SLF001

    def test_discard_tolerates_none_and_missing(self):
        web._discard_ceremony_dir(None)  # noqa: SLF001
        web._discard_ceremony_dir("/definitely/not/here")  # noqa: SLF001

    def test_cookie_dir_is_fresh_each_time(self):
        first = web._ceremony_cookie_dir()  # noqa: SLF001
        second = web._ceremony_cookie_dir()  # noqa: SLF001
        self.addCleanup(shutil.rmtree, first, True)
        self.addCleanup(shutil.rmtree, second, True)
        self.assertNotEqual(first, second)
        self.assertEqual(os.listdir(first), [])


class TestSigninThrottleHandling(unittest.TestCase):
    """Apple answers a rate-limited account with 409 on /signin/init, before
    any challenge exists. That is not a bad password, a bad key or a bad
    assertion, and retrying is what prolongs it -- so it gets its own
    message and its own status."""

    def setUp(self):
        _reset_pending_auth()

    def tearDown(self):
        _reset_pending_auth()

    def _client(self):
        return web.create_app(testing=True).test_client()

    def test_recognises_the_signin_rate_limit(self):
        error = Exception(
            "409 Client Error:  for url: "
            "https://idmsa.apple.com/appleauth/auth/signin/init",
        )
        self.assertTrue(web._is_signin_throttled(error))  # noqa: SLF001

    def test_does_not_mistake_other_failures_for_throttling(self):
        throttled = web._is_signin_throttled  # noqa: SLF001
        self.assertFalse(throttled(Exception("boom")))
        self.assertFalse(throttled(Exception("409 on /verify/security/key")))
        self.assertFalse(throttled(Exception("500 signin/init")))

    def test_start_reports_429_and_offers_a_retry(self):
        error = requests.exceptions.HTTPError(
            "409 Client Error:  for url: "
            "https://idmsa.apple.com/appleauth/auth/signin/init",
        )
        with (
            patch("icloudpy.utils.get_password_from_keyring", return_value="pw"),
            patch("icloudpy.ICloudPyService", side_effect=error),
        ):
            response = _csrf_post(self._client(), "/auth/security-key/start")
        self.assertEqual(response.status_code, 429)
        self.assertIn(b"rate-limiting", response.data)

    def test_start_requires_csrf(self):
        """The only path that spends a sign-in must not be triggerable by a
        cross-site form post."""
        response = self._client().post("/auth/security-key/start")
        self.assertIn(response.status_code, (400, 403))




class TestNoDeadInternalLinks(unittest.TestCase):
    """Every internal link a template offers must resolve.

    A renamed route left the dashboard pointing at a page that no longer
    existed, so the one action offered when sync is stopped led to a 404 --
    exactly when the operator is least able to guess the real URL."""

    def test_every_templated_link_has_a_route(self):
        import glob
        import os as _os

        app = web.create_app(testing=True)
        known = set()
        for rule in app.url_map.iter_rules():
            known.add(str(rule.rule))

        template_dir = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            "src",
            "templates",
        )
        offending = []
        for path in glob.glob(_os.path.join(template_dir, "*.html")):
            body = open(path, encoding="utf-8").read()
            offending.extend(
                f"{_os.path.basename(path)} -> {target}"
                for target in re.findall(r'(?:href|action)="(/[^"{]*)"', body)
                if target.rstrip("/") and target not in known
            )
        self.assertEqual(offending, [])


class TestCeremonyIsVerifiedNotAssumed(unittest.TestCase):
    """Apple accepting the assertion is not proof the sync loop can sign in.

    Reporting success on the submit alone is how a session that still
    wanted a second factor was announced as working."""

    def setUp(self):
        _reset_pending_auth()

    def tearDown(self):
        _reset_pending_auth()

    def _client(self):
        return web.create_app(testing=True).test_client()


    def test_accepted_but_unusable_is_reported_as_failure(self):
        api = _api()
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH.update(  # noqa: SLF001
                {
                    "api": api,
                    "username": "a@icloud.com",
                    "password": "pw",
                    "stashed_at": __import__("time").monotonic(),
                    "fsa_challenge": _FSA,
                },
            )
        assertion = base64.b64encode(
            json.dumps(
                {"credentialID": "x", "challenge": _FSA["challenge"] + "="},
            ).encode(),
        ).decode()
        with (
            patch.object(web, "_session_authenticates", return_value=False),
            patch("icloudpy.utils.store_password_in_keyring"),
        ):
            response = _csrf_post(
                self._client(),
                "/auth/security-key",
                {"assertion": assertion},
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"still asks for", response.data)


class TestSessionVerification(unittest.TestCase):
    """``_session_authenticates`` signs in the way the sync loop will.

    Apple accepting the assertion is not the same as the loop being able
    to authenticate, and reporting success on the submit alone once
    announced a session that still wanted a second factor."""

    def test_true_when_no_factor_is_wanted(self):
        with (
            patch("icloudpy.utils.get_password_from_keyring", return_value="pw"),
            patch("icloudpy.ICloudPyService", return_value=_api(requires_2fa=False)),
        ):
            self.assertTrue(web._session_authenticates("a@icloud.com"))  # noqa: SLF001

    def test_false_when_apple_still_wants_a_factor(self):
        with (
            patch("icloudpy.utils.get_password_from_keyring", return_value="pw"),
            patch("icloudpy.ICloudPyService", return_value=_api(requires_2fa=True)),
        ):
            self.assertFalse(web._session_authenticates("a@icloud.com"))  # noqa: SLF001

    def test_false_when_sign_in_raises(self):
        with (
            patch("icloudpy.utils.get_password_from_keyring", return_value="pw"),
            patch("icloudpy.ICloudPyService", side_effect=RuntimeError("nope")),
        ):
            self.assertFalse(web._session_authenticates("a@icloud.com"))  # noqa: SLF001

    def test_checks_the_directory_the_loop_reads(self):
        with (
            patch("icloudpy.utils.get_password_from_keyring", return_value="pw"),
            patch(
                "icloudpy.ICloudPyService",
                return_value=_api(requires_2fa=False),
            ) as svc,
        ):
            web._session_authenticates("a@icloud.com")  # noqa: SLF001
        self.assertEqual(
            svc.call_args.kwargs["cookie_directory"],
            web.DEFAULT_COOKIE_DIRECTORY,
        )


class TestAbandonedCeremonyLeavesNoCookies(unittest.TestCase):
    """A ceremony's private cookie jar holds its Apple session cookies. It
    was removed only on a submit, so a ceremony that expired, was reset, or
    was answered with a stale signature left them in the temp dir."""

    def setUp(self):
        _reset_pending_auth()
        self.jar = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.jar, True)

    def tearDown(self):
        _reset_pending_auth()

    def _client(self):
        return web.create_app(testing=True).test_client()

    def _stash(self, stashed_at=None):
        import time

        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH.update(  # noqa: SLF001
                {
                    "api": _api(),
                    "username": "a@icloud.com",
                    "password": "pw",
                    "stashed_at": time.monotonic() if stashed_at is None else stashed_at,
                    "fsa_challenge": _FSA,
                    "cookie_dir": self.jar,
                },
            )

    def test_reset_removes_the_jar(self):
        self._stash()
        _csrf_post(self._client(), "/auth/reset")
        self.assertFalse(os.path.exists(self.jar))

    def test_expiry_removes_the_jar(self):
        import time

        self._stash(stashed_at=time.monotonic() - web._PENDING_AUTH_TTL_SECONDS - 1)  # noqa: SLF001
        with web._AUTH_LOCK:  # noqa: SLF001
            web._expire_stale_pending_auth_unlocked()  # noqa: SLF001
        self.assertFalse(os.path.exists(self.jar))
        self.assertEqual(web._PENDING_AUTH, {})  # noqa: SLF001

    def test_a_stale_signature_removes_the_jar(self):
        self._stash()
        stale = base64.b64encode(
            json.dumps({"challenge": base64.b64encode(b"z" * 32).decode()}).encode(),
        ).decode()
        response = _csrf_post(self._client(), "/auth/security-key", {"assertion": stale})
        self.assertIn(b"older challenge", response.data)
        self.assertFalse(os.path.exists(self.jar))
