import copy
import json
import math
import platform
import random
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from bwbench import compare
from bwbench.fingerprint import fingerprint
from bwbench.ratios import bootstrap_interval, geometric_mean_ratio, interleave, problems, ratio_seed

# An arm's environment: its lock is the resolved set, which problems() requires of every arm.
ARM_FP = fingerprint() | {"lock": {"name": "requirements.txt", "sha256": "0" * 64}}
times = st.lists(st.floats(1e-4, 10.0), min_size=2, max_size=30)


def test_interleave_runs_every_arm_once_per_round_in_changing_orders():
    arms = ["superlu", "umfpack", "pypardiso"]
    order = interleave(arms, 20, random.Random(1))
    assert len(order) == 20
    assert all(sorted(r) == sorted(arms) for r in order)
    assert len({tuple(r) for r in order}) > 1  # 6 orders, so 20 equal rounds would be no shuffle
    assert order == interleave(arms, 20, random.Random(1))


def test_interleave_puts_each_arm_first_about_equally_often():
    order = interleave(["a", "b"], 2000, random.Random(2))
    first_a = sum(r[0] == "a" for r in order)
    assert 900 < first_a < 1100  # binomial(2000, 0.5): 1000 +- 4.5 standard deviations


def test_ratio_is_the_geometric_mean_of_paired_rounds():
    # Rounds 2 and 3 ran on a slower machine moment; pairing cancels it.
    base, cand = [1.0, 2.0, 4.0], [2.0, 4.0, 8.0]
    assert geometric_mean_ratio(base, cand) == pytest.approx(2.0, rel=1e-12)  # exp/log round trip
    assert geometric_mean_ratio([1.0, 1.0], [0.5, 2.0]) == pytest.approx(1.0, rel=1e-12)
    with pytest.raises(ValueError, match="rounds"):
        geometric_mean_ratio([1.0], [1.0, 2.0])


def test_interval_of_a_constant_ratio_has_no_width():
    lo, hi = bootstrap_interval([1.0, 2.0, 3.0], [3.0, 6.0, 9.0], seed=0, resamples=500)
    assert lo == pytest.approx(3.0, rel=1e-12)
    assert hi == pytest.approx(3.0, rel=1e-12)


@given(times, st.integers(0, 2**32 - 1))
def test_interval_holds_the_ratio(base: list[float], seed: int):
    cand = [b * (1.5 + 0.1 * math.sin(i)) for i, b in enumerate(base)]
    lo, hi = bootstrap_interval(base, cand, seed, resamples=400)
    ratio = geometric_mean_ratio(base, cand)
    assert lo <= ratio * (1 + 1e-12)  # float slack on exp(log)
    assert ratio <= hi * (1 + 1e-12)
    assert bootstrap_interval(base, cand, seed, resamples=400) == (lo, hi)


def test_interval_covers_the_true_ratio_about_95_percent_of_the_time():
    rng = random.Random(3)
    covered, trials = 0, 200
    for t in range(trials):
        drift = [rng.lognormvariate(0, 0.3) for _ in range(20)]  # the shared machine's state per round
        base = [d * rng.lognormvariate(0, 0.1) for d in drift]
        cand = [1.5 * d * rng.lognormvariate(0, 0.1) for d in drift]
        lo, hi = bootstrap_interval(base, cand, seed=t, resamples=1000)
        covered += lo <= 1.5 <= hi
    # The percentile bootstrap undercovers a little at 20 rounds; well outside this is a bug.
    assert 0.88 <= covered / trials <= 0.99


def fake_time_arm(slow: dict[str, float], fail: frozenset[str] = frozenset()) -> tuple[Callable, list[str]]:
    calls: list[str] = []

    def time_arm(arm: compare.Arm, *_: object) -> dict:
        calls.append(arm.name)
        if arm.name in fail:
            return {"missing": "the case failed: boom"}
        k = len(calls)
        return {
            "seconds": [slow[arm.name] * (1 + 0.01 * (k % 3))] * 3,
            "solver": arm.solver,
            "versions": {"bw2calc": "3.1.0"},
            "missing": None,
        }

    return time_arm, calls


