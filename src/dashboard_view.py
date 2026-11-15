"""What the dashboard says, worked out from what ``/api/status`` already has.

The dashboard answers one question, "is everyone's iCloud safely copied?",
and offers one tap when it isn't. Everything here is a view of the status
payload (``web._build_status``) and the log tail the page already reads:
no disk, network or lock is added to the page load.

- ``people``: one entry per Apple ID, the main account first, each with a
  tone, one sentence, and at most one action.
- ``headline``: the sentence at the top, from the people.
- ``log_summary``: warnings and errors in the tail, so the log can stay
  folded unless it has something to say.
"""

import re
from typing import Any

# Severity, most urgent first. A person's tone is the worst of their parts;
# the headline is the worst of the people.
TONES = ("err", "warn", "busy", "idle", "ok")

_LEVEL = re.compile(r":: (WARNING|ERROR|CRITICAL) ::")


def _worst(*tones: str) -> str:
    return min(tones, key=TONES.index)


def library_label(name: str) -> str:
    """The person's name for a photo library, not Apple's zone name."""
    if name == "PrimarySync":
        return "Personal library"
    if name == "SharedLibrary" or name.startswith("SharedSync-"):
        return "Shared Library"
    return name


def every(seconds: Any) -> str:
    """``43200`` -> ``every 12 h``; the schedule as a person says it."""
    try:
        seconds = int(seconds)
    except TypeError, ValueError:
        return ""
    if seconds <= 0:
        return "once, then stops"
    if seconds % 86400 == 0:
        days = seconds // 86400
        return "every day" if days == 1 else f"every {days} days"
    if seconds % 3600 == 0:
        return f"every {seconds // 3600} h"
    if seconds % 60 == 0:
        return f"every {seconds // 60} min"
    return f"every {seconds} s"


def _hue(name: str) -> int:
    """An avatar colour that comes from the name, so it never changes."""
    return sum(ord(c) * (i + 1) for i, c in enumerate(name.lower())) * 37 % 360


def _count(n: Any) -> str:
    return f"{int(n):,}"


def _service_view(service: dict) -> dict[str, Any]:
    stats = service.get("stats") or {}
    facts = []
    if stats.get("files_downloaded") is not None:
        facts.append(f"{_count(stats['files_downloaded'])} new")
    if stats.get("files_skipped") is not None:
        facts.append(f"{_count(stats['files_skipped'])} already here")
    if stats.get("files_removed"):
        facts.append(f"{_count(stats['files_removed'])} removed")
    if stats.get("errors"):
        facts.append(f"{_count(stats['errors'])} failed")
    marker_missing = bool(service.get("require_mount_marker") and not service.get("marker_present"))
    libraries = [{**lib, "label": library_label(lib.get("name", ""))} for lib in service.get("libraries") or []]
    # Said once for the service when it is true of every library.
    all_indexing = bool(libraries) and all(lib.get("indexing") for lib in libraries)
    name = service.get("name")
    # What the person's line says when this service is the trouble.
    problem = None
    if service.get("syncing_since_relative"):
        tone, when = (
            "busy",
            f"Syncing now · started {service['syncing_since_relative']}",
        )
    elif marker_missing:
        tone, when = "err", "Paused: the folder isn't mounted"
        problem = f"{name} is paused: its folder isn't mounted"
    elif any(lib.get("state") == "failed" for lib in libraries):
        tone, when = (
            "warn",
            f"Last backup {stats.get('last_sync_relative') or 'not finished'}",
        )
        problem = f"A {name} library failed"
    elif stats.get("last_sync_relative"):
        tone, when = "ok", f"Backed up {stats['last_sync_relative']}"
    else:
        tone, when = "idle", "Waiting for the first backup"
    return {
        **service,
        "tone": tone,
        "when": when,
        "facts": " · ".join(facts),
        "schedule": every(service.get("sync_interval_s")),
        "marker_missing": marker_missing,
        "libraries": libraries,
        "all_indexing": all_indexing,
        "problem": problem,
    }


