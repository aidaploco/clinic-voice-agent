"""Is anything private in this repository, its history, or its GitHub page?

    uv run python -m evals.pii_audit                       # needs your .env
    PII_EXTRA="a@b.com,First Last" PII_PUBLIC="handle,First Last" \
        uv run python -m evals.pii_audit

Run it before the repository is made public, and after any change that touches records, logs or
the README. It takes every private value in the owner's `.env` (phone numbers, keys, tokens, the
trunk's address and login, the LiveKit project's name) plus anything in `PII_EXTRA` (a comma
separated list given at run time, never stored: an email address, a name), and looks for each:

- in every file git tracks or would add, and every file that was ever committed on any branch
  (the whole history, with commit messages and who made them);
- on GitHub: pull requests, issues, their comments and reviews, the repository's description and
  topics, and branch names.

`PII_PUBLIC` lists what is meant to be public (the GitHub handle, the author's name): it is
taken out of the text before looking, so that a private value that contains it (a surname inside
the handle) is only found where it appears on its own.

A phone number is also found written another way ("+1 (555) 010-0100", digits only). It then looks
for things that merely look private: email addresses, phone-shaped numbers, home-folder paths.

It never prints a value it was looking for, and masks what it found. A finding says what kind of
thing, and where. Exit status 1 means a private value was found, 2 that GitHub could not be
read (so the result says nothing about it); the look-alikes are listed to be
judged by a person.
"""

import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

# Settings in `.env` that are not private: limits, switches, a local endpoint.
NOT_PRIVATE = {
    "MAX_CALL_SECONDS", "MAX_CONCURRENT_CALLS", "MAX_CALLS_PER_DAY", "DAILY_CALL_CAP",
    "DEV_CONSOLE", "INBOUND_POLL_SECONDS", "OTEL_EXPORTER_OTLP_ENDPOINT", "DATABASE_URL",
    "TRACE_ENDPOINT", "TRACE_FILE",
    "PIPELINE", "REALTIME_WAITS", "LANGUAGE_MENU", "WORKER_PORT", "AGENT_NAME",
}  # fmt: skip
PHONE_KEYS = ("NUMBER",)  # a setting whose name has this holds phone numbers
MIN_LENGTH = 6  # a shorter value would match everywhere ("true", "25")

# What may appear and is not private: GitHub's no-reply addresses, reserved example domains.
HARMLESS_EMAIL = re.compile(
    r"@(users\.noreply\.github\.com|noreply\.github\.com|example\.(com|org|net)|[\w.-]+\.test|localhost)$"
    r"|^noreply@|^git@github\.com$"
)
EMAIL = re.compile(r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
INTERNATIONAL = re.compile(r"\+\d[\d\s().-]{7,17}\d")
NATIONAL = re.compile(r"\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")
HOME = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+")
LOCKFILES = ("uv.lock", "package-lock.json")


@dataclass(frozen=True)
class Needle:
    label: str  # what it is (a setting's name), never its value
    value: str
    digits: str = ""  # for a phone number: only its digits


@dataclass(frozen=True)
class Finding:
    label: str
    where: str
    line: int | None = None


def digits_of(text: str) -> str:
    return re.sub(r"\D", "", text)


def parse_env(text: str) -> dict[str, str]:
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def needles_from(env: dict[str, str], extra: list[str]) -> list[Needle]:
    """The private values in an environment, each labelled by the setting it came from."""
    found: list[Needle] = []
    for key, value in env.items():
        if key in NOT_PRIVATE or len(value) < MIN_LENGTH:
            continue
        if any(word in key for word in PHONE_KEYS):
            for number in value.split(","):
                if len(digits_of(number)) >= 7:
                    found.append(Needle(key, number.strip(), digits_of(number)))
            continue
        found.append(Needle(key, value))
        if "://" in value and (host := urlparse(value).hostname):
            found.append(Needle(f"{key} (host)", host))
            if "." in host:
                found.append(Needle(f"{key} (project)", host.split(".")[0]))
    for number, item in enumerate(extra, 1):
        if len(item.strip()) >= 3:
            found.append(Needle(f"PII_EXTRA #{number}", item.strip()))
    return found


def scan(text: str, where: str, needles: list[Needle]) -> list[Finding]:
    """Every needle in the text, as findings that say where, never what."""
    hits = []
    lowered = text.lower()
    candidates = None
    for needle in needles:
        if needle.digits:
            if candidates is None:
                candidates = [
                    (m.start(), digits_of(m.group()))
                    for m in re.finditer(r"\+?\d[\d\s().-]{5,}\d", text)
                ]
            for start, digits in candidates:
                if len(digits) >= 7 and (needle.digits in digits or digits in needle.digits):
                    hits.append(Finding(needle.label, where, text.count("\n", 0, start) + 1))
        else:
            start = lowered.find(needle.value.lower())
            while start != -1:
                hits.append(Finding(needle.label, where, text.count("\n", 0, start) + 1))
                start = lowered.find(needle.value.lower(), start + 1)
    return hits


def without_public(text: str, public: list[str]) -> str:
    """The text with what is meant to be public (a handle, an author's name) taken out."""
    for item in public:
        if item.strip():
            text = re.sub(re.escape(item.strip()), " ", text, flags=re.IGNORECASE)
    return text


def mask(found: str) -> str:
    """What a look-alike was, without enough of it to be the thing."""
    return re.sub(r"\d(?=(?:\D*\d){2})", "•", found) if any(c.isdigit() for c in found) else "…"


def look_alikes(text: str, where: str) -> list[tuple[str, str, int, str]]:
    """Things that merely look private: (kind, where, line, masked)."""
    out = []
    for kind, pattern in (("email", EMAIL), ("phone", INTERNATIONAL), ("phone", NATIONAL),
                          ("home path", HOME)):  # fmt: skip
        for m in pattern.finditer(text):
            if kind == "email" and HARMLESS_EMAIL.search(m.group()):
                continue
            if kind == "phone" and len(digits_of(m.group())) not in range(8, 16):
                continue
            line = text.count("\n", 0, m.start()) + 1
            out.append((kind, where, line, mask(m.group()) if kind == "phone" else "…"))
    return out


# ----- where to look -----------------------------------------------------------------------


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True, errors="replace"
    ).stdout


