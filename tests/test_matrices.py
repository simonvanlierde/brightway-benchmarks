import types

import numpy as np
import pytest
from scipy import sparse
from scipy.sparse import linalg as sla

from bwbench.matrices import as_bw2data, neumann, neumann_score
from bwbench.synth import system


def test_float32_reference_rounds_the_amounts():
    s = system("smoke")
    err = abs(s.float32_reference() - s.reference[0][0]) / abs(s.reference[0][0])
    assert 1e-12 < err < 1e-6


def test_bw2data_form_has_every_exchange():
    s = system("smoke")
    bio, tech, cfs = as_bw2data(s)
    assert len(bio) == s.profile.flows
    assert len(tech) == s.profile.products
    assert sum(len(v["exchanges"]) for v in tech.values()) == s.tech_data.size + s.bio_data.size
    assert [len(c) for c in cfs] == [f.size for f in s.cf_flows]


def test_neumann_solves_with_units_and_refuses_to_diverge():
    s = system("smoke")
    a = s.technosphere()
    demand = np.zeros(s.profile.products)
    demand[5] = 2.0
    x = neumann(sparse.identity(s.profile.products, format="csr") - a, demand, scale=s.scale)
    # Entries the demand cannot reach are 0 here and rounding noise (about 1e-19) in a dense solve.
    assert np.allclose(x, np.linalg.solve(a.toarray(), demand), rtol=1e-12, atol=1e-15 * np.abs(x).max())
    with pytest.raises(ArithmeticError):
        neumann(sparse.csr_matrix([[0.0, 1.0], [1.0, 0.0]]), np.ones(2))


def test_neumann_stops_on_the_tail_bound_at_a_high_radius():
    # A chain whose columns sum to 0.95: the old stopping rule held only up to 0.5.
    n = 50
    x = sparse.diags([np.full(n - 1, 0.95)], [1], format="csr")
    demand = np.zeros(n)
    demand[-1] = 1.0
    got = neumann(x, demand)
    assert np.allclose(got, np.linalg.solve(np.eye(n) - x.toarray(), demand), rtol=1e-14, atol=0)


def test_neumann_converges_past_a_column_sum_of_one():
    # Column 1 sums to 2, but the spectral radius is sqrt(0.2): a Monte Carlo draw can look like this.
    x = sparse.csr_matrix([[0.0, 2.0], [0.1, 0.0]])
    got = neumann(x, np.array([1.0, 1.0]))
    assert np.allclose(got, np.linalg.solve(np.eye(2) - x.toarray(), [1.0, 1.0]), rtol=1e-14, atol=0)


def test_neumann_score_matches_the_reference():
    s = system("smoke")
    n = s.profile.products
    demand = np.zeros(n)
    demand[0] = 1.0
    cf = np.zeros(s.profile.flows)
    cf[s.cf_flows[0] - s.flow_offset] = s.cf_data[0]
    lca = types.SimpleNamespace(
        technosphere_matrix=s.technosphere(),
        demand_array=demand,
        biosphere_matrix=s.biosphere(),
        characterization_matrix=sparse.diags(cf),
    )
    assert neumann_score(lca, s.scale) == pytest.approx(s.reference[0][0], rel=1e-12)


def test_neumann_score_solves_the_sampled_matrix_not_a_stale_copy():
    """bw2calc 2.5.0's JacobiGMRESLCA kept a copy in ``technosphere_matrix`` that draws never reached."""
    s = system("smoke")
    stale = s.technosphere().tocsr()
    sampled = stale.copy()
    off_diagonal = sampled.tocoo().row != sampled.tocoo().col
    sampled.data[off_diagonal] *= 1.2
    demand = np.zeros(s.profile.products)
    demand[0] = 1.0
    cf = np.zeros(s.profile.flows)
    cf[s.cf_flows[0] - s.flow_offset] = s.cf_data[0]
    biosphere, characterization = s.biosphere(), sparse.diags(cf)
    lca = types.SimpleNamespace(
        technosphere_matrix=stale,
        technosphere_mm=types.SimpleNamespace(matrix=sampled),
        demand_array=demand,
        biosphere_matrix=biosphere,
        characterization_matrix=characterization,
    )
    expected = float((characterization @ biosphere @ sla.spsolve(sampled.tocsc(), demand)).sum())
    assert expected != pytest.approx(s.reference[0][0], rel=1e-3)
    assert neumann_score(lca, s.scale) == pytest.approx(expected, rel=1e-9)