def _primary(status: dict) -> dict[str, Any]:
    services = [_service_view(s) for s in status.get("services") or []]
    auth = status.get("auth_state") or "not_configured"
    username = status.get("username")
    trust = status.get("trust_days_remaining")
    action = None
    detail = None
    if auth == "not_configured":
        tone, sentence = "err", "No Apple ID set up yet"
        action = {"label": "Set up", "href": "/auth"}
    elif auth == "setup_needed":
        tone, sentence = "warn", "Waiting for the first sign-in"
        action = {"label": "Sign in", "href": "/auth"}
    elif auth == "reauth_needed":
        tone, sentence = "err", "Backups are stopped"
        detail = {
            "session_unusable": "The saved session is no longer valid and no password is stored.",
            "sign_in_failed": "Apple refused the sign-in. This can be an outage; it keeps retrying.",
        }.get(
            status.get("auth_blocked_reason") or "",
            "Apple is asking for a second factor.",
        )
        action = {"label": "Sign in again", "href": "/auth"}
    else:
        busy = [s for s in services if s["tone"] == "busy"]
        broken = [s for s in services if s["tone"] in ("err", "warn")]
        if busy:
            tone, sentence = "busy", "Backing up now"
            detail = " · ".join(f"{s['name']} started {s['syncing_since_relative']}" for s in busy)
        elif broken:
            tone = _worst(*(s["tone"] for s in broken))
            sentence = "; ".join(s["problem"] for s in broken)
        elif services and all(s["tone"] == "ok" for s in services):
            tone = "ok"
            # The stalest service bounds how safe everything is.
            oldest = min(services, key=lambda s: (s.get("stats") or {}).get("completed_at") or 0)
            sentence = oldest["when"]
        else:
            tone, sentence = "idle", "Waiting for the first backup"
        if trust is not None and trust <= 0:
            tone = _worst(tone, "warn")
            detail = "Apple's trust for this sign-in has run out. Refresh it to keep backups running."
            action = {"label": "Refresh trust", "post": "/auth/refresh-trust"}
        elif trust is not None and trust < 7 and tone != "err":
            tone = _worst(tone, "warn")
            detail = f"Apple's trust for this sign-in runs out in {trust} day{'' if trust == 1 else 's'}."
            action = {"label": "Refresh trust", "post": "/auth/refresh-trust"}
    return {
        "kind": "primary",
        "id": None,
        "name": username or "Main account",
        "initial": (username or "?")[0].upper(),
        "hue": _hue(username or ""),
        "tone": tone,
        "sentence": sentence,
        "detail": detail,
        "action": action,
        "services": services,
        "trust_days_remaining": trust,
        "signed_in": auth == "ready",
    }


def _member(member: dict) -> dict[str, Any]:
    name = member.get("name") or member["id"].capitalize()
    backup = member.get("backup") or {}
    status = backup.get("status") or "waiting"
    report = backup.get("report") or {}
    page = f"/household/{member['id']}"
    action = None
    detail = None
    if not member.get("session_saved"):
        tone, sentence = "idle", "Waiting for sign-in"
        action = {"label": "Send link", "href": page}
    elif status == "review":
        tone, sentence = "warn", "Ready for review"
        detail = f"{_count(report.get('download', 0))} to download"
        if report.get("deletes") and not report.get("over_limit") and report.get("unclaimed"):
            detail += f" · {_count(report['unclaimed'])} to delete"
        detail += ". Nothing changes until you tap Start backup."
        action = {"label": "Review", "href": page}
    elif status == "checking":
        tone, sentence = "busy", "Checking what's already in the folder"
    elif status == "syncing":
        tone, sentence = "busy", "Backing up now"
    elif status == "ok":
        tone = "ok"
        sentence = f"Backed up {backup['last_sync_relative']}" if backup.get("last_sync_relative") else "Backed up"
        new = backup.get("files_downloaded")
        detail = backup.get("detail") or (f"{_count(new)} new" if new else None)
    elif status == "needs_sign_in":
        tone, sentence = "err", "Sign-in has run out"
        detail = backup.get("detail")
        action = {"label": "Send link", "href": page}
    elif status in ("blocked", "error"):
        tone, sentence = "err", ("Not backing up" if status == "blocked" else "The last backup failed")
        detail = backup.get("detail")
        action = {"label": "Open", "href": page}
    else:
        tone, sentence = "idle", "First backup starts soon"
    return {
        "kind": "member",
        "id": member["id"],
        "name": name,
        "initial": name[:1].upper(),
        "hue": _hue(member["id"]),
        "username": member.get("username"),
        "tone": tone,
        "sentence": sentence,
        "detail": detail,
        "action": action,
        "page": page,
    }


def refreshing(status: dict, everyone: list[dict]) -> bool:
    """Whether the page should keep itself current: something is running."""
    return any(p["tone"] == "busy" for p in everyone) or any(
        s.get("syncing_since_relative") for s in status.get("services") or []
    )


