"""bwbench.solvers' patch seam, on fake bw2calc modules: no Brightway on the host."""

import sys
import types
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

from bwbench import solvers


def original(*_: object, **__: object) -> None:
    msg = "bw2calc's own solver ran"
    raise AssertionError(msg)


# bw2calc 3.1.0's layout of solver names, plus a module whose name only starts like bw2calc's.
LAYOUT = {
    "bw2calc": ["spsolve", "factorized"],
    "bw2calc.lca_base": ["spsolve", "lu_solver"],
    "bw2calc.multi_lca": [],
    "bw2calc.fast_scores": ["factorized"],
    "bw2calc.fast_supply_arrays": ["lu_solver"],
    "bw2calc_other": ["spsolve"],
}


@pytest.fixture
def fake_bw2calc(monkeypatch: pytest.MonkeyPatch) -> dict[str, types.ModuleType]:
    modules = {}
    for name, attrs in LAYOUT.items():
        module = types.ModuleType(name)
        for attr in attrs:
            setattr(module, attr, original)
        monkeypatch.setitem(sys.modules, name, module)
        modules[name] = module
    monkeypatch.setattr(solvers, "CALLS", [0])
    return modules


def diagonal(a: sparse.spmatrix) -> solvers.Solve:
    """A factorizer for diagonal matrices that, like UMFPACK's, takes one column at a time."""
    d = sparse.csr_matrix(a).diagonal()

    def solve(b: np.ndarray) -> np.ndarray:
        assert b.ndim == 1
        return b / d

    return solve


A = sparse.diags([2.0, 4.0]).tocsr()


def test_every_bw2calc_copy_of_the_names_is_replaced(fake_bw2calc: dict[str, types.ModuleType]):
    solvers.patch(diagonal)
    for name, module in fake_bw2calc.items():
        patched = [a for a in ("spsolve", "factorized", "lu_solver") if getattr(module, a, original) is not original]
        assert patched == ([] if name == "bw2calc_other" else LAYOUT[name]), name


def test_patched_names_solve_and_count(fake_bw2calc: dict[str, types.ModuleType]):
    solvers.patch(diagonal)
    np.testing.assert_allclose(fake_bw2calc["bw2calc"].spsolve(A, np.array([2.0, 4.0])), [1.0, 1.0])
    solve = fake_bw2calc["bw2calc.lca_base"].lu_solver(A, copy=False)
    np.testing.assert_allclose(solve(np.array([[2.0, 4.0, 6.0], [8.0, 8.0, 4.0]])), [[1.0, 2.0, 3.0], [2.0, 2.0, 1.0]])
    assert solvers.CALLS == [2]


def test_a_patched_run_that_never_reached_the_patch_fails(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(solvers, "CALLS", [0])
    monkeypatch.delenv("BWBENCH_SOLVER", raising=False)
    solvers.assert_reached()  # not patched: nothing to reach
    monkeypatch.setenv("BWBENCH_SOLVER", "klu")
    with pytest.raises(AssertionError, match="never called the patched klu"):
        solvers.assert_reached()
    solvers.CALLS[0] = 1
    solvers.assert_reached()


def test_an_unknown_solver_is_refused(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BWBENCH_SOLVER", "kluu")
    with pytest.raises(ValueError, match="kluu"):
        solvers.patch_from_env()
    monkeypatch.delenv("BWBENCH_SOLVER")
    assert solvers.patch_from_env() is None


def test_by_column_solves_each_column_of_a_2d_right_hand_side():
    a = np.array([[2.0, 0.0], [1.0, 4.0]])

    def one_column(b: np.ndarray) -> np.ndarray:
        assert b.ndim == 1  # UMFPACK's and KLU's solves take one column
        return np.linalg.solve(a, b)

    solve = solvers.by_column(one_column)
    b = np.array([[2.0, 4.0], [9.0, 6.0]])
    np.testing.assert_allclose(solve(b), np.linalg.solve(a, b))
    np.testing.assert_allclose(solve(np.array([2.0, 9.0])), [1.0, 2.0])


def test_accelerate_off_macos_is_not_applicable(monkeypatch: pytest.MonkeyPatch):
    """Timecase turns NotImplementedError into the arm's missing reason."""
    monkeypatch.setattr(sys, "platform", "linux")
    solvers.accelerate_library.cache_clear()
    with pytest.raises(NotImplementedError, match="macOS only"):
        solvers.accelerate(A)


@pytest.mark.skipif(sys.platform == "win32", reason="shell-script stand-in")
def test_accelerate_names_the_compile_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """An SDK without SparseFactorizationLU: the reason is cc's error line, not its last line."""
    (tmp_path / "accelerate.c").write_text("")
    cc = tmp_path / "bin" / "cc"
    cc.parent.mkdir()
    cc.write_text(
        "#!/bin/sh\necho \"accelerate.c:23:23: error: use of undeclared identifier 'SparseFactorizationLU'\" >&2\n"
        "echo '1 error generated.' >&2\nexit 1\n"
    )
    cc.chmod(0o755)
    monkeypatch.setenv("PATH", str(cc.parent))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(solvers, "ACCELERATE_C", tmp_path / "accelerate.c")
    solvers.accelerate_library.cache_clear()
    with pytest.raises(
        RuntimeError, match=r"cc could not build accelerate.c: .*undeclared identifier 'SparseFactorizationLU'"
    ):
        solvers.accelerate_library()
    assert not list(tmp_path.glob("*.dylib")) + list(tmp_path.glob("*.tmp"))
    solvers.accelerate_library.cache_clear()


def test_accelerate_is_a_patchable_solver():
    assert "accelerate" in solvers.FACTORIZERS
