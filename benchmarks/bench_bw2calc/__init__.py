# NOTE: asv imports this folder as a package but does not install this repo, so the
# shared generator in src/ is put on the path here. Importing bwbench pins BLAS threads.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import bwbench  # noqa: F401
from bwbench.solvers import patch_from_env

# The klu and umfpack-T environments set BWBENCH_SOLVER; bw2calc must be patched before any
# case builds an LCA.
patch_from_env()
