"""bw2calc: the time to ``import`` it in a fresh interpreter.

asv runs a ``timeraw_*`` function's returned code in a new Python process for every sample, so
this cell times a cold import, which the other cases' setups keep out of their samples.
"""


def timeraw_import_bw2calc() -> str:
    return "import bw2calc"