def result(
    monkeypatch: pytest.MonkeyPatch, fail: frozenset[str] = frozenset(), rounds: int = 6
) -> tuple[dict, list[str]]:
    time_arm, calls = fake_time_arm({"superlu": 1.0, "umfpack": 0.5, "pypardiso": 0.25}, fail)
    monkeypatch.setattr(compare, "time_arm", time_arm)
    c = compare.comparisons("Linux", {})["solvers"]
    built = {c.baseline.env: compare.Built(python=Path("python"), fingerprint=ARM_FP)}
    doc = {
        "format": "bwbench-ratios/1",
        "tier": "contributed",
        "machine": "test machine",
        "created": "2026-11-14T12:00:00Z",
        "source": {"commit": None, "run": None},
        "rounds": rounds,
        "repeats": 3,
        "seed": 4,
        "resamples": 10_000,
        "fingerprint": fingerprint(),
        "comparisons": [compare.measure(c, built, rounds, 3, 4, Path())],
    }
    return json.loads(json.dumps(doc)), calls


def test_measure_interleaves_and_writes_a_valid_file(monkeypatch: pytest.MonkeyPatch):
    doc, calls = result(monkeypatch)
    assert problems(doc) == []
    assert len(calls) == 18
    assert all(sorted(calls[i : i + 3]) == ["pypardiso", "superlu", "umfpack"] for i in range(0, 18, 3))
    ratios = {r["candidate"]: r for r in doc["comparisons"][0]["ratios"]}
    assert ratios["umfpack"]["ratio"] == pytest.approx(0.5, rel=0.03)  # the fake's 1% steps between rounds
    assert ratios["pypardiso"]["ratio"] == pytest.approx(0.25, rel=0.03)


def test_a_missing_arm_has_no_ratio_not_a_zero(monkeypatch: pytest.MonkeyPatch):
    doc, _ = result(monkeypatch, fail=frozenset({"umfpack"}))
    assert problems(doc) == []
    c = doc["comparisons"][0]
    assert c["arms"]["umfpack"]["missing"] == "the case failed: boom"
    assert c["arms"]["umfpack"]["seconds"] == []
    by = {r["candidate"]: r for r in c["ratios"]}
    assert by["umfpack"] == {
        "candidate": "umfpack",
        "ratio": None,
        "ci95": None,
        "seconds": None,
        "missing": "candidate missing",
    }
    assert by["pypardiso"]["ratio"] is not None


def test_a_missing_baseline_leaves_every_candidate_without_a_ratio(monkeypatch: pytest.MonkeyPatch):
    doc, _ = result(monkeypatch, fail=frozenset({"superlu"}))
    assert problems(doc) == []
    assert {r["missing"] for r in doc["comparisons"][0]["ratios"]} == {"baseline missing"}


def broken(doc: dict, change: Callable[[dict], object]) -> list[str]:
    doc = copy.deepcopy(doc)
    change(doc)
    return problems(doc)


