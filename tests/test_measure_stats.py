"""scripts/measure_stats.py on three hand-written ecospold2 datasets (the real release is licensed)."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "measure_stats.py"


def dataset(
    activity: str,
    product: str,
    ref: float,
    location: str,
    isic: str,
    inputs: list[tuple],
    *,
    cpc: str = "",
    group: str = "0",
    by_product: str = "",
) -> str:
    """``isic`` holds comma-separated codes; the CPC classification comes after them."""
    classification = "".join(
        f"<classification><classificationSystem>ISIC rev.4 ecoinvent</classificationSystem>"
        f"<classificationValue>{code}:something</classificationValue></classification>"
        for code in isic.split(",")
        if code
    )
    if cpc:
        classification += (
            f"<classification><classificationSystem>CPC</classificationSystem>"
            f"<classificationValue>{cpc}:other</classificationValue></classification>"
        )
    exchanges = ""
    for supplier, p, amount in inputs:
        link = f' activityLinkId="{supplier}"' if supplier else ""
        exchanges += (
            f'<intermediateExchange intermediateExchangeId="{p}"{link} amount="{amount}">'
            "<inputGroup>5</inputGroup></intermediateExchange>"
        )
    if by_product:  # a second output, never linked
        exchanges += (
            f'<intermediateExchange intermediateExchangeId="{by_product}" amount="9.0">'
            "<outputGroup>2</outputGroup></intermediateExchange>"
        )
    return (
        '<ecoSpold xmlns="http://www.EcoInvent.org/EcoSpold02"><childActivityDataset><activityDescription>'
        f'<activity id="{activity}"/>{classification}<geography><shortname>{location}</shortname></geography>'
        f'</activityDescription><flowData><intermediateExchange intermediateExchangeId="{product}" amount="{ref}">'
        f"<outputGroup>{group}</outputGroup></intermediateExchange>{exchanges}</flowData></childActivityDataset></ecoSpold>"
    )


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch):
    spec = importlib.util.spec_from_file_location("measure_stats", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "measure_stats", module)  # the worker pool imports read() by name
    spec.loader.exec_module(module)
    return module


def release(tmp_path: Path, files: dict[str, str]) -> Path:
    datasets = tmp_path / "3.12-cutoff" / "datasets"
    datasets.mkdir(parents=True)
    for name, xml in files.items():
        (datasets / f"{name}.spold").write_text(xml)
    return tmp_path / "3.12-cutoff"


def leaves(node: object):
    if isinstance(node, dict):
        for v in node.values():
            yield from leaves(v)
    elif isinstance(node, list):
        for v in node:
            yield from leaves(v)
    else:
        yield node


def test_measure_stats_builds_the_technosphere(tmp_path: Path, script: ModuleType):
    folder = release(
        tmp_path,
        {
            # A takes in B, D, its own product (a loss) and a product nobody makes (unlinked).
            # It has a by-product, and a CPC code after its ISIC code.
            "A_pa": dataset(
                "SECRET-ACT-1",
                "SECRET-PROD-1",
                1.0,
                "ZZLOC",
                "3510",
                [
                    ("SECRET-ACT-2", "SECRET-PROD-2", 0.5),
                    ("SECRET-ACT-1", "SECRET-PROD-1", 0.1),
                    ("SECRET-ACT-9", "SECRET-PROD-9", 1.0),
                    ("SECRET-ACT-4", "SECRET-PROD-4", 0.25),
                ],
                cpc="1234",
                by_product="SECRET-BYPROD",
            ),
            # B is a waste treatment (production -1) that takes in A.
            "B_pb": dataset(
                "SECRET-ACT-2",
                "SECRET-PROD-2",
                -1.0,
                "ZZLOC",
                "3821",
                [("SECRET-ACT-1", "SECRET-PROD-1", 0.2), (None, "px", 3.0)],
            ),
            # C has a CPC code but no ISIC code, and takes in D twice: the two amounts add up.
            "C_pc": dataset(
                "SECRET-ACT-3",
                "SECRET-PROD-3",
                1.0,
                "YYLOC",
                "",
                [("SECRET-ACT-4", "SECRET-PROD-4", 0.1), ("SECRET-ACT-4", "SECRET-PROD-4", 0.2)],
                cpc="5678",
            ),
            # D shares its ISIC division (35) with A, and has two codes in it.
            "D_pd": dataset("SECRET-ACT-4", "SECRET-PROD-4", 1.0, "YYLOC", "3520,3530", []),
        },
    )
    out = tmp_path / "stats.json"
    script.main(folder, out)

    result = json.loads(out.read_text())
    stats = result["stats"]
    assert (result["datasets"], result["unlinked_inputs"], result["self_inputs"]) == (4, 1, 1)
    assert stats["entries"] == 4  # A <- B, A <- D, B <- A and C <- D; unlinked and self inputs are not entries
    assert stats["loops"] == {"components": 1, "largest": 2, "products_in_loops": 2}
    assert stats["same_location_share"] == pytest.approx(3 / 4)  # only A <- D crosses locations
    # C has no ISIC code (its CPC code is not one); A <- D is 35 against 35, A <- B and B <- A 35 against 38.
    assert stats["same_sector_share"] == pytest.approx(1 / 3)
    # Column A: 0.5 and 0.25 over 1 - 0.1; column B: 0.2 / -1, a negative input; column C: 0.1 + 0.2.
    assert stats["negative_input_share"] == pytest.approx(0.25)
    amounts = stats["log10_abs_input"]
    assert amounts["q50"] == pytest.approx((np.log10(0.25 / 0.9) + np.log10(0.3)) / 2)
    # Column sums are 0.75 / 0.9, 0.2, 0.3 and 0 (D takes nothing in).
    assert stats["column_abs_sum"]["q50"] == pytest.approx(0.25)
    # A heavy tail makes the mean one dataset's figure, so amounts publish no mean either.
    assert "mean" not in amounts
    assert "mean" not in stats["column_abs_sum"]
    assert "q00" not in amounts
    assert "q100" not in amounts
    assert stats["lu_fill"]
    assert stats["inputs_per_product"]["q50"] == 1
    for key in ("inputs_per_product", "consumers_per_supplier", "log10_abs_input", "column_abs_sum"):
        assert not {"mean", "q00", "q100"} & stats[key].keys(), key  # each is one dataset's figure
    assert "ecoinvent Association" in result["credit"]

    # Licence boundary: no id or location reaches the output, and the statistics are numbers.
    text = out.read_text()
    for secret in ("SECRET", "ZZLOC", "YYLOC", "1234", "5678"):
        assert secret not in text
    assert all(v is None or isinstance(v, int | float) for v in leaves(stats))

    # A structure-only rerun recomputes the structure and keeps only the fill, with its date.
    fill = stats["lu_fill"]
    before = json.loads(out.read_text())
    before["stats"]["gone"] = 1  # a field measure() no longer reports
    before["measured"], before["versions"] = "2020-01-01", {"numpy": "0", "scipy": "0"}
    before["stats"]["clustering"] = 0.5  # a stale structural value
    out.write_text(json.dumps(before))
    script.main(folder, out, structure_only=True)
    again = json.loads(out.read_text())
    assert again["stats"]["lu_fill"] == fill
    assert again["fill_measured"] == "2020-01-01"
    assert again["fill_versions"] == {"numpy": "0", "scipy": "0"}
    assert again["measured"] != "2020-01-01"
    assert again["stats"]["factor_seconds"] == stats["factor_seconds"]
    assert "gone" not in again["stats"]
    assert again["stats"]["clustering"] == stats["clustering"]

    with pytest.raises(SystemExit, match="does not exist"):
        script.main(folder, tmp_path / "missing.json", structure_only=True)
    again["stats"]["entries"] = 99
    out.write_text(json.dumps(again))
    with pytest.raises(SystemExit, match="another matrix"):
        script.main(folder, out, structure_only=True)


def test_a_dataset_without_a_reference_product_is_an_error(tmp_path: Path, script: ModuleType):
    folder = release(tmp_path, {"A_pa": dataset("A", "pa", 1.0, "CH", "", [], group="2")})
    with pytest.raises(ValueError, match=r"A_pa\.spold: no reference product"):
        script.main(folder, tmp_path / "stats.json")


def test_two_datasets_sharing_a_reference_product_are_an_error(tmp_path: Path, script: ModuleType):
    folder = release(
        tmp_path, {"A_pa": dataset("A", "pa", 1.0, "CH", "", []), "A_pa2": dataset("A", "pa", 1.0, "DE", "", [])}
    )
    with pytest.raises(ValueError, match="share a reference product"):
        script.main(folder, tmp_path / "stats.json")
