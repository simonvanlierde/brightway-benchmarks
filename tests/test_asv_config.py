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
    # `just smoke` benchmarks the last line as the latest release, so it must be a tag.
    assert not re.fullmatch(r"[0-9a-f]{40}", lines[-1])


@pytest.mark.parametrize("subject", SUBJECTS)
def test_configs_point_at_their_own_folders(subject: str):
    conf = json.loads((ASV / f"{subject}.json").read_text())
    assert conf["project"] == subject
    for key in ("results_dir", "env_dir", "html_dir"):
        assert conf[key].endswith(subject)
