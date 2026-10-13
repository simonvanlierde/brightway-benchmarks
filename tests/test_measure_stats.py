"""scripts/measure_stats.py on three hand-written ecospold2 datasets (the real release is licensed)."""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "measure_stats.py"


def dataset(activity: str, product: str, ref: float, location: str, isic: str, inputs: list[tuple]) -> str:
    classification = (
        f"<classification><classificationSystem>ISIC rev.4 ecoinvent</classificationSystem>"
        f"<classificationValue>{isic}:something</classificationValue></classification>"
        if isic
        else ""
    )
    exchanges = ""
    for supplier, p, amount in inputs:
        link = f' activityLinkId="{supplier}"' if supplier else ""
        exchanges += (
            f'<intermediateExchange intermediateExchangeId="{p}"{link} amount="{amount}">'
            "<inputGroup>5</inputGroup></intermediateExchange>"
        )
    return (
        '<ecoSpold xmlns="http://www.EcoInvent.org/EcoSpold02"><childActivityDataset><activityDescription>'
        f'<activity id="{activity}"/>{classification}<geography><shortname>{location}</shortname></geography>'
        f'</activityDescription><flowData><intermediateExchange intermediateExchangeId="{product}" amount="{ref}">'
        f"<outputGroup>0</outputGroup></intermediateExchange>{exchanges}</flowData></childActivityDataset></ecoSpold>"
    )


def test_measure_stats_builds_the_technosphere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    datasets = tmp_path / "3.12-cutoff" / "datasets"
    datasets.mkdir(parents=True)
    files = {
        # A takes in B, its own product (a loss) and a product nobody makes (unlinked).
        "A_pa": dataset("A", "pa", 1.0, "CH", "3510", [("B", "pb", 0.5), ("A", "pa", 0.1), ("Z", "pz", 1.0)]),
        # B is a waste treatment (production -1) that takes in A.
        "B_pb": dataset("B", "pb", -1.0, "CH", "3821", [("A", "pa", 0.2), (None, "px", 3.0)]),
        "C_pc": dataset("C", "pc", 1.0, "DE", "", []),
    }
    for name, xml in files.items():
        (datasets / f"{name}.spold").write_text(xml)

    spec = importlib.util.spec_from_file_location("measure_stats", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "measure_stats", script)  # the worker pool imports read() by name
    spec.loader.exec_module(script)
    out = tmp_path / "stats.json"
    script.main(tmp_path / "3.12-cutoff", out)

    result = json.loads(out.read_text())
    stats = result["stats"]
    assert (result["datasets"], result["unlinked_inputs"], result["self_inputs"]) == (3, 1, 1)
    assert stats["entries"] == 2  # A <- B and B <- A; unlinked and self inputs are not entries
    assert stats["loops"] == {"components": 1, "largest": 2, "products_in_loops": 2}
    assert stats["same_location_share"] == 1
    assert stats["same_sector_share"] == 0  # 35 against 38
    # Column A: 0.5 / (1 - 0.1); column B: 0.2 / -1, a negative input.
    assert stats["negative_input_share"] == pytest.approx(0.5)
    amounts = stats["log10_abs_input"]
    assert amounts["mean"] == pytest.approx((np.log10(0.5 / 0.9) + np.log10(0.2)) / 2)
    assert "q00" not in amounts
    assert "q100" not in amounts
    assert stats["lu_fill"]

    # A structure-only rerun recomputes the structure and keeps only the fill, with its date.
    fill = stats["lu_fill"]
    before = json.loads(out.read_text())
    before["stats"]["gone"] = 1  # a field measure() no longer reports
    before["stats"]["clustering"] = 0.5  # a stale structural value
    out.write_text(json.dumps(before))
    script.main(tmp_path / "3.12-cutoff", out, structure_only=True)
    again = json.loads(out.read_text())
    assert again["stats"]["lu_fill"] == fill
    assert again["fill_measured"] == before["measured"]
    assert "gone" not in again["stats"]
    assert again["stats"]["clustering"] == stats["clustering"]

    with pytest.raises(SystemExit, match="does not exist"):
        script.main(tmp_path / "3.12-cutoff", tmp_path / "missing.json", structure_only=True)
    again["stats"]["entries"] = 99
    out.write_text(json.dumps(again))
    with pytest.raises(SystemExit, match="another matrix"):
        script.main(tmp_path / "3.12-cutoff", out, structure_only=True)
