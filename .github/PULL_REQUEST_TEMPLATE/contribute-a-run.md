<!-- rumdl-disable MD041 -->
<!-- Title: `feat(ratios): add <machine> run of <date>`. docs/running.md "Contribute a run" has the steps. -->

The machine: what it is (laptop, desktop, workstation), its memory, and whether it ran on mains
power in its performance mode.

- [ ] One file per run, at `ratios/contributed/<machine>/<YYYY-MM-DD>.json`.
- [ ] `bwbench validate --contribution` exits 0 on it.
- [ ] I read the file, and it names no host, user or folder of mine.
- [ ] My commits are signed off (`git commit -s`).

Command: the `bwbench compare` line I ran, flags included.

Anything odd during the run (other load, thermal throttling, an arm that failed to install):
