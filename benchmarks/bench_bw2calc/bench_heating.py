"""bw2calc on a home-heating question over BAFU 2025: a heat pump or a gas boiler, in the Netherlands.

``bwbench.heating`` builds the foreground (six nodes) as arrays; each case loads it as an
in-memory datapackage beside BAFU's, so the suite needs no bw2data. The cases run only at
``BWBENCH_SIZES=bafu``, since the foreground names BAFU processes. Every score is checked
against ``heating.reference``, a Neumann series on the same matrices with no Brightway code.
"""

import functools

import bw2calc as bc

from bwbench import DIRECT_RTOL, bafu, check_table, first_time, heating, knob
from bwbench.asv import classes
from bwbench.bench import BenchSetup, NotApplicable, bench
from bwbench.solvers import assert_reached
from bwbench.synth import System, method_name, packages, skip_unless_factorizable, system

SIZES = knob("sizes", "smoke")


@functools.cache
def background(size: str) -> tuple[System, dict[str, int]]:
    """BAFU as arrays, and the matrix index of each process the foreground names."""
    if size != "bafu":
        raise NotApplicable("the heating foreground names BAFU 2025 processes: it runs at BWBENCH_SIZES=bafu")
    s = system(size)
    return s, heating.locate(bafu.archive(), heating.NAMES, s.ids)


def score(lca: bc.LCA) -> float:
    """The score of the last solve, as ``redo_lci`` leaves it."""
    return float((lca.characterization_matrix @ lca.inventory).sum())


def scenario(cop: float, share: float, size: str = "bafu") -> heating.Foreground:
    s, at = background(size)
    return heating.foreground(
        s, at, cop=cop, renewable_share=share, heat_demand_kwh=heating.DEFAULTS["heat_demand_kwh"]
    )


@functools.cache
def multi_reference(size: str) -> list[list[float]]:
    s, at = background(size)
    fg = heating.foreground(s, at, **heating.DEFAULTS)
    return heating.reference(s, fg, [{fg.id(node): 1.0} for node in heating.OPTIONS.values()])


@functools.cache
def sweep_reference(size: str, n: int) -> list[list[float]]:
    """Method 0's score of each option, per scenario, each scenario's foreground solved on its own."""
    s, _ = background(size)
    rows = []
    for cop, share in heating.scenarios(n):
        fg = scenario(cop, share, size)
        rows.append([r[0] for r in heating.reference(s, fg, [{fg.id(o): 1.0} for o in heating.OPTIONS.values()])])
    return rows


@bench({"size": SIZES}, error="relative_error", asv="HeatingMulti", timeout=900)
def heating_scores(size: str) -> BenchSetup:
    """Both options against the three EN 15804 methods with MultiLCA, the foreground loaded beside BAFU."""
    s, at = background(size)
    skip_unless_factorizable(size, pardiso=bc.PYPARDISO, factorizations=2)
    inventory, methods, _, _ = packages(size)
    fg = heating.foreground(s, at, **heating.DEFAULTS)
    config = {"impact_categories": [method_name(i) for i in range(len(methods))]}
    demands = {name: {fg.id(node): 1} for name, node in heating.OPTIONS.items()}

    def run() -> object:
        lca = bc.MultiLCA(
            demands=demands, method_config=config, data_objs=[inventory, heating.datapackage(fg), *methods]
        )
        lca.lci()
        lca.lcia()
        return lca.scores

    def against_reference(scores: dict) -> float:
        assert_reached()
        table = [[float(scores[(method_name(m), name)]) for m in range(len(methods))] for name in demands]
        return check_table(table, multi_reference(size), DIRECT_RTOL, "heating score")

    if first_time("heating_scores", size):  # also the warm-up before the first timed call
        against_reference(run())
    return run, against_reference


@bench(
    {"size": SIZES, "scenarios": knob("scenarios", "4,16", int), "variant": ["rebuild", "redo_lci"]},
    error="relative_error",
    asv="HeatingSweep",
    timeout=1800,
)
def heating_sweep(size: str, scenarios: int, variant: str) -> BenchSetup:
    """Both options' climate change score over a grid of heat pump COP and renewable share.

    ``rebuild``: per scenario, a new foreground datapackage and LCA, factorized once for both
    options. ``redo_lci``: one LCA of the part no scenario changes, factorized once; each
    scenario's electricity comes in through the demand (``heating.scenario_demand``).
    """
    s, at = background(size)
    skip_unless_factorizable(size, pardiso=bc.PYPARDISO, factorizations=scenarios if variant == "rebuild" else 1)
    inventory, methods, _, _ = packages(size)
    method = methods[0]
    grid = heating.scenarios(scenarios)
    options = list(heating.OPTIONS.values())

    if variant == "rebuild":
        foregrounds = [scenario(cop, share, size) for cop, share in grid]

        def run() -> list[list[float]]:
            rows = []
            for fg in foregrounds:
                lca = bc.LCA(demand={fg.id(options[0]): 1}, data_objs=[inventory, heating.datapackage(fg), method])
                lca.lci(factorize=True)
                lca.lcia()
                row = [score(lca)]
                lca.redo_lci({fg.id(options[1]): 1})
                rows.append([*row, score(lca)])
            return rows

    elif variant == "redo_lci":
        fixed = heating.without_grid(heating.foreground(s, at, **heating.DEFAULTS))
        demands = [[heating.scenario_demand(scenario(cop, share, size), o) for o in options] for cop, share in grid]

        def run() -> list[list[float]]:
            lca = bc.LCA(demand=demands[0][0], data_objs=[inventory, heating.datapackage(fixed), method])
            lca.lci(factorize=True)
            lca.lcia()
            rows = []
            for row in demands:
                scores = []
                for demand in row:
                    lca.redo_lci(demand)
                    scores.append(score(lca))
                rows.append(scores)
            return rows

    else:
        raise ValueError(variant)

    def against_reference(rows: list[list[float]]) -> float:
        assert_reached()
        return check_table(rows, sweep_reference(size, scenarios), DIRECT_RTOL, f"heating {variant} score")

    if first_time("heating_sweep", size, scenarios, variant):  # also the warm-up before the first timed call
        against_reference(run())
    return run, against_reference


classes(__name__)
