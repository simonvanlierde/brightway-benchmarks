# Calibrating activity families

Generator v5 keeps regional variants of an activity in one family. Members copy the family's
supplier list. A supplier with a member in the consumer's region can be replaced by that
member. Members that nobody buys from sell to a later regional market or its global member.
This keeps shared input lists that degree distributions alone do not describe.

Family sizes use fixed quantiles of a capped Zipf distribution. Input counts use rounded
lognormal quantiles within bands of similar family size, each spanning a factor of two.
The generator shuffles both sets of quantiles. These are finite empirical distributions:
a band's population limits its tails, and a band with one family gets the median input
count. Only the declared `ecoinvent` size is calibrated. Other sizes scale the recipe.

The fitted settings retain their full precision. Rounding a setting can move an input count
across an integer boundary and change later random draws. The smoke hash and four-seed
calibration tests protect that boundary.

## Choosing the search

We compared candidates on seeds 0 to 3 using Bayesian optimisation, population search and
targeted checks. Errors were scaled by the existing test tolerances. For the integer consumer
q90 guard, a continuous guide measured the share of suppliers with at least 12 consumers.
This resolved a search plateau without changing any acceptance threshold. Candidates also
needed mean METIS fill and an actual SuperLU COLAMD factorization of Aᵀ to pass.

[Gutmann and Corander](https://www.jmlr.org/papers/v17/15-017.html) use a surrogate of simulator
discrepancy to choose evaluations adaptively.
[Common random numbers](https://arxiv.org/abs/1910.09259) support comparisons on fixed seeds.
Neither guarantees that a generator can meet its targets. A neural posterior was unnecessary:
the required output was one passing configuration.

[Ng et al. (2026)](https://arxiv.org/html/2608.03716v1) generate synthetic supply networks and
adaptively fit weights on a fixed graph. Their method supports staged calibration, but does
not establish LCI supplier overlap or sparse-factorization fill.

## Keeping fill explicit

[Small recursive separators help control sparse-factorization fill](https://simons.berkeley.edu/sites/default/files/docs/787/gilbertslides.pdf).
Matching degrees or sector shares alone does not establish realistic solver workloads.
A [microcanonical stochastic block model](https://arxiv.org/abs/1610.02703) can preserve
specified degrees and block constraints, but these do not prescribe shared supplier lists
or elimination fill. No measured improvement justified replacing the family construction
with another block model or an ERGM.

`tests/test_measure.py` is the acceptance check. It checks structural statistics over seeds
0 to 3, mean loop and negative-input shares, mean METIS fill, and COLAMD fill on Aᵀ.
`scripts/calibration_sweep.py` records per-seed statistics and factorization results; a passing
sweep alone does not establish the fill or across-seed mean checks. Input magnitudes remain
less dispersed than the calibration data, so passing these guards does not reproduce every
property of a real database.
