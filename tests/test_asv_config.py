"""The asv configs and the release lists next to them."""

import json
import re
from pathlib import Path

import pytest

ASV = Path(__file__).resolve().parents[1] / "asv"
SUBJECTS = sorted(p.stem for p in ASV.glob("*.json"))


@pytest.mark.parametrize("subject", SUBJECTS)
def test_hashes_are_tags_or_full_commits_ending_on_a_release(subject: str):
    lines = (ASV / f"{subject}.hashes").read_text().splitlines()
    assert lines
    assert len(set(lines)) == len(lines)
    for line in lines:
        assert re.fullmatch(r"[0-9a-f]{40}|v?\d+(\.\d+)*", line), line
    # `just smoke` benchmarks the first and last line as the oldest and latest release, and
    # `just stack` resolves the last, so both must be tags.
    assert not re.fullmatch(r"[0-9a-f]{40}", lines[0])
    assert not re.fullmatch(r"[0-9a-f]{40}", lines[-1])


@pytest.mark.parametrize("subject", SUBJECTS)
def test_configs_point_at_their_own_folders(subject: str):
    conf = json.loads((ASV / f"{subject}.json").read_text())
    assert conf["project"] == subject
    assert conf["results_dir"] == f"../results/{subject}"
    assert conf["env_dir"] == f"../.asv/env/{subject}"
    assert conf["html_dir"] == f"../site/{subject}"


def test_the_site_deploys_from_main_only():
    workflow = (ASV.parent / ".github" / "workflows" / "site.yml").read_text()
    deploy = workflow[workflow.index("\n  deploy:") :]
    assert "if: github.ref == 'refs/heads/main'" in deploy
