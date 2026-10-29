import json
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

from bwbench.ecospold import write_ecospold
from bwbench.synth import PROFILES_DIR, system

NS = {"es": "http://www.EcoInvent.org/EcoSpold02"}


def fake_flows(n: int) -> list[str]:
    return [str(uuid.uuid5(uuid.NAMESPACE_URL, f"flow {j}")) for j in range(n)]


def read_back(folder: Path, flows: list[str]) -> tuple[sparse.csc_matrix, sparse.csc_matrix]:
    """A and B as an ecoSpold2 importer would see them: amounts by activity link and flow id."""
    files = sorted((folder / "datasets").glob("*.spold"))
    roots = [ET.parse(f).getroot() for f in files]  # noqa: S314 - files this test wrote

    def activity(root: ET.Element) -> str:
        return next(root.iterfind(".//es:activity", NS)).attrib["id"]

    def is_reference(exc: ET.Element) -> bool:
        return exc.findtext("es:outputGroup", default="", namespaces=NS) == "0"

    product = {}  # activity id -> product index, from the dataset's reference product name
    for root in roots:
        ref = next(e for e in root.iterfind(".//es:intermediateExchange", NS) if is_reference(e))
        product[activity(root)] = int(ref.findtext("es:name", default="", namespaces=NS).split()[-1])
    flow = {f: j for j, f in enumerate(flows)}
    n = len(roots)
    a, b = sparse.lil_matrix((n, n)), sparse.lil_matrix((len(flows), n))
    for root in roots:
        col = product[activity(root)]
        for exc in root.iterfind(".//es:intermediateExchange", NS):
            amount = float(exc.attrib["amount"])
            if is_reference(exc):
                a[col, col] += amount
            else:
                a[product[exc.attrib["activityLinkId"]], col] -= amount
        for exc in root.iterfind(".//es:elementaryExchange", NS):
            b[flow[exc.attrib["elementaryExchangeId"]], col] += float(exc.attrib["amount"])
    return a.tocsc(), b.tocsc()


def test_release_holds_the_system(tmp_path: Path):
    s = system("smoke")
    flows = fake_flows(s.profile.flows + 5)  # more flows than needed: the first ones are used
    written = write_ecospold(s, tmp_path, flows)
    a, b = read_back(tmp_path, flows)
    assert written == s.tech_rows.size + s.bio_rows.size + b[s.profile.flows :].nnz  # padding on the spare flows
    assert len(list((tmp_path / "datasets").iterdir())) == s.profile.products
    np.testing.assert_array_equal(a.toarray(), s.technosphere().toarray())
    np.testing.assert_array_equal(b[: s.profile.flows].toarray(), s.biosphere().toarray())


def test_same_system_same_files(tmp_path: Path):
    s, flows = system("smoke"), fake_flows(30)
    one, two = tmp_path / "1", tmp_path / "2"
    write_ecospold(s, one, flows), write_ecospold(s, two, flows)
    names = sorted(p.name for p in (one / "datasets").iterdir())
    assert names == sorted(p.name for p in (two / "datasets").iterdir())
    assert all((one / "datasets" / n).read_bytes() == (two / "datasets" / n).read_bytes() for n in names)


def test_too_few_flows(tmp_path: Path):
    with pytest.raises(ValueError, match="30 flows"):
        write_ecospold(system("smoke"), tmp_path, fake_flows(29))


def test_files_as_heavy_as_ecoinvent(tmp_path: Path):
    """Per dataset, the counts ecoinvent 3.12 averages; padding uses only the flows past the system's."""
    s = system("smoke")
    flows = fake_flows(s.profile.flows + 50)
    write_ecospold(s, tmp_path, flows)
    want = json.loads((PROFILES_DIR / "ecoinvent-3.12-cutoff.json").read_text())["ecospold"]
    roots = [ET.parse(f).getroot() for f in (tmp_path / "datasets").glob("*.spold")]  # noqa: S314 - files this test wrote
    n = len(roots)

    def mean(path: str) -> float:
        return sum(len(r.findall(path, NS)) for r in roots) / n

    assert mean(".//es:elementaryExchange") == pytest.approx(want["elementary_exchanges"], abs=0.2)
    assert mean(".//es:property") == pytest.approx(want["properties"], abs=1)
    # abs=1: a few smoke datasets have fewer than 25 exchanges to put one on
    assert mean(".//es:lognormal") == pytest.approx(want["lognormal_uncertainties"], abs=1)
    assert mean(".//es:pedigreeMatrix") == mean(".//es:lognormal")
    # Comments at ecoinvent's count and length per kind: bw2io keeps their text in memory. Counted
    # over datasets with room for them: a smoke dataset can have fewer exchanges than comments.
    for kind, child, (count, chars) in [
        *((kind, "comment", v) for kind, v in want["comments"].items()),
        ("generalComment", "text", want["general_comment"]),
    ]:
        room = [r for r in roots if kind == "generalComment" or len(r.findall(f".//es:{kind}", NS)) > count]
        texts = [e.text or "" for r in room for e in r.iterfind(f".//es:{kind}/es:{child}", NS)]
        assert len(texts) / len(room) == pytest.approx(count, abs=1), kind
        assert sum(map(len, texts)) / len(texts) == pytest.approx(chars, rel=0.05), kind
    assert mean(".//es:parameter") == pytest.approx(want["parameters"], abs=0.1)
    assert mean(".//es:lognormal[@mu='-inf']") == 0  # set_lognormal_loc_value takes log(|amount|)
    ids = {e.attrib["elementaryExchangeId"] for r in roots for e in r.iterfind(".//es:elementaryExchange", NS)}
    assert ids <= set(flows)
    assert ids - set(flows[: s.profile.flows])  # some padding, on the spare flows only
