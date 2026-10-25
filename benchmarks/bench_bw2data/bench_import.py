"""bw2data: the time to ``import bw2data`` in a fresh interpreter.

asv runs a ``timeraw_*`` function's returned code in a new Python process for every sample, so
this times a cold import, which the other cases' setups keep out of their samples.
"""


def timeraw_import_bw2data() -> str:
    return "import bw2data"
