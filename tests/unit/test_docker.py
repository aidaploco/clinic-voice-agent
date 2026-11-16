"""The container setup: keep secrets out of the image and the page off the network."""

import re
from pathlib import Path

import yaml

DOCKERFILE = Path("Dockerfile").read_text()
IGNORE = Path(".dockerignore").read_text().splitlines()
COMPOSE = yaml.safe_load(Path("compose.yaml").read_text())


def test_every_base_image_is_pinned_by_digest():
    sources = re.findall(r"^(?:FROM|COPY --from=)(?:\s+)?(\S+)", DOCKERFILE, flags=re.M)
    sources = [s for s in sources if s not in ("page", "app")]
    assert len(sources) == 3  # node, python, uv
    for source in sources:
        assert re.search(r"@sha256:[0-9a-f]{64}$", source), source


def test_secrets_and_local_files_are_kept_out_of_the_build():
    for pattern in (".env", ".git", ".venv", "recordings", "web/node_modules"):
        assert pattern in IGNORE, pattern
    assert not re.search(r"COPY[^\n]*\.env", DOCKERFILE.replace(".env.example", ""))
    assert not re.search(r"^ENV[^\n]*(KEY|SECRET|TOKEN|PASSWORD)", DOCKERFILE, flags=re.M | re.I)


def test_the_application_does_not_run_as_root():
    assert re.search(r"^USER app$", DOCKERFILE, flags=re.M)


def test_every_published_port_is_on_the_hosts_loopback_only():
    for name, service in COMPOSE["services"].items():
        for port in service.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), (name, port)


def test_the_app_services_take_their_keys_from_the_environment_file_not_the_compose_file():
    app = COMPOSE["x-app"]
    assert app["env_file"] == ".env"
    inline = " ".join(str(v) for v in app["environment"].values())
    assert "sk-" not in inline and "API_KEY" not in " ".join(app["environment"])
