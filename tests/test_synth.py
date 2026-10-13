import numpy as np
import pytest
from scipy import sparse

from bwbench.synth import SIZES, as_bw2data, generate, neumann


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
    supply = np.linalg.solve(s.technosphere().toarray(), np.eye(s.size.products, 30))
    g = s.biosphere().toarray() @ supply
    dense = [[g[f - s.flow_offset, p] @ c for f, c in zip(s.cf_flows, s.cf_data, strict=True)] for p in range(30)]
    assert np.allclose(s.reference_scores(), dense, rtol=1e-12)
    assert np.min(dense) > 0


def test_bw2data_form_has_every_exchange():
    s = generate(SIZES["smoke"])
    bio, tech, cfs = as_bw2data(s)
    assert len(bio) == s.size.flows
    assert len(tech) == s.size.products
    assert sum(len(v["exchanges"]) for v in tech.values()) == s.tech_data.size + s.bio_data.size
    assert [len(c) for c in cfs] == [f.size for f in s.cf_flows]


def test_neumann_solves_one_demand_and_refuses_to_diverge():
    s = generate(SIZES["smoke"])
    a = s.technosphere()
    demand = np.zeros(s.size.products)
    demand[5] = 2.0
    x = neumann(sparse.identity(s.size.products, format="csr") - a, demand)
    assert np.allclose(a @ x, demand, rtol=0, atol=1e-14)
    with pytest.raises(ArithmeticError):
        neumann(sparse.csr_matrix([[0.0, 1.0], [1.0, 0.0]]), np.ones(2))