def working_files() -> list[Path]:
    names = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")
    return [Path(n) for n in names if n and Path(n).is_file()]


def history_text() -> str:
    """Every commit on every branch: who, the message, and every line it added or removed."""
    return git("log", "--all", "-p", "--format=COMMIT %H%n%an <%ae>%n%cn <%ce>%n%B", "--no-color")


def identities() -> list[str]:
    return sorted(set(git("log", "--all", "--format=%an <%ae>%n%cn <%ce>").split("\n")) - {""})


class GitHubUnreadable(RuntimeError):
    """GitHub could not be read: a search that read nothing must not look like a clean one."""


def github(path: str) -> list[dict]:
    import json

    run = subprocess.run(
        ["gh", "api", "--paginate", path], capture_output=True, text=True, check=False
    )
    if run.returncode != 0:
        raise GitHubUnreadable(f"{path}: {run.stderr.strip().splitlines()[-1:] or ['failed']}")
    out = run.stdout
    if not out.strip():
        return []
    chunks = re.sub(r"\]\s*\[", ",", out) if out.lstrip().startswith("[") else out
    data = json.loads(chunks)
    return data if isinstance(data, list) else [data]


def github_texts(repo: str) -> list[tuple[str, str]]:
    surfaces = {
        "repository": f"repos/{repo}",
        "pull request": f"repos/{repo}/pulls?state=all",
        "issue": f"repos/{repo}/issues?state=all",
        "issue comment": f"repos/{repo}/issues/comments",
        "review comment": f"repos/{repo}/pulls/comments",
        "branch": f"repos/{repo}/branches",
        "release": f"repos/{repo}/releases",
    }
    texts = []
    for name, path in surfaces.items():
        items = github(path)
        print(f"  read {len(items):>3} from GitHub {name}", flush=True)
        for item in items:
            parts = [str(item.get(k) or "") for k in ("title", "body", "description", "name",
                                                       "homepage", "topics")]  # fmt: skip
            texts.append((f"GitHub {name} {item.get('number') or item.get('id') or ''}".strip(),
                          "\n".join(parts)))  # fmt: skip
    reviews = 0
    for pr in github(f"repos/{repo}/pulls?state=all"):
        for review in github(f"repos/{repo}/pulls/{pr['number']}/reviews"):
            reviews += 1
            texts.append((f"GitHub review on #{pr['number']}", str(review.get("body") or "")))
    print(f"  read {reviews:>3} from GitHub reviews", flush=True)
    return texts


def repo_name() -> str:
    url = git("remote", "get-url", "origin").strip()
    return re.sub(r"^.*github\.com[:/]", "", url).removesuffix(".git")


def main() -> int:
    env_file = Path(".env")
    env = parse_env(env_file.read_text()) if env_file.exists() else {}
    extra = [e for e in os.environ.get("PII_EXTRA", "").split(",") if e.strip()]
    public = [p for p in os.environ.get("PII_PUBLIC", "").split(",") if p.strip()]
    needles = needles_from(env, extra)
    print(f"looking for {len(needles)} private values from .env and PII_EXTRA", flush=True)
    if not env:
        print("no .env found: only the look-alike checks mean anything", file=sys.stderr)

    findings: list[Finding] = []
    seen: list[tuple[str, str, int, str]] = []

    def check(text: str, where: str, generic: bool = True) -> None:
        findings.extend(scan(without_public(text, public), where, needles))
        if generic:
            seen.extend(look_alikes(text, where))

    for path in working_files():
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        check(text, f"file {path}", generic=path.name not in LOCKFILES)
    check(history_text(), "git history (all branches)")
    for who in identities():
        check(who, "commit identity")
        print(f"commit identity: {re.sub(r'<.*@', '<…@', who)}")
    unreadable = False
    try:
        for where, text in github_texts(repo_name()):
            check(text, where)
    except (GitHubUnreadable, subprocess.CalledProcessError, ValueError, KeyError) as error:
        unreadable = True
        print(
            f"COULD NOT READ GITHUB ({type(error).__name__}: {error}); is `gh` logged in "
            "to the account that owns the repository? Nothing was checked there.",
            file=sys.stderr,
        )

    by_label: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_label[f.label].append(f)
    print()
    if by_label:
        print("PRIVATE VALUES FOUND:")
        for label, items in sorted(by_label.items()):
            print(f"  {label}: {len(items)} place(s)")
            for f in items[:8]:
                print(f"    {f.where}" + (f" line {f.line}" if f.line else ""))
    else:
        print("no private value from .env or PII_EXTRA found anywhere searched")
    if seen:
        print("\nLOOK-ALIKES TO JUDGE (masked):")
        grouped: dict[tuple[str, str, str], list[int]] = defaultdict(list)
        for kind, where, line, masked in seen:
            grouped[(kind, where, masked)].append(line)
        for (kind, where, masked), lines in sorted(grouped.items())[:60]:
            print(f"  {kind:<9} {masked:<22} {where} lines {sorted(set(lines))[:5]}")
    if unreadable:
        print("\nNOT A CLEAN RESULT: GitHub was not read.", file=sys.stderr)
    return 1 if by_label else (2 if unreadable else 0)


if __name__ == "__main__":
    sys.exit(main())
