import numpy as np

from bwbench.synth import SIZES, as_bw2data, generate


def test_same_seed_same_system():
    a, b = generate(SIZES["smoke"], seed=3), generate(SIZES["smoke"], seed=3)
    assert np.array_equal(a.tech_rows, b.tech_rows)
    assert np.array_equal(a.tech_data, b.tech_data)
    assert a.reference_scores() == b.reference_scores()
    assert not np.array_equal(a.tech_data, generate(SIZES["smoke"], seed=4).tech_data)


def test_technosphere_is_diagonally_dominant_and_has_no_repeated_cells():
    s = generate(SIZES["smoke"])
    a = s.technosphere()
    assert np.allclose(a.diagonal(), 1.0)
    off = abs(a).sum(axis=0).A1 - 1.0
    assert off.max() < 0.5
    cells = s.tech_rows * s.size.products + s.tech_cols
    assert np.unique(cells).size == cells.size


def test_reference_scores_match_a_dense_solve():
    s = generate(SIZES["smoke"])
    demand = np.zeros(s.size.products)
    demand[0] = 1.0
    supply = np.linalg.solve(s.technosphere().toarray(), demand)
    g = s.biosphere().toarray() @ supply
    dense = [g[f - s.flow_offset] @ c for f, c in zip(s.cf_flows, s.cf_data, strict=True)]
    assert np.allclose(s.reference_scores(), dense, rtol=1e-12)
    assert min(dense) > 0


def test_bw2data_form_has_every_exchange():
    s = generate(SIZES["smoke"])
    bio, tech, cfs = as_bw2data(s)
    assert len(bio) == s.size.flows
    assert len(tech) == s.size.products
    assert sum(len(v["exchanges"]) for v in tech.values()) == s.tech_data.size + s.bio_data.size
    assert [len(c) for c in cfs] == [f.size for f in s.cf_flows]
