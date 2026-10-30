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


@pytest.fixture(scope="module")
def full_release(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Aggregates of the release at `ecoinvent` size, counted from each file's text as it is written (no disk)."""
    import math  # noqa: PLC0415
    import re  # noqa: PLC0415

    from bwbench import ecospold  # noqa: PLC0415

    s = system("ecoinvent")
    flows = fake_flows(s.profile.flows + 3000)
    spare = set(flows[s.profile.flows :])
    comments = dict.fromkeys(ecospold.COMMENT, 0)
    chars, mu_error, padding = 0, 0.0, 0.0

    def count(_path: Path, text: str, encoding: str | None = None) -> None:
        nonlocal chars, mu_error, padding
        chars += len(text)  # all ASCII, so characters are bytes
        for kind, comment in ecospold.COMMENT.items():  # each kind's comment has its own length
            comments[kind] += text.count(comment)
        for mean, mu in re.findall(r'<lognormal meanValue="([^"]+)" mu="([^"]+)"', text):
            mu_error = max(mu_error, abs(float(mu) - math.log(abs(float(mean)))))
        for flow, amount in re.findall(r'elementaryExchangeId="([^"]+)" \S+ amount="([^"]+)"', text):
            if flow in spare:
                padding = max(padding, abs(float(amount)))

    with pytest.MonkeyPatch.context() as m:
        m.setattr(Path, "write_text", count)
        write_ecospold(s, tmp_path_factory.mktemp("full"), flows)
    n = s.profile.products
    return {"chars": chars, "mu_error": mu_error, "padding": padding, "comments": comments, "n": n}


def test_full_release_as_heavy_as_ecoinvent(full_release: dict):
    want = json.loads((PROFILES_DIR / "ecoinvent-3.12-cutoff.json").read_text())["ecospold"]
    assert full_release["chars"] / full_release["n"] == pytest.approx(want["bytes"], rel=0.01)


def test_full_release_comments_per_kind(full_release: dict):
    """The release's comment count per kind, at most one per exchange (ecoSpold2 allows one).

    A synthetic dataset with fewer intermediate exchanges than ecoinvent's mean of 12.78 comments
    gets one on each, so intermediate comments come to about 7.3 a dataset.
    """
    want = json.loads((PROFILES_DIR / "ecoinvent-3.12-cutoff.json").read_text())["ecospold"]["comments"]
    got = {kind: c / full_release["n"] for kind, c in full_release["comments"].items()}
    shortfall = {"intermediateExchange": 5.6}
    for kind, (count, _) in want.items():
        assert got[kind] == pytest.approx(count - shortfall.get(kind, 0), abs=0.1), kind


def test_full_release_lognormal_mu(full_release: dict):
    assert full_release["mu_error"] < 1e-12  # set_lognormal_loc_value takes log(|amount|) as mu


def test_full_release_padding_is_tiny(full_release: dict):
    assert 0 < full_release["padding"] < 1e-6


def test_bw2io_reads_every_exchange(tmp_path: Path):
    """bw2io's extractor finds each written exchange and accepts every uncertainty (runs where bw2io is installed)."""
    extractor = pytest.importorskip("bw2io.extractors.ecospold2").Ecospold2DataExtractor
    written = write_ecospold(system("smoke"), tmp_path, fake_flows(80))
    data = extractor.extract(tmp_path / "datasets", "synthetic", use_mp=False)
    exchanges = [e for ds in data for e in ds["exchanges"]]
    assert len(exchanges) == written
    # abort_exchange resets a rejected uncertainty with "Invalid parameters - set to undefined
    # uncertainty" or, for a lognormal, "... Reverting to undefined uncertainty."
    assert not [e for e in exchanges if "undefined uncertainty" in e.get("comment", "")]