def ratio_of(doc: dict, name: str = "umfpack") -> dict:
    return next(r for r in doc["comparisons"][0]["ratios"] if r["candidate"] == name)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda d: d.pop("fingerprint"), "'fingerprint' is a required property"),
        (lambda d: d["fingerprint"].pop("cpu_model"), "fingerprint: missing field cpu_model"),
        (lambda d: d["comparisons"][0]["arms"]["superlu"]["fingerprint"].update(version=2), "fingerprint: version"),
        (lambda d: d.update(tier="verified"), "'verified' is not one of"),
        (lambda d: d.update(extra=1), "Additional properties"),
        (lambda d: d.update(created="yesterday"), "is not a 'date-time'"),
        (lambda d: ratio_of(d).update(ratio=ratio_of(d)["ratio"] * 1.01), "but the seconds give"),
        (lambda d: ratio_of(d).update(ci95=[0.1, 0.2]), "outside its interval"),
        (lambda d: ratio_of(d).update(ci95=ratio_of(d)["ci95"][::-1]), "low above high"),
        (lambda d: ratio_of(d).update(ci95=[ratio_of(d)["ci95"][0] * 0.99, ratio_of(d)["ci95"][1]]), "the seed gives"),
        (lambda d: d["comparisons"][0]["ratios"].pop(), "has no ratio"),
        (lambda d: d["comparisons"][0]["ratios"].append(ratio_of(d)), "2 ratios"),
        (lambda d: d["comparisons"].append(d["comparisons"][0]), "comparison 'solvers' twice"),
        (
            lambda d: ratio_of(d).update(missing="no reason", ratio=None, ci95=None, seconds=None),
            "missing, but both arms have times",
        ),
        (
            lambda d: d["comparisons"][0]["arms"]["superlu"]["fingerprint"].update(lock=None),
            "superlu/fingerprint: no lock",
        ),
        (lambda d: ratio_of(d).update(ratio=0.0), "less than or equal to the minimum"),
        (lambda d: ratio_of(d).update(missing="no reason", ratio=0.5), "is not of type 'null'"),
        (lambda d: ratio_of(d).update(candidate="superlu"), "is not a candidate arm"),
        (lambda d: d["comparisons"][0]["arms"]["umfpack"]["seconds"].pop(), "5 times for 6 rounds"),
        (lambda d: d["comparisons"][0]["arms"]["umfpack"].update(missing="gone"), "a ratio from a missing arm"),
        (lambda d: d["comparisons"][0].update(baseline="klu"), "baseline 'klu' is not an arm"),
        (lambda d: d["comparisons"][0].update(case="first score"), "does not match"),
        (lambda d: d["comparisons"][0]["arms"]["umfpack"].update(missing="", seconds=[]), "should be non-empty"),
        (lambda d: ratio_of(d).update(missing="", ratio=None, ci95=None, seconds=None), "should be non-empty"),
        (lambda d: d.update(machine="box \u202egpj.exe"), r"machine: 'box \u202egpj.exe' does not match"),
        (lambda d: ratio_of(d).update(candidate="umf\u200bpack"), "does not match"),
        (lambda d: d["fingerprint"].update(cpu_model="CPU\x1b[2J"), "fingerprint/cpu_model: control or format"),
        (lambda d: d["comparisons"][0]["arms"]["superlu"]["versions"].update({"bw\u2066": "1"}), "U+2066"),
    ],
)
def test_validator_names_each_problem(monkeypatch: pytest.MonkeyPatch, change: Callable[[dict], object], expected: str):
    doc, _ = result(monkeypatch)
    found = broken(doc, change)
    assert any(expected in p for p in found), found


def test_validate_command_exit_codes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    doc, _ = result(monkeypatch)
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(doc))
    bad.write_text(json.dumps(doc | {"tier": "verified"}))
    assert compare.main(["validate", str(good)]) == 0
    assert compare.main(["validate", str(good), str(bad)]) == 1
    assert "bad.json: tier: 'verified' is not one of" in capsys.readouterr().err
    with pytest.raises(SystemExit) as e:
        compare.main(["compare"])  # no -o
    assert e.value.code == 2


def test_compare_defaults_to_the_solvers():
    args = compare.parse(["compare", "-o", "x.json"])
    assert args.ids == ["solvers"]
    assert compare.parse(["compare", "all", "-o", "x.json"]).ids == ["all"]


def test_release_comparisons_only_on_macos_and_windows():
    assert "bw2calc-release" not in compare.comparisons("Linux", {})
    mac = compare.comparisons("Darwin", {"bw2calc": "3.1.0", "bw2data": "4.8"})
    assert mac["bw2calc-release"].baseline.env.requirements == ("bw2calc<3.1.0",)
    assert mac["bw2data-release"].candidates[0].env.requirements == ("bw2data==4.8", "bw2calc")


def test_release_comparisons_need_the_latest_release():
    """Without a release comparison named, compare() resolves no release: the others still run."""
    assert set(compare.comparisons("Darwin", {})) == {"solvers", "install-path", "python"}


def test_an_arm_that_fails_later_drops_its_solver_and_versions(monkeypatch: pytest.MonkeyPatch):
    time_arm, calls = fake_time_arm({"superlu": 1.0, "umfpack": 0.5, "pypardiso": 0.25})

    def flaky(arm: compare.Arm, *rest: object) -> dict:
        if arm.name == "umfpack" and calls.count("umfpack") >= 2:
            return {"missing": "the case failed: boom"}
        return time_arm(arm, *rest)

    monkeypatch.setattr(compare, "time_arm", flaky)
    c = compare.comparisons("Linux", {})["solvers"]
    built = {c.baseline.env: compare.Built(python=Path("python"), fingerprint=ARM_FP)}
    umfpack = compare.measure(c, built, 4, 3, 1, Path())["arms"]["umfpack"]
    assert umfpack["missing"] == "the case failed: boom"
    assert (umfpack["solver"], umfpack["versions"], umfpack["seconds"]) == (None, {}, [])


