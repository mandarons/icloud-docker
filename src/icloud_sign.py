# /// script
# requires-python = ">=3.10"
# dependencies = ["fido2"]
# ///
"""Sign an Apple security-key challenge locally.

Runs on whichever machine physically holds the key. It never sees your
Apple ID password and never contacts Apple: it signs a challenge the
container already obtained, and the assertion goes straight to the
clipboard so the signature never appears on screen or in shell history.

Why this cannot be a button in the page: WebAuthn requires the relying
party id to be a suffix of the page origin and Apple's is ``apple.com``,
and browsers blocklist FIDO devices from WebHID/WebUSB precisely to stop a
page performing raw CTAP against another origin.

Usage:  uv run <dashboard>/signer.py <challenge-blob>
        uv run - <challenge-blob>   (script fed on stdin; offline form)
"""

import base64
import json
import struct
import subprocess
import sys

from fido2.client import DefaultClientDataCollector, Fido2Client
from fido2.hid import CtapHidDevice
from fido2.webauthn import (
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialRequestOptions,
    PublicKeyCredentialType,
    UserVerificationRequirement,
)

RP_ID = "apple.com"
# Apple serves the sign-in widget from here, so this is the origin a real
# browser reports for the ceremony, and rpId apple.com is a registrable
# suffix of it as WebAuthn requires.
ORIGIN = "https://idmsa.apple.com"


_COPY_COMMANDS = (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"])


def unpack(blob: str) -> tuple[bytes, list[bytes]]:
    """Decode the bundle: challenge then length-prefixed credential ids."""
    raw = base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))
    offset = 0
    (challenge_len,) = struct.unpack_from("!H", raw, offset)
    offset += 2
    challenge = raw[offset : offset + challenge_len]
    offset += challenge_len
    handles = []
    while offset < len(raw):
        (handle_len,) = struct.unpack_from("!H", raw, offset)
        offset += 2
        handles.append(raw[offset : offset + handle_len])
        offset += handle_len
    return challenge, handles


def encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def build_client_data(challenge: bytes) -> bytes:
    """The clientDataJSON a browser would produce for this assertion."""
    return json.dumps(
        {
            "type": "webauthn.get",
            "challenge": base64.urlsafe_b64encode(challenge).decode().rstrip("="),
            "origin": ORIGIN,
            "crossOrigin": False,
        },
        separators=(",", ":"),
    ).encode()



def sign(device, challenge: bytes, handles: list[bytes]) -> dict:
    """Produce the WebAuthn assertion Apple expects for a security key."""
    client = Fido2Client(
        device,
        client_data_collector=DefaultClientDataCollector(ORIGIN),
    )
    options = PublicKeyCredentialRequestOptions(
        challenge=challenge,
        rp_id=RP_ID,
        allow_credentials=[
            PublicKeyCredentialDescriptor(
                id=handle,
                type=PublicKeyCredentialType("public-key"),
            )
            for handle in handles
        ],
        # Chrome signs in for this account with a plain tap and no PIN, so
        # Apple accepts UV=0 here. Asking for "required" merely fails on a
        # key that has no PIN configured.
        user_verification=UserVerificationRequirement("discouraged"),
    )
    # Say what is being signed before asking for the touch. A relayed
    # WebAuthn request can come from somewhere you did not expect, which is
    # why Windows shows the source on its own redirected prompts; the
    # defence is knowing what the touch will approve.
    print(
        f"\n  Signing an Apple sign-in for {RP_ID} (as {ORIGIN}),\n"
        f"  relayed from your icloud-docker container.\n"
        f"  Only touch the key if you just started this from its dashboard.\n\n"
        f"  {device.product_name} — TOUCH IT NOW\n",
        file=sys.stderr,
    )
    result = client.get_assertion(options).get_response(0)
    return {
        "clientData": encode(result.response.client_data),
        "signatureData": encode(result.response.signature),
        "authenticatorData": encode(result.response.authenticator_data),
        "userHandle": encode(result.response.user_handle)
        if result.response.user_handle
        else None,
        "credentialID": encode(result.raw_id),
        "rpId": RP_ID,
    }


def to_clipboard(text: str) -> str:
    """Copy without echoing. Returns the tool used, or "" if none worked."""
    for command in _COPY_COMMANDS:
        try:
            subprocess.run(command, input=text.encode(), check=True)
            return command[0]
        except (OSError, subprocess.CalledProcessError):
            continue
    return ""


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 64

    challenge, handles = unpack(sys.argv[1])

    devices = list(CtapHidDevice.list_devices())
    if not devices:
        print("No security key found — plug it in and run this again.", file=sys.stderr)
        return 3

    try:
        payload = sign(devices[0], challenge, handles)
    except Exception as error:  # noqa: BLE001
        print(f"  Could not sign: {error}", file=sys.stderr)
        return 5

    payload["challenge"] = encode(challenge).rstrip("=")
    assertion = base64.b64encode(json.dumps(payload).encode()).decode()

    tool = to_clipboard(assertion)
    if not tool:
        print(
            "  Signed, but no clipboard tool was available (tried pbcopy,\n"
            "  wl-copy, xclip). Install one and re-run rather than pasting the\n"
            "  signature through your terminal.",
            file=sys.stderr,
        )
        return 6

    print(
        f"  Signed. Assertion copied to your clipboard via {tool}.\n"
        "  Paste it into the browser and submit; the page clears your\n"
        "  clipboard once Apple accepts it.\n",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