def people(status: dict) -> list[dict[str, Any]]:
    """The main account, then each household member."""
    return [_primary(status)] + [_member(m) for m in status.get("household") or []]


def _plainly(person: dict) -> str:
    """One person's state as a sentence that stands alone at the top."""
    name, sentence = person["name"], person["sentence"]
    if person["kind"] == "primary":
        # The card already says the state; the headline says what to do.
        action = (person.get("action") or {}).get("label")
        trust = person.get("trust_days_remaining")
        if action == "Sign in again":
            return "Sign in again to restart backups"
        if action in ("Sign in", "Set up"):
            return "Sign in to start backing up"
        if action == "Refresh trust":
            if trust is not None and trust > 0:
                return f"Refresh trust: it runs out in {trust} day{'' if trust == 1 else 's'}"
            return "Refresh trust to keep backups running"
        return sentence
    return {
        "Ready for review": f"{name}'s backup is ready for review",
        "Waiting for sign-in": f"Waiting for {name} to sign in",
        "Sign-in has run out": f"{name} needs to sign in again",
        "Not backing up": f"{name}'s backup is not running",
        "The last backup failed": f"{name}'s last backup failed",
    }.get(sentence, f"{name}: {sentence[0].lower()}{sentence[1:]}")


def headline(everyone: list[dict]) -> dict[str, str]:
    """The sentence at the top: the one thing that needs you, or that all is well.

    Plain words, the fact itself. The cards below carry the detail, so the
    headline never repeats a time or a count from them.
    """
    if not everyone:
        return {"tone": "idle", "title": "Nothing set up yet"}
    needs = [p for p in everyone if p["action"] and p["tone"] in ("err", "warn")]
    if needs:
        worst = min(needs, key=lambda p: TONES.index(p["tone"]))
        return {"tone": worst["tone"], "title": _plainly(worst)}
    if any(p["tone"] == "busy" for p in everyone):
        return {"tone": "busy", "title": "Backing up"}
    if all(p["tone"] == "ok" for p in everyone):
        return {"tone": "ok", "title": "Everything is backed up"}
    waiting = next(p for p in everyone if p["tone"] != "ok")
    return {"tone": waiting["tone"], "title": _plainly(waiting)}


# What the config says when a key is left out and its default applies. Every
# pass logs these, and they are the config working as designed. Matched on the
# message, so a real config warning from the same module still counts.
_DEFAULT_NOTICE = re.compile(r"not found\. (?:Using default|Downloading|Not removing)|is missing\. Using default")


def _problem(line: str) -> str | None:
    """What an app log line is about, without the file, id or numbers.

    ``[alex] File not found in iCloud Drive - /icloud/drive/...`` becomes
    ``File not found in iCloud Drive``. Library lines (``icloudpy.*``) give
    None: the app logs the same failure in its own words.
    """
    parts = line.split(" :: ", 5)
    if len(parts) < 6 or parts[2].strip() != "root":
        return None
    message = re.sub(r"^\[[^\]]*\]\s*", "", parts[5].strip())
    message = re.split(r" - |: | /|\(", message, maxsplit=1)[0]
    message = re.sub(r"SharedSync-[0-9A-Fa-f-]+", "the Shared Library", message)
    message = re.sub(r"\d[\d,.]*", "N", message).strip(" .")
    return message[:70] or None


def log_summary(lines: list[str]) -> dict[str, Any]:
    """Warnings and errors in the log tail, the most recent one, and what
    most of them are about (``top``), so a count never stands alone."""
    warnings = errors = 0
    last = None
    seen: dict[str, int] = {}
    for line in lines or []:
        match = _LEVEL.search(line)
        if not match:
            continue
        if match.group(1) == "WARNING" and _DEFAULT_NOTICE.search(line):
            continue
        if match.group(1) == "WARNING":
            warnings += 1
        else:
            errors += 1
        last = line
        problem = _problem(line)
        if problem:
            seen[problem] = seen.get(problem, 0) + 1
    if errors or warnings:
        parts = []
        if errors:
            parts.append(f"{errors} error{'' if errors == 1 else 's'}")
        if warnings:
            parts.append(f"{warnings} warning{'' if warnings == 1 else 's'}")
        text = " and ".join(parts) + " recently"
    else:
        text = "Nothing unusual recently"
    top = None
    if seen:
        problem, count = max(seen.items(), key=lambda item: item[1])
        top = f"Mostly: {problem} ({count})" if len(seen) > 1 else f"{problem} ({count})"
    return {"warnings": warnings, "errors": errors, "text": text, "last": last, "top": top}