def test_the_stored_interval_follows_from_the_seed(monkeypatch: pytest.MonkeyPatch):
    doc, _ = result(monkeypatch)
    c = doc["comparisons"][0]
    base, cand = c["arms"]["superlu"]["seconds"], c["arms"]["umfpack"]["seconds"]
    seed = ratio_seed(doc["seed"], "solvers", "umfpack")
    assert ratio_of(doc)["ci95"] == list(bootstrap_interval(base, cand, seed, doc["resamples"]))


def script(path: Path, body: str) -> Path:
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)
    return path


ARM = compare.Arm("superlu", compare.Env("uv", "3.13", ("bw2calc",)))
CUTOFF = "2026-11-07T12:00:00Z"


@pytest.mark.skipif(sys.platform == "win32", reason="shell-script stand-ins")
@pytest.mark.parametrize(
    ("body", "why"),
    [
        ("", "printed no JSON object"),
        ("echo 'Traceback?'", "printed no JSON object"),
        ("sleep 5", "timed out after 1 s"),
        ("""echo '{"seconds": [1.0], "solver": null, "versions": {}, "missing": null}'""", "never imported bw2calc"),
    ],
)
def test_an_arm_that_prints_no_result_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str, why: str):
    monkeypatch.setattr(compare, "TIMEOUT", 1)
    built = compare.Built(python=script(tmp_path / "python", body))
    out = compare.time_arm(ARM, built, "bench_lca.SingleScore.time_first_score", {}, 1, tmp_path)
    assert why in out["missing"]


@pytest.fixture
def fake_uv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A uv that refuses ``uv venv`` over an existing folder, as uv 0.13 does, and freezes what FREEZE says."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    script(
        bin_ / "uv",
        f"""case "$1 $2" in
venv*) for a; do dir=$a; done
  [ -e "$dir" ] && {{ echo 'A virtual environment already exists; use the --clear flag' >&2; exit 2; }}
  mkdir -p "$dir/bin" && ln -s {sys.executable} "$dir/bin/python" ;;
"pip install") echo "$UV_EXCLUDE_NEWER" >>"$0.cutoffs" ;;
"pip freeze") [ -n "$FREEZE" ] && echo "$FREEZE" || {{ echo 'freeze failed' >&2; exit 1; }} ;;
esac""",
    )
    monkeypatch.setenv("PATH", f"{bin_}:{__import__('os').environ['PATH']}")
    monkeypatch.setenv("FREEZE", "bw2calc==3.1.0")
    return tmp_path


@pytest.mark.skipif(sys.platform == "win32", reason="shell-script stand-ins")
def test_an_arm_builds_again_in_the_same_folder(fake_uv: Path):
    """A second run over the same --work folder builds each arm afresh, not over the last run's venv."""
    env = compare.Env("uv", "3.13", ("bw2calc",))
    for _ in range(2):
        built = compare.build(env, fake_uv / "work" / "env0", CUTOFF)
        assert built.failed is None
        assert built.fingerprint is not None
        assert built.fingerprint["lock"]["name"] == "requirements.txt"


@pytest.mark.skipif(sys.platform == "win32", reason="shell-script stand-ins")
@pytest.mark.parametrize("freeze", ["", " "])
def test_an_arm_whose_resolved_set_is_unknown_fails(fake_uv: Path, monkeypatch: pytest.MonkeyPatch, freeze: str):
    monkeypatch.setenv("FREEZE", freeze)
    built = compare.build(compare.Env("uv", "3.13", ("bw2calc",)), fake_uv / "env0", CUTOFF)
    assert built.failed is not None
    assert built.failed.startswith("uv pip freeze")


@pytest.mark.parametrize("created", ["2026-11-14", "2026-11-14T12:00:00", "yesterday"])
def test_created_is_checked_without_rfc3339_validator(monkeypatch: pytest.MonkeyPatch, created: str):
    """Without rfc3339-validator, jsonschema skips format: date-time."""
    import jsonschema  # noqa: PLC0415

    doc, _ = result(monkeypatch)
    monkeypatch.setattr(jsonschema.Draft202012Validator, "FORMAT_CHECKER", jsonschema.FormatChecker(formats=()))
    assert problems(doc) == []
    assert broken(doc, lambda d: d.update(created=created)) == [f"created: not an RFC 3339 date-time: {created!r}"]


