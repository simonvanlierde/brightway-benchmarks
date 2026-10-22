"""bw2calc and stats_arrays: the time to ``import`` each in a fresh interpreter.

asv runs a ``timeraw_*`` function's returned code in a new Python process for every sample, so
these cells time a cold import, which the other cases' setups keep out of their samples.

``stats_arrays`` sits here because bw2calc is what draws from it (Monte Carlo) and the stack
file pins it (``asv/bw2calc.stack.txt``): the cell shows what bw2calc's fixed stack pays for
it. bw2data also depends on it but needs no cell of its own: its import time includes it.
"""


def timeraw_import_bw2calc() -> str:
    return "import bw2calc"


def timeraw_import_stats_arrays() -> str:
    return "import stats_arrays"
