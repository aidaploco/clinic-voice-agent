"""The pull-request gate: a gate nobody tests is one that quietly stops gating."""

import re
import subprocess
from pathlib import Path

import yaml

WORKFLOWS = sorted(Path(".github/workflows").glob("*.yml"))
CI = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())


def test_there_is_one_workflow_so_there_is_one_thing_to_require():
    assert [path.name for path in WORKFLOWS] == ["ci.yml"]


def test_the_summary_check_waits_for_every_other_job():
    others = set(CI["jobs"]) - {"ci-success"}
    assert set(CI["jobs"]["ci-success"]["needs"]) == others


def test_the_summary_check_runs_even_when_a_job_before_it_failed():
    assert CI["jobs"]["ci-success"]["if"] == "always()"


def test_nothing_that_ci_requires_is_filtered_by_path():
    triggers = CI[True]  # YAML reads the bare key `on` as the boolean True
    for event in ("push", "pull_request"):
        assert "paths" not in (triggers.get(event) or {})


def test_downloaded_tools_are_pinned_and_checksummed():
    text = Path(".github/workflows/ci.yml").read_text()
    downloads = re.findall(r"curl [^\n]*releases/download/[^\n]*", text)
    assert len(downloads) == 2  # gitleaks, actionlint
    assert text.count("sha256sum -c -") == len(downloads)


def test_the_push_guard_refuses_main_and_allows_a_branch():
    def run(remote_ref: str) -> subprocess.CompletedProcess:
        line = f"refs/heads/x 1111111 {remote_ref} 0000000\n"
        return subprocess.run(
            ["bash", ".githooks/pre-push"], input=line, capture_output=True, text=True, check=False
        )

    refused = run("refs/heads/main")
    assert refused.returncode == 1 and "pull request" in refused.stderr
    assert run("refs/heads/feature").returncode == 0
    assert run("refs/heads/main-fix").returncode == 0  # a prefix is not main