@pytest.mark.parametrize(
    ("attrs", "expected"),
    [({}, None), ({"PYPARDISO": False}, "superlu"), ({"PYPARDISO": False, "UMFPACK": True}, "umfpack")],
)
def test_timecase_names_the_solver_only_when_bw2calc_says(
    monkeypatch: pytest.MonkeyPatch, attrs: dict, expected: str | None
):
    """bw2calc before 2.0 has no PYPARDISO flag, and 2.0's early dev releases no UMFPACK."""
    import types  # noqa: PLC0415

    from bwbench import timecase  # noqa: PLC0415

    monkeypatch.setitem(sys.modules, "bw2calc", types.SimpleNamespace(**attrs))
    assert timecase.solver() == expected


def test_the_accelerate_arm_runs_on_macos_and_is_missing_elsewhere():
    mac = {a.name: a for a in compare.comparisons("Darwin", {})["solvers"].candidates}
    assert (mac["accelerate"].solver, mac["accelerate"].missing) == ("accelerate", None)
    assert set(mac["accelerate"].hide) == {"pypardiso", "scikits.umfpack"}  # bw2calc's own pick is SuperLU
    for system in ("Linux", "Windows"):
        arm = compare.comparisons(system, {})["solvers"].candidates[-1]
        assert (arm.name, arm.missing) == ("accelerate", "Apple Accelerate is macOS only")


def test_an_arm_missing_on_this_system_is_recorded_not_timed(monkeypatch: pytest.MonkeyPatch):
    doc, calls = result(monkeypatch)
    assert "accelerate" not in calls
    c = doc["comparisons"][0]
    assert c["arms"]["accelerate"]["missing"] == "Apple Accelerate is macOS only"
    assert {r["candidate"]: r["missing"] for r in c["ratios"]}["accelerate"] == "candidate missing"
    assert problems(doc) == []


@pytest.mark.skipif(sys.platform == "win32", reason="shell-script stand-ins")
@pytest.mark.parametrize(("solver", "patched"), [("accelerate", "accelerate"), ("superlu", "")])
def test_a_patched_arm_sets_its_solver_and_the_others_clear_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, solver: str, patched: str
):
    """A BWBENCH_SOLVER left in the caller's environment must not patch the SuperLU arm."""
    monkeypatch.setenv("BWBENCH_SOLVER", "klu")
    line = '{"seconds": [1.0], "solver": "%s", "versions": {}, "missing": null}\\n'
    body = f"printf '{line}' \"${{BWBENCH_SOLVER:-superlu}}\""
    built = compare.Built(python=script(tmp_path / "python", body))
    arm = compare.Arm(solver, ARM.env, solver=solver)
    out = compare.time_arm(arm, built, "bench_lca.SingleScore.time_first_score", {}, 1, tmp_path)
    assert (out["missing"], out["solver"]) == (None, patched or "superlu")


def test_timecase_names_a_patched_solver_once_bw2calc_called_it(monkeypatch: pytest.MonkeyPatch):
    import types  # noqa: PLC0415

    from bwbench import solvers, timecase  # noqa: PLC0415

    monkeypatch.setitem(sys.modules, "bw2calc", types.SimpleNamespace(PYPARDISO=False))
    monkeypatch.setenv("BWBENCH_SOLVER", "accelerate")
    monkeypatch.setattr(solvers, "CALLS", [0])
    assert timecase.solver() == "superlu"  # never reached: time_arm then reports the mismatch
    solvers.CALLS[0] = 1
    assert timecase.solver() == "accelerate"


def test_compare_imports_without_numpy():
    """The compare command runs where only the arms have NumPy (the ratios workflow's uv run --no-project)."""
    import subprocess  # noqa: PLC0415

    code = "import sys; sys.modules['numpy'] = None; import bwbench.compare"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_the_signing_job_runs_only_locked_packages():
    """The attest job holds the OIDC token: its Python comes from uv.lock, never an unlocked --with."""
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ratios.yml").read_text()
    attest = workflow[workflow.index("\n  attest:") : workflow.index("\n  publish:")]
    assert "id-token: write" in attest
    uv = [line for line in attest.splitlines() if "uv sync" in line or "uv run" in line]
    assert uv
    assert all("--with" not in line and "--no-project" not in line for line in uv), uv
    assert all("--frozen" in line if "uv sync" in line else "--no-sync" in line for line in uv), uv


@pytest.mark.parametrize("doc", ["docs/method.md", ".github/workflows/ratios.yml"])
def test_the_verify_command_pins_the_signing_workflow_and_branch(doc: str):
    """-R alone accepts a file signed by any workflow of the repository, run on any branch."""
    text = " ".join((Path(__file__).resolve().parents[1] / doc).read_text().replace("#", " ").split())
    start = text.index("gh attestation verify")
    command = text[start : text.index("`", start)]
    assert "--signer-workflow simonvanlierde/brightway-benchmarks/.github/workflows/ratios.yml" in command
    assert "--source-ref refs/heads/main" in command


