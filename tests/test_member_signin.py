"""Tests for signing a household member in from a browser at the dashboard."""

import os
import re
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
from icloudpy import exceptions

import tests  # noqa: F401 - sets ENV_CONFIG_FILE_PATH via tests/__init__
from src import accounts, member_signin, web
from tests.test_web import _csrf_post

MAIN = "main@example.com"
MEMBER = "member@example.com"


def _config(**web_ui):
    return {
        "app": {"credentials": {"username": MAIN}, "web_ui": web_ui},
        "accounts": [{"id": "member", "username": MEMBER}],
    }


def _app():
    """A bare app with only the sign-in pages, for rendering them alone."""
    app = Flask(__name__, template_folder=os.path.join(os.path.dirname(member_signin.__file__), "templates"))
    member_signin.configure_session(app)
    app.register_blueprint(member_signin.blueprint)
    return app


class _ConfigDir(unittest.TestCase):
    """Each test gets its own config folder and a clean in-memory state."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        env = patch.dict(os.environ, {"ICLOUD_DOCKER_CONFIG_DIR": self.dir})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(shutil.rmtree, self.dir, True)
        member_signin._PENDING.clear()  # noqa: SLF001
        member_signin._FAILURES.clear()  # noqa: SLF001
        member_signin._FINISHED.clear()  # noqa: SLF001


class TestAccounts(_ConfigDir):
    def test_reads_valid_entries(self):
        self.assertEqual(accounts.get_accounts(_config()), [accounts.Account("member", MEMBER)])

    def test_no_accounts_section(self):
        self.assertEqual(accounts.get_accounts({"app": {}}), [])
        self.assertEqual(accounts.get_accounts(None), [])

    def test_skips_bad_entries(self):
        config = {
            "app": {"credentials": {"username": MAIN}},
            "accounts": [
                "member",
                {"id": "Bad Id", "username": MEMBER},
                {"id": "ok", "username": "no-at-sign"},
                {"id": "self", "username": MAIN.upper()},
                {"id": "member", "username": MEMBER},
                {"id": "member", "username": "other@example.com"},
            ],
        }
        with self.assertLogs(accounts.LOGGER, level="WARNING") as logs:
            found = accounts.get_accounts(config)
        self.assertEqual([a.id for a in found], ["member"])
        self.assertEqual(len(logs.output), 5)

    def test_accounts_must_be_a_list(self):
        with self.assertLogs(accounts.LOGGER, level="WARNING"):
            self.assertEqual(accounts.get_accounts({"accounts": {"id": "x"}}), [])

    def test_get_account(self):
        self.assertEqual(accounts.get_account(_config(), "member").username, MEMBER)
        self.assertIsNone(accounts.get_account(_config(), "nobody"))

    def test_session_saved(self):
        self.assertFalse(accounts.session_saved("member"))
        os.makedirs(accounts.cookie_directory("member"))
        self.assertFalse(accounts.session_saved("member"))
        with open(os.path.join(accounts.cookie_directory("member"), "membersession"), "w") as f:
            f.write("x")
        self.assertTrue(accounts.session_saved("member"))
        self.assertTrue(accounts.cookie_directory("member").startswith(self.dir))

    def test_username_is_optional(self):
        config = {"app": {"credentials": {"username": MAIN}}, "accounts": [{"id": "member"}]}
        self.assertEqual(accounts.get_accounts(config), [accounts.Account("member", None)])

    def test_pinned_username_fills_in(self):
        accounts.pin_username("member", MEMBER)
        config = {"app": {"credentials": {"username": MAIN}}, "accounts": [{"id": "member"}]}
        self.assertEqual(accounts.get_account(config, "member").username, MEMBER)
        self.assertEqual(accounts.pinned_username("member"), MEMBER)

    def test_unreadable_pin_is_ignored(self):
        os.makedirs(accounts.account_directory("member"))
        with open(os.path.join(accounts.account_directory("member"), "account.json"), "w") as f:
            f.write("[]")
        self.assertIsNone(accounts.pinned_username("member"))

    def test_forget_drops_pin_and_session(self):
        accounts.pin_username("member", MEMBER)
        os.makedirs(accounts.cookie_directory("member"))
        accounts.forget("member")
        self.assertFalse(os.path.exists(accounts.account_directory("member")))
        accounts.forget("member")


class FakeService:
    """Stands in for ``ICloudPyService``; records what the page did."""

    instances: list[FakeService] = []
    requires_2fa = True
    raise_on_init: Exception | None = None
    accept_code = True

    def __init__(self, apple_id, password, cookie_directory):
        # icloudpy writes its session files before Apple has said yes.
        with open(os.path.join(cookie_directory, "member.session"), "w", encoding="utf-8") as f:
            f.write("{}")
        if FakeService.raise_on_init:
            raise FakeService.raise_on_init
        self.apple_id, self.password, self.cookie_directory = (
            apple_id,
            password,
            cookie_directory,
        )
        self.pushed = self.trusted = False
        FakeService.instances.append(self)

    def trigger_2fa_push_notification(self):
        self.pushed = True

    def validate_2fa_code(self, code):
        self.code = code
        return FakeService.accept_code

    def trust_session(self):
        self.trusted = True


class TestSignInPages(_ConfigDir):
    def setUp(self):
        super().setUp()
        FakeService.instances = []
        FakeService.requires_2fa = True
        FakeService.raise_on_init = None
        FakeService.accept_code = True
        for patcher in (
            patch.object(web, "_load_current_config", lambda: _config()),
            patch("icloudpy.ICloudPyService", FakeService),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = web.create_app(testing=True).test_client()

    def _open(self):
        response = _csrf_post(self.client, "/household/member/sign-in")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/sign-in")
        return self._csrf()

    def _csrf(self):
        html = self.client.get("/sign-in").get_data(as_text=True)
        match = re.search(r'name="csrf_token" value="([^"]+)"', html)
        return match.group(1) if match else ""

    def test_full_sign_in(self):
        csrf = self._open()
        response = self.client.post("/sign-in/password", data={"csrf_token": csrf, "password": "pw"})
        self.assertEqual(response.status_code, 302)
        api = FakeService.instances[0]
        self.assertEqual(api.apple_id, MEMBER)
        self.assertTrue(api.cookie_directory.startswith(accounts.cookie_directory("member")))
        self.assertTrue(api.pushed)
        # Waiting for the code is not signed in.
        self.assertFalse(accounts.session_saved("member"))
        self.assertIn("6-digit code", self.client.get("/sign-in").get_data(as_text=True))

        response = self.client.post("/sign-in/code", data={"csrf_token": csrf, "code": "123 456"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(api.code, "123456")
        self.assertTrue(api.trusted)
        self.assertIn("You're signed in", self.client.get("/sign-in").get_data(as_text=True))
        self.assertNotIn("member", member_signin._PENDING)  # noqa: SLF001
        self.assertTrue(accounts.session_saved("member"))
        self.assertFalse(os.path.exists(member_signin._staging("member")))  # noqa: SLF001

    def test_no_second_factor_needed(self):
        FakeService.requires_2fa = False
        csrf = self._open()
        self.client.post("/sign-in/password", data={"csrf_token": csrf, "password": "pw"})
        self.assertIn("You're signed in", self.client.get("/sign-in").get_data(as_text=True))

    def test_post_needs_the_session_csrf(self):
        self._open()
        response = self.client.post("/sign-in/password", data={"csrf_token": "wrong", "password": "pw"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(FakeService.instances, [])
        self.assertEqual(self.client.post("/sign-in/code", data={"code": "123456"}).status_code, 403)

    def test_empty_password(self):
        csrf = self._open()
        response = self.client.post("/sign-in/password", data={"csrf_token": csrf, "password": ""})
        self.assertEqual(response.status_code, 400)

    def test_three_rejected_passwords_lock_the_page(self):
        FakeService.raise_on_init = exceptions.ICloudPyFailedLoginException("no", None)
        csrf = self._open()
        for _ in range(3):
            response = self.client.post("/sign-in/password", data={"csrf_token": csrf, "password": "bad"})
            self.assertEqual(response.status_code, 400)
            self.assertIn("accept that", response.get_data(as_text=True))
            self.assertIn("https://iforgot.apple.com", response.get_data(as_text=True))
            # A refused sign-in leaves nothing that reads as signed in.
            self.assertFalse(accounts.session_saved("member"))
            self.assertFalse(os.path.exists(member_signin._staging("member")))  # noqa: SLF001
        FakeService.raise_on_init = None
        response = self.client.post("/sign-in/password", data={"csrf_token": csrf, "password": "good"})
        self.assertEqual(response.status_code, 429)
        self.assertIn("https://www.icloud.com", response.get_data(as_text=True))
        self.assertEqual(FakeService.instances, [])

    def test_failures_age_out(self):
        member_signin._FAILURES["member"] = [0.0, 0.0, 0.0]  # noqa: SLF001
        self.assertFalse(member_signin._locked_out("member"))  # noqa: SLF001

    def test_apple_unreachable(self):
        FakeService.raise_on_init = ConnectionError("down")
        csrf = self._open()
        response = self.client.post("/sign-in/password", data={"csrf_token": csrf, "password": "pw"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(member_signin._FAILURES.get("member", []), [])  # noqa: SLF001

    def test_apple_rejecting_the_apple_id_reads_as_a_refusal(self):
        import requests

        error = requests.HTTPError("400 Client Error")
        error.response = requests.Response()
        error.response.status_code = 400
        FakeService.raise_on_init = error
        csrf = self._open()
        response = self.client.post("/sign-in/password", data={"csrf_token": csrf, "password": "pw"})
        self.assertEqual(response.status_code, 400)
        body = response.get_data(as_text=True)
        self.assertIn("didn&#39;t accept", body)
        self.assertIn("iforgot.apple.com", body)
        self.assertEqual(member_signin._FAILURES.get("member", []), [])  # noqa: SLF001

    def test_a_second_tap_on_the_code_lands_on_done(self):
        """Two submits of the same code: Apple checks once, both end on the done page."""
        import threading

        csrf = self._open()
        self.client.post("/sign-in/password", data={"csrf_token": csrf, "password": "pw"})
        api = FakeService.instances[0]
        entered, release = threading.Event(), threading.Event()
        checks = []

        def slow_check(code):
            checks.append(code)
            entered.set()
            release.wait(5)
            return True

        api.validate_2fa_code = slow_check
        cookie = self.client.get_cookie("sign_in_session").value
        second = {}

        def tap_again():
            other = web.create_app(testing=True).test_client()
            other.set_cookie("sign_in_session", cookie)
            second["response"] = other.post("/sign-in/code", data={"csrf_token": csrf, "code": "123456"})

        first = threading.Thread(
            target=lambda: self.client.post("/sign-in/code", data={"csrf_token": csrf, "code": "123456"}),
        )
        first.start()
        entered.wait(5)
        late = threading.Thread(target=tap_again)
        late.start()
        release.set()
        first.join(5)
        late.join(5)
        self.assertEqual(checks, ["123456"])
        self.assertEqual(second["response"].status_code, 302)
        self.assertIn("You're signed in", self.client.get("/sign-in").get_data(as_text=True))
        self.assertTrue(accounts.session_saved("member"))

    def test_send_a_new_code(self):
        csrf = self._open()
        self.assertEqual(self.client.post("/sign-in/resend", data={"csrf_token": csrf}).status_code, 400)
        self.client.post("/sign-in/password", data={"csrf_token": csrf, "password": "pw"})
        with patch.object(FakeService, "trigger_2fa_push_notification") as push:
            html = self.client.post("/sign-in/resend", data={"csrf_token": csrf}).get_data(as_text=True)
        push.assert_called_once()
        self.assertIn("New code sent.", html)
        self.assertIn('name="code"', html)
        self.assertEqual(self.client.post("/sign-in/resend").status_code, 403)

    def test_push_failure_still_asks_for_the_code(self):
        csrf = self._open()
        with patch.object(FakeService, "trigger_2fa_push_notification", side_effect=RuntimeError("x")):
            self.client.post("/sign-in/password", data={"csrf_token": csrf, "password": "pw"})
        self.assertIn("6-digit code", self.client.get("/sign-in").get_data(as_text=True))

    def test_code_without_a_pending_sign_in(self):
        csrf = self._open()
        response = self.client.post("/sign-in/code", data={"csrf_token": csrf, "code": "123456"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Start again", response.get_data(as_text=True))

    def test_pending_sign_in_expires(self):
        csrf = self._open()
        self.client.post("/sign-in/password", data={"csrf_token": csrf, "password": "pw"})
        member_signin._PENDING["member"]["at"] -= member_signin._PENDING_SECONDS + 1  # noqa: SLF001
        self.assertIn("Apple ID password", self.client.get("/sign-in").get_data(as_text=True))

    def test_short_code(self):
        csrf = self._open()
        self.client.post("/sign-in/password", data={"csrf_token": csrf, "password": "pw"})
        response = self.client.post("/sign-in/code", data={"csrf_token": csrf, "code": "12"})
        self.assertEqual(response.status_code, 400)

    def test_three_wrong_codes_start_over(self):
        FakeService.accept_code = False
        csrf = self._open()
        self.client.post("/sign-in/password", data={"csrf_token": csrf, "password": "pw"})
        for expected in ("Try the newest one", "Try the newest one", "Start again"):
            response = self.client.post("/sign-in/code", data={"csrf_token": csrf, "code": "111111"})
            self.assertIn(expected, response.get_data(as_text=True))
        self.assertNotIn("member", member_signin._PENDING)  # noqa: SLF001

    def test_code_check_error_counts_as_wrong(self):
        csrf = self._open()
        self.client.post("/sign-in/password", data={"csrf_token": csrf, "password": "pw"})
        with patch.object(FakeService, "validate_2fa_code", side_effect=RuntimeError("x")):
            response = self.client.post("/sign-in/code", data={"csrf_token": csrf, "code": "111111"})
        self.assertEqual(response.status_code, 400)

    def test_trust_failure_still_signs_in(self):
        csrf = self._open()
        self.client.post("/sign-in/password", data={"csrf_token": csrf, "password": "pw"})
        with patch.object(FakeService, "trust_session", side_effect=RuntimeError("x")):
            self.client.post("/sign-in/code", data={"csrf_token": csrf, "code": "123456"})
        self.assertIn("You're signed in", self.client.get("/sign-in").get_data(as_text=True))

    def test_session_expires(self):
        self._open()
        with self.client.session_transaction() as s:
            s["expires"] = 0
        self.assertEqual(self.client.get("/sign-in").status_code, 403)

    def test_without_a_session_is_403(self):
        self.assertEqual(self.client.get("/sign-in").status_code, 403)

    def test_shows_the_whole_apple_id_and_leads_home(self):
        self._open()
        html = self.client.get("/sign-in").get_data(as_text=True)
        self.assertIn(f'value="{MEMBER}" autocomplete="username" readonly', html)
        self.assertIn('<a class="home" href="/household/member">', html)
        self.assertIn("trust whoever runs it", html)
        self.assertNotIn("/settings", html)

    def test_headers(self):
        self._open()
        response = self.client.get("/sign-in")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")

    def test_secret_is_private_and_reused(self):
        first = member_signin.session_key()
        self.assertEqual(stat.S_IMODE(os.stat(member_signin._secret_path()).st_mode), 0o600)  # noqa: SLF001
        self.assertEqual(member_signin.session_key(), first)


class TestSignInWithoutUsername(_ConfigDir):
    """No username in config: the member enters it, and it gets pinned."""

    def setUp(self):
        super().setUp()
        FakeService.instances = []
        FakeService.requires_2fa = True
        FakeService.raise_on_init = None
        FakeService.accept_code = True
        config = {
            "app": {"credentials": {"username": MAIN}},
            "accounts": [{"id": "member"}, {"id": "other", "username": "other@example.com"}],
        }
        for patcher in (
            patch.object(web, "_load_current_config", lambda: config),
            patch("icloudpy.ICloudPyService", FakeService),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = web.create_app(testing=True).test_client()
        _csrf_post(self.client, "/household/member/sign-in")
        html = self.client.get("/sign-in").get_data(as_text=True)
        self.csrf = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        self.html = html

    def _sign_in(self, username, password="pw"):
        return self.client.post(
            "/sign-in/password",
            data={"csrf_token": self.csrf, "username": username, "password": password},
        )

    def test_page_asks_for_the_apple_id(self):
        self.assertIn('name="username"', self.html)
        self.assertNotIn('class="who"', self.html)

    def test_sign_in_pins_the_apple_id(self):
        self.assertEqual(self._sign_in(f"  {MEMBER} ").status_code, 302)
        self.assertEqual(FakeService.instances[0].apple_id, MEMBER)
        self.assertIsNone(accounts.pinned_username("member"))
        self.client.post("/sign-in/code", data={"csrf_token": self.csrf, "code": "123456"})
        self.assertEqual(accounts.pinned_username("member"), MEMBER)

    def test_no_second_factor_pins_too(self):
        FakeService.requires_2fa = False
        self._sign_in(MEMBER)
        self.assertEqual(accounts.pinned_username("member"), MEMBER)

    def test_refuses_a_non_apple_id(self):
        response = self._sign_in("not-an-email")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(FakeService.instances, [])

    def test_spaces_and_invisible_characters_are_dropped(self):
        local, domain = MEMBER.split("@")
        self.assertEqual(self._sign_in(f" {local.upper()} \u200b@ {domain}\u00a0").status_code, 302)
        self.assertEqual(FakeService.instances[0].apple_id, MEMBER)

    def test_a_refusal_keeps_the_typed_apple_id(self):
        FakeService.raise_on_init = exceptions.ICloudPyFailedLoginException("Invalid email/password combination.", None)
        body = self._sign_in(MEMBER).get_data(as_text=True)
        self.assertIn(f'value="{MEMBER}"', body)

    def test_refuses_an_apple_id_already_here(self):
        for taken in (MAIN, "OTHER@example.com"):
            with self.subTest(taken=taken):
                response = self._sign_in(taken)
                self.assertIn("already backed up here", response.get_data(as_text=True))
        self.assertEqual(FakeService.instances, [])


class TestDashboard(_ConfigDir):
    def setUp(self):
        super().setUp()
        patcher = patch.object(web, "_load_current_config", lambda: _config())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = web.create_app(testing=True).test_client()

    def test_dashboard_lists_members(self):
        with patch.object(web, "_build_service", return_value={}):
            html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Waiting for sign-in", html)
        self.assertIn('href="/household/member"', html)

    def test_unknown_member_goes_home(self):
        self.assertEqual(self.client.get("/household/nobody").status_code, 302)

    def test_forget(self):
        accounts.pin_username("member", MEMBER)
        response = _csrf_post(self.client, "/household/member/forget")
        self.assertTrue(response.headers["Location"].endswith("/household/member"))
        self.assertIsNone(accounts.pinned_username("member"))
        self.assertEqual(_csrf_post(self.client, "/household/nobody/forget").status_code, 302)
        self.assertEqual(self.client.post("/household/member/forget").status_code, 403)

    def test_admin_signs_someone_in_on_this_device(self):
        self.assertEqual(self.client.post("/household/member/sign-in").status_code, 403)
        response = _csrf_post(self.client, "/household/member/sign-in")
        self.assertEqual(response.headers["Location"], "/sign-in")
        html = self.client.get("/sign-in").get_data(as_text=True)
        self.assertIn(f'value="{MEMBER}" autocomplete="username" readonly', html)
        with self.client.session_transaction() as s:
            s["done"] = True
        self.assertIn('href="/household/member"', self.client.get("/sign-in").get_data(as_text=True))

    def test_admin_can_enter_the_apple_id_ahead_of_time(self):
        no_id = {
            "app": {"credentials": {"username": MAIN}},
            "accounts": [{"id": "member"}, {"id": "other", "username": "taken@example.com"}],
        }
        with patch.object(web, "_load_current_config", lambda: no_id):
            self.assertIn(
                'action="/household/member/apple-id"',
                self.client.get("/household/member").get_data(as_text=True),
            )
            for bad in ("not-an-email", MAIN.upper(), "taken@example.com"):
                with self.subTest(bad=bad):
                    response = _csrf_post(self.client, "/household/member/apple-id", data={"apple_id": bad})
                    self.assertIn("apple_id_error=1", response.headers["Location"])
                    self.assertIsNone(accounts.pinned_username("member"))
            self.assertEqual(self.client.post("/household/member/apple-id", data={"apple_id": MEMBER}).status_code, 403)
            response = _csrf_post(self.client, "/household/member/apple-id", data={"apple_id": f" {MEMBER.upper()} "})
            self.assertNotIn("apple_id_error", response.headers["Location"])
            self.assertEqual(accounts.pinned_username("member"), MEMBER)
            html = self.client.get("/household/member").get_data(as_text=True)
            self.assertNotIn('action="/household/member/apple-id"', html)
            self.assertIn(MEMBER, html)

    def test_accounts_page_shows_add_form_and_errors(self):
        with patch.object(web, "_build_service", return_value={}):
            html = self.client.get("/auth?household_error=Nope").get_data(as_text=True)
            dashboard = self.client.get("/").get_data(as_text=True)
        self.assertIn('action="/household/add"', html)
        self.assertIn("Nope", html)
        self.assertNotIn('action="/household/add"', dashboard)

    def test_a_members_whole_row_opens_their_page(self):
        with patch.object(web, "_build_service", return_value={}):
            html = self.client.get("/").get_data(as_text=True)
        self.assertIn('class="row-link" href="/household/member"', html)


class TestAddPerson(_ConfigDir):
    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.dir, "config.yaml")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write('app:\n  # keep me\n  credentials:\n    username: "main@example.com"\n')
        patcher = patch.object(web, "_current_config_path", return_value=self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = web.create_app(testing=True).test_client()

    def _text(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def test_adds_and_opens_the_member_page(self):
        response = _csrf_post(self.client, "/household/add", {"id": "Alex "})
        self.assertTrue(response.headers["Location"].endswith("/household/alex"))
        self.assertIn("- id: alex", self._text())
        self.assertIn("# keep me", self._text())

    def test_second_add_appends(self):
        _csrf_post(self.client, "/household/add", {"id": "alex"})
        _csrf_post(self.client, "/household/add", {"id": "sam"})
        self.assertIn("- id: sam", self._text())

    def test_refusals_come_back_to_the_accounts_page(self):
        _csrf_post(self.client, "/household/add", {"id": "alex"})
        for bad in ("alex", "Bad Name", ""):
            with self.subTest(bad=bad):
                response = _csrf_post(self.client, "/household/add", {"id": bad})
                self.assertIn("/auth?household_error=", response.headers["Location"])

    def test_accounts_must_be_a_list(self):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("accounts: nope\n")
        response = _csrf_post(self.client, "/household/add", {"id": "alex"})
        self.assertIn("household_error=", response.headers["Location"])

    def test_needs_csrf(self):
        self.assertEqual(self.client.post("/household/add", data={"id": "alex"}).status_code, 403)


class TestTheSignInPageSaysWhatItIs(unittest.TestCase):
    """The page a member opens says whose it is, what happens, and when to trust it."""

    def _render(self, state, review_first=False):
        from flask import render_template

        with _app().test_request_context("/sign-in"):
            return render_template(
                "signin.html",
                state=state,
                apple_id=None,
                ask_username=False,
                message=None,
                kind=None,
                review_first=review_first,
                csrf_token="x",
            )

    def test_before_signing_in(self):
        for state in ("password", "code"):
            html = self._render(state)
            self.assertIn("Not Apple", html)
            self.assertIn("Not Apple. Only sign in", html)
            self.assertIn("trust whoever runs it", html)
        self.assertIn("Nothing in your iCloud is changed or deleted", self._render("password"))

    def test_after_signing_in(self):
        self.assertNotIn("not Apple", self._render("done"))
        self.assertIn("starts once it's been checked", self._render("done", review_first=True))
        self.assertIn("starts in a few minutes", self._render("done"))
        self.assertNotIn("not Apple", self._render("invalid"))

    def test_names_drive_when_it_is_on(self):
        member = accounts.Account("member", "m@example.com")
        on = {"drive": {"destination": "drive/Main"}, "accounts": [{"id": "member"}]}
        off = {"drive": {"destination": "drive/Main"}, "accounts": [{"id": "member", "drive": False}]}
        with patch.object(member_signin, "_load_config", return_value=on):
            self.assertTrue(member_signin._with_drive(member))  # noqa: SLF001
            self.assertFalse(member_signin._with_drive(None))  # noqa: SLF001
        with patch.object(member_signin, "_load_config", return_value=off):
            self.assertFalse(member_signin._with_drive(member))  # noqa: SLF001
        from flask import render_template

        with _app().test_request_context("/sign-in"):
            html = render_template(
                "signin.html",
                state="password",
                what="photos and iCloud Drive files",
                csrf_token="x",
            )
        self.assertIn("copy of your iCloud photos and iCloud Drive files", html)

    def test_whether_a_review_comes_first(self):
        member = accounts.Account("member", "m@example.com")
        plain = {"photos": {"destination": "photos"}, "accounts": [{"id": "member"}]}
        adopting = {
            "photos": {"destination": "photos"},
            "accounts": [{"id": "member", "photos": {"adopt": "icloudpd"}}],
        }
        with patch.object(member_signin, "_load_config", return_value=adopting):
            self.assertTrue(member_signin._review_first(member))  # noqa: SLF001
            self.assertFalse(member_signin._review_first(None))  # noqa: SLF001
        with patch.object(member_signin, "_load_config", return_value=plain):
            self.assertFalse(member_signin._review_first(member))  # noqa: SLF001
        with patch.object(member_signin, "_load_config", return_value=None):
            self.assertFalse(member_signin._review_first(member))  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()
