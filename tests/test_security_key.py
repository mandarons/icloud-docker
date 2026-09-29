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
import struct
import unittest
from unittest.mock import MagicMock, patch

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