@pytest.mark.skipif(sys.platform == "win32", reason="shell-script stand-ins")
@pytest.mark.skipif(compare.PIXI_PLATFORMS.get((platform.system(), platform.machine())) is None, reason="no pixi")
def test_both_install_paths_resolve_with_the_same_cutoff(fake_uv: Path):
    """install-path compares one bw2calc release: pixi and uv leave out the same new releases."""
    env = ".pixi/envs/default/bin"
    script(fake_uv / "bin" / "pixi", f'[ "$1" = install ] && mkdir -p {env} && ln -s {sys.executable} {env}/python')
    compare.build(compare.Env("uv", "3.13", ("bw2calc",)), fake_uv / "env0", CUTOFF)
    compare.build(compare.Env("pixi", "3.13", ("bw2calc",)), fake_uv / "env1", CUTOFF)
    assert (fake_uv / "bin" / "uv.cutoffs").read_text().split() == [CUTOFF]
    manifest = tomllib.loads((fake_uv / "env1" / "pixi.toml").read_text())
    assert manifest["workspace"]["exclude-newer"] == CUTOFF
    assert manifest["dependencies"]["bw2calc"] == "*"


def test_each_comparison_is_saved_as_it_finishes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """A job killed in a later comparison keeps the ones before it, in a valid file."""
    time_arm, _ = fake_time_arm({"superlu": 1.0, "umfpack": 0.5, "pypardiso": 0.25, "pypi": 1.0, "conda-forge": 1.1})
    monkeypatch.setattr(compare, "time_arm", time_arm)
    monkeypatch.setattr(compare, "build", lambda *_: compare.Built(python=Path("python"), fingerprint=ARM_FP))
    real = compare.measure

    def measure(c: compare.Comparison, *rest: object) -> dict:
        if c.id == "install-path":
            raise KeyboardInterrupt
        return real(c, *rest)  # ty: ignore[invalid-argument-type]

    monkeypatch.setattr(compare, "measure", measure)
    out = tmp_path / "r.json"
    with pytest.raises(KeyboardInterrupt):
        compare.compare(["solvers", "install-path"], out, 3, 1, "contributed", "test machine", tmp_path)
    doc = json.loads(out.read_text())
    assert [c["id"] for c in doc["comparisons"]] == ["solvers"]
    assert problems(doc) == []
    assert list(tmp_path.glob("*.tmp")) == []


def test_a_run_without_any_ratio_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Every arm missing writes the file, with the reasons, but exits 4: nothing was measured."""
    monkeypatch.setattr(compare, "build", lambda *_: compare.Built(failed="cannot install here"))
    out = tmp_path / "r.json"
    assert compare.main(["compare", "-o", str(out), "--work", str(tmp_path / "w"), "--machine", "test"]) == 4
    assert {r["missing"] for r in json.loads(out.read_text())["comparisons"][0]["ratios"]} == {"baseline missing"}
    assert "exit codes" in compare.parser().format_help().lower()


def test_the_schema_refuses_every_control_and_format_character_it_can_name():
    """The schema's text pattern covers Cc and Cf in the Basic Multilingual Plane; problems() covers the rest."""
    import re  # noqa: PLC0415
    import unicodedata  # noqa: PLC0415

    pattern = re.compile(
        json.loads(compare.PACKAGE.joinpath("ratios.schema.json").read_text())["$defs"]["text"]["pattern"]
    )
    hidden = [chr(i) for i in range(0x10000) if unicodedata.category(chr(i)) in {"Cc", "Cf"}]
    assert [f"U+{ord(c):04X}" for c in hidden if pattern.search(f"a{c}b")] == []
    assert pattern.search("GitHub ubuntu24 ½ µ")


@pytest.mark.parametrize("label", ["", "x" * 101, "box\u202eexe", "box\x1b[2J"])
def test_compare_refuses_a_machine_label_the_file_could_not_hold(
    label: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(compare, "compare", lambda *_: pytest.fail("compare ran"))  # never install bw2calc here
    with pytest.raises(SystemExit) as e:
        compare.main(["compare", "-o", str(tmp_path / "r.json"), "--machine", label])
    assert e.value.code == 2
