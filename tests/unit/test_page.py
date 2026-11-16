"""The page's files: everything it loads is served from the repository, nothing from elsewhere."""

import re
from pathlib import Path

STATIC = Path("src/clinic_voice_agent/web/static")


def test_the_page_loads_only_files_that_exist_here():
    html = (STATIC / "index.html").read_text()
    for reference in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert reference.startswith("/static/"), reference
        assert (STATIC / reference.removeprefix("/static/")).is_file(), reference


def test_the_page_script_never_writes_markup_from_a_call():
    script = (STATIC / "app.js").read_text()
    for forbidden in ("innerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert forbidden not in script, forbidden


def test_the_vendored_client_matches_its_recorded_checksum():
    import hashlib

    note = (STATIC / "vendor" / "README.md").read_text()
    recorded = re.search(r"sha256\s+([0-9a-f]{64})", note).group(1)
    actual = hashlib.sha256((STATIC / "vendor" / "livekit-client.umd.js").read_bytes()).hexdigest()
    assert actual == recorded
