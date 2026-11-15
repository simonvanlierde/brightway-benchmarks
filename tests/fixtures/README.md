# Tiny USEEIO archive

`useeio-tiny.tar.gz` contains fictional processed datapackages written with
bw_processing 1.6. It has three commodities (30, 60, 120), three processes
(7, 50, 90), two emitted flows (500, 700), and three methods (GCC, ACID, ETOX).
The score oracle and all amounts live in `test_useeio.py`. Each method also
contains an unused flow 999, which the loader must drop.

An invalid zip outside `processed/` checks that only processed packages are read.
The same archive is read by a narrow NumPy zip adapter in the host test and by
bw_processing itself in the container integration case.

## Ratio files

`ratios/hosted/2026-11-14/` holds the three files of one hosted `ratios` run (Actions run
43604589027), the real export the comparison page's tests read. Their intervals are recomputed
from the stored times with `bwbench.ratios.ratio_seed`, which came after that run, so
`bwbench validate` passes them.
