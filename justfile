# Task runner: https://just.systems. `just` lists the recipes, `just <name>` runs one.
#
# `import?` skips a recipe file you did not scaffold. Recipes are prefixed
# (`py-`, `ts-`, `rs-`, `go-`) because imports share one namespace, except the few only
# one kind has, such as `pipeline` or `up`.
import? 'just/python.just'
import? 'just/ts.just'
import? 'just/rust.just'
import? 'just/go.just'
import? 'just/docker.just'

# List the recipes (what a bare `just` runs).
default:
    @just --list

# The stack checks CI runs. `just hooks` runs the git hooks, which CI also runs.
check:
    @just py-check

# Fix and format every stack here, as each stack's `fmt` recipe does.
fmt:
    @just py-fmt

# Run every git hook over the whole repo, not just staged files. The checks workflow skips
# the hooks in its SKIP list, which the stack workflows run instead. Here they all run, so
# this can fail where the checks workflow passes.
hooks:
    prek run -a

# --- benchmarks --------------------------------------------------------------
# Everything below runs in the benchmark box, a throwaway `tmp-bwbench-*` container
# (docs/assurance-case.md). docs/running.md lists the BWBENCH_* variables.

# A rerun skips what already succeeded, so a backfill that stopped partway picks up where it
# was, if BWBENCH_MACHINE (or the CPU slot that names the machine, as box-e0) is the same.
# Extra arguments reach `asv run`, e.g. `just bench bw2calc "" -e` to show each check's message.
# Benchmark SUBJECT over its releases (asv/SUBJECT.hashes), or over RANGE (an asv range).
bench subject range="" *args:
    scripts/box.sh scripts/asv.sh {{ subject }} run --skip-existing-successful {{ args }} {{ if range == "" { "HASHFILE:/src/asv/" + subject + ".hashes" } else { quote(range) } }}

# After a generator version bump: only the newest release of each minor line (scripts/minor_lines.py).
bench-lines subject *args:
    mkdir -p .asv
    python3 scripts/minor_lines.py {{ subject }} > .asv/{{ subject }}.lines.hashes
    scripts/box.sh scripts/asv.sh {{ subject }} run --skip-existing-successful {{ args }} HASHFILE:/src/.asv/{{ subject }}.lines.hashes

# Proves the harness, not the numbers. Results go to .asv/smoke/, never to results/ or the site.
# One quick pass per subject at its oldest and latest release, smoke size, and a bw2io import of
# the smoke system written as ecoSpold2 files; fails on any failure.
smoke:
    #!/usr/bin/env bash
    set -uo pipefail
    status=0
    for conf in asv/*.json; do
      s=$(basename "$conf" .json)
      rm -rf ".asv/smoke/$s"
      for release in $( (head -n 1; tail -n 1) <"asv/$s.hashes" | uniq); do
        BWBENCH_MACHINE=smoke scripts/box.sh scripts/asv.sh "$s" run --quick --show-stderr "$release^!" || { echo "$s $release: exit $?"; status=1; }
      done
    done
    python3 scripts/check_smoke.py .asv/smoke || status=1
    # bw2io's import of the generated ecoSpold2 release, which must link every exchange.
    just bw2io-import synthetic smoke || { echo "bw2io-import: exit $?"; status=1; }
    exit $status

# Results go to .asv/noise/, never to results/ or the site. Sizes come from BWBENCH_* as usual.
# Short cases need the CPU's performance power profile (Linux: powerprofilesctl set performance).
# Each sample's CPU time, wall time and involuntary context switches go to rounds.jsonl beside them.
# Run-to-run noise: RUNS separate quick runs of SUBJECT's latest release, then each case's spread.
noise subject runs="10":
    #!/usr/bin/env bash
    set -uo pipefail
    last=$(tail -n 1 "asv/{{ subject }}.hashes")
    rm -rf ".asv/noise/{{ subject }}"
    for i in $(seq {{ runs }}); do
      echo "noise: run $i of {{ runs }}" >&2
      # A failed case fails the run, but the other cases' samples still count. asv's output goes
      # to stderr, so stdout carries only the summary below.
      BWBENCH_MACHINE=noise BWBENCH_ROUNDLOG="/src/.asv/noise/{{ subject }}/rounds.jsonl" scripts/box.sh scripts/asv.sh {{ subject }} run --quick --append-samples "$last^!" >&2 ||
        echo "noise: run $i exited $?" >&2
    done
    uv run --no-project --with numpy==2.5.3 python scripts/noise_summary.py ".asv/noise/{{ subject }}"

# After a new upstream release, follow docs/running.md ("Add a release").
# Resolve SUBJECT's fixed stack (its latest release's dependencies at the cutoff) into asv/.
stack subject:
    scripts/box.sh scripts/stack.sh {{ subject }}
    test ! -L ".asv/stack/{{ subject }}.txt"  # the box wrote it: never copy through a link
    cp ".asv/stack/{{ subject }}.txt" "asv/{{ subject }}.stack.txt"

# Results go to .asv/stack/. Failing cases are expected on old releases; the table is the signal.
# Every release of SUBJECT once at smoke size on its fixed stack, then which cases pass per release.
stack-check subject:
    rm -rf ".asv/stack/{{ subject }}"
    -BWBENCH_MACHINE=stack scripts/box.sh scripts/asv.sh {{ subject }} run --quick "HASHFILE:/src/asv/{{ subject }}.hashes"
    python3 scripts/release_report.py {{ subject }}

# Tags resolve through asv's clone of the upstream repository in .asv/SUBJECT, which `just bench` makes.
# Cases that moved beyond their noise between SUBJECT's newest two releases in results/, as Markdown.
release-changes subject:
    python3 scripts/release_changes.py {{ subject }} results

# Today's PyPI releases of the Brightway set on PYTHON, then every case once at smoke size.
# COLUMN: latest, floors, pre, conda-forge or suites (docs/running.md, "Compat").
# 6g: every suite shares one pytest process here, not one process per case as under asv.
compat python="3.13" column="latest":
    BWBENCH_TARGET={{ if column == "conda-forge" { "conda" } else { "box" } }} BWBENCH_MEM=${BWBENCH_MEM:-6g} scripts/box.sh scripts/compat.sh {{ python }} {{ column }}

# Build the static site in site/, around the viewer the site workflow adds: the compat archive (the
# `compat` branch, which the compat workflow writes) and redirects from the old asv pages.
site:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p site
    [ ! -d profiles ] || { mkdir -p site/profiles && cp -r profiles/. site/profiles/; }
    if git fetch --quiet origin compat 2>/dev/null; then git archive FETCH_HEAD compat | tar -x -C site
    else echo "no compat branch yet, so the site has no setup guidance" >&2
    fi
    for conf in asv/*.json; do
      s=$(basename "$conf" .json)
      # `just ui-data` reads release tags from asv's mirror; commits and tags are enough.
      repo=$(python3 scripts/asv_conf.py repo "$s")
      [ -d ".asv/$s" ] || git clone --quiet --bare --filter=tree:0 "$repo" ".asv/$s"
      # Old links into asv's pages: SUBJECT/index.html#NAME opens NAME's history in the viewer.
      mkdir -p "site/$s"
      printf '%s\n' '<!doctype html><meta charset="utf-8"><title>Moved</title>' \
        "<script>location.replace('../?page=explorer&group=$s'+(location.hash.length>1?'&bench='+encodeURIComponent(location.hash.slice(1).split('?')[0]):''))</script>" \
        '<p>The benchmark histories have moved to <a href="../?page=explorer">the explorer</a>.</p>' >"site/$s/index.html"
    done
    # The old landing page's anchors (#works-together, #latest-release) still mean something to the viewer.
    printf '%s\n' '<!doctype html><meta charset="utf-8"><title>Moved</title>' \
      "<script>location.replace(location.hash ? './' + location.hash : './?page=explorer')</script>" \
      '<p>The benchmark histories have moved to <a href="./?page=explorer">the explorer</a>.</p>' >site/asv.html

# Build the viewer and serve it on 127.0.0.1:PORT with the committed real data, to look at a UI
# change (a PR checked out with `gh pr checkout`). From a laptop: ssh -L PORT:localhost:PORT HOST.
ui-serve port="4400":
    # A local look only, so the host's pnpm may stand in for the pinned one (CI uses the pin).
    cd ui && export npm_config_manage_package_manager_versions=false && pnpm install --frozen-lockfile && pnpm run build && node e2e/serve.mjs {{ port }}

# Write the UI's data from results/ to OUT (scripts/export_ui.py says what it reads), and the setup
# guidance from site/compat/status.json, which `just site` fetches; without it there is none.
# Needs uv: change points come from Apache Otava, in an environment of its own.
ui-data out:
    python3 scripts/export_ui.py results {{ out }}
    python3 scripts/export_guidance.py site/compat/status.json {{ out }}

# Commit results/ to the local `results` branch for the site; refuses results that name this host.
results-commit:
    scripts/results-commit.sh

# bw2calc's own lci() with one sparse solver: superlu, umfpack, pypardiso, umfpack-T or klu.
# 12 GB by default on plain docker: SuperLU on A at the ecoinvent size needs several.
solver-lci solver size="smoke" bw2calc="3.1.0":
    BWBENCH_MEM="${BWBENCH_MEM:-12g}" scripts/box.sh sh -c 'PYTHONPATH=src uv run -q --no-project --python 3.13 --with bw2calc=={{ bw2calc }} --with threadpoolctl==3.7.0 --with pypardiso==0.4.7 --with scikit-umfpack==0.4.2 --with pyklu==0.2.0 python scripts/solver_lci.py {{ solver }} {{ size }}'

# RELEASE: a licensed release folder (holding datasets/ and MasterData/), mounted read-only, with
# dataset counts or `all` as SIZES (3000,all); or `synthetic`, with profiles as SIZES (smoke,ecoinvent).
# 8 GB by default: a full import peaks at about 4.5 GB.
# Time and peak memory of an ecoinvent import with bw2io 0.9.17 and bw2data 4.8, a fresh process per size.
bw2io-import release sizes:
    #!/usr/bin/env bash
    set -euo pipefail
    run='PYTHONPATH=src uv run -q --no-project --python 3.13 --with bw2io==0.9.17 --with bw2data==4.8 python scripts/bw2io_import.py'
    export BWBENCH_MEM="${BWBENCH_MEM:-8g}"
    if [ {{ quote(release) }} = synthetic ]; then
      exec scripts/box.sh sh -c "$run synthetic {{ quote(sizes) }}"
    fi
    # box.sh mounts only this repo, so a licensed release needs a plain docker run of its image.
    image=$(scripts/box.sh --image)
    exec docker run --rm -i --init --name "tmp-bwbench-$$" --user "$(id -u):$(id -g)" --cap-drop ALL \
      --security-opt no-new-privileges --pids-limit 4096 --memory "$BWBENCH_MEM" --memory-swap "$BWBENCH_MEM" \
      --cpus "${BWBENCH_CPUS:-2}" \
      -v "$PWD":/src:ro -v "$PWD/.asv":/src/.asv -v "$(realpath {{ quote(release) }})":/ecoinvent:ro -w /src \
      "$image" scripts/in-box.sh sh -c "$run /ecoinvent {{ quote(sizes) }}"

# A SQLite project against sentier-brightway's Parquet registry (the format of bw2data #290, which
# stays outside bw2data). size: smoke | ecoinvent; solver: superlu | pypardiso.
registry-vs-sqlite size="smoke" solver="superlu":
    scripts/box.sh sh -c 'PYTHONPATH=src uv run -q --no-project --python 3.13 --with "sentier-brightway @ git+https://github.com/sentier-dev/sentier-brightway@adacaf9" --with bw2data==4.8 --with bw2calc==3.1.0 --with threadpoolctl==3.7.0 {{ if solver == "pypardiso" { "--with pypardiso==0.4.7" } else if solver == "superlu" { "" } else { error("solver: superlu or pypardiso") } }} --with duckdb==1.5.6 python scripts/registry_vs_sqlite.py {{ size }}'

# Docker's default seccomp profile (moby/profiles at TAG; v0.2.4 is Docker 29.9's) plus one rule
# allowing personality(ADDR_NO_RANDOMIZE), so `setarch -R` can turn address randomization off.
# Rewrite docker/seccomp-noaslr.json, the profile box.sh gives the codspeed box.
seccomp-profile tag="seccomp/v0.2.4":
    curl -fsSL "https://raw.githubusercontent.com/moby/profiles/{{ tag }}/seccomp/default.json" | jq '.syscalls = [{"names": ["personality"], "action": "SCMP_ACT_ALLOW", "args": [{"index": 0, "value": 262144, "op": "SCMP_CMP_EQ"}]}] + .syscalls' >docker/seccomp-noaslr.json

# CodSpeed counts instructions, not seconds, so a busy machine changes nothing. Profiles go to
# .asv/codspeed/SUBJECT/; nothing is uploaded. Smoke size unless BWBENCH_SIZES says otherwise.
# One suite under pytest-codspeed's CPU simulation; extra packages (a solver) come on top.
codspeed subject *packages:
    BWBENCH_TARGET=codspeed BWBENCH_SIZES="${BWBENCH_SIZES:-smoke}" scripts/box.sh scripts/codspeed.sh {{ subject }} {{ packages }}

# Profile one case under pyinstrument, as `just profile bw2calc first_score release=3.0.0
# with=scikit-umfpack size=ecoinvent cls=IterativeLCA`: release= and with= pick the environment
# (the latest release, and bw2calc's SuperLU, when left out), NAME=VALUE the parameters. HTML and speedscope
# JSON go to .asv/profiles/.
profile subject case *args:
    scripts/box.sh scripts/profile.sh {{ subject }} {{ case }} {{ args }}

# Rewrite codemeta.json to agree with CITATION.cff, then check. The writer
# exits 1 whenever it changes a file, so the check that follows decides the result.
citation:
    -prek run citesync-write --hook-stage manual --all-files
    prek run citesync --all-files

# Release X.Y.Z. First run: cut CHANGELOG's [Unreleased] into [X.Y.Z] and commit it; merge that to main. Second run, on up-to-date main: sign and push tag vX.Y.Z.
release version:
    #!/usr/bin/env bash
    set -euo pipefail
    version={{ version }}
    [[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "not a version: $version" >&2; exit 1; }
    tag=v$version
    repo=https://github.com/simonvanlierde/brightway-benchmarks
    # The release workflow refuses a tag that differs from pyproject.toml, after the tag exists.
    grep "^version = \"$version\"$" pyproject.toml >/dev/null ||
        { echo "set version = \"$version\" in pyproject.toml (and uv.lock) first" >&2; exit 1; }
    # citesync fails while the manifests and citation files disagree. Run it before any file changes.
    prek run citesync --all-files
    git fetch --quiet origin main
    # Not grep -q: it stops reading early, and under pipefail git show then fails on a
    # changelog bigger than the pipe buffer.
    if git show origin/main:CHANGELOG.md | grep "^## \[$version\] - " >/dev/null; then
        .github/scripts/tag-release.sh "$version"
        exit 0
    fi
    prev=$(sed -n 's/^## \[\([0-9][0-9.]*\)\].*/\1/p' CHANGELOG.md | head -1)
    if [ -n "$prev" ]; then link=$repo/compare/v$prev...$tag; else link=$repo/releases/tag/$tag; fi
    tmp=$(mktemp)
    trap 'rm -f "$tmp"' EXIT
    awk -v v="$version" -v d="$(date +%F)" -v repo="$repo" -v link="$link" '
        /^## \[Unreleased\]/ && !h { print; print ""; print "## [" v "] - " d; h = 1; next }
        /^\[Unreleased\]: / { print "[Unreleased]: " repo "/compare/v" v "...HEAD"; print "[" v "]: " link; l = 1; next }
        { print }
        END { if (!h) exit 1; if (!l) { print ""; print "[Unreleased]: " repo "/compare/v" v "...HEAD"; print "[" v "]: " link } }
    ' CHANGELOG.md >"$tmp" || { echo "CHANGELOG.md has no [Unreleased] section" >&2; exit 1; }
    # The same section the release workflow takes as notes; an empty one would publish none.
    awk -v head="## [$version]" '/^## \[/ { if (on) exit; on = index($0, head) == 1; next } on && NF' "$tmp" | grep . >/dev/null ||
        { echo "[Unreleased] has no entries to release" >&2; exit 1; }
    cp "$tmp" CHANGELOG.md
    git add CHANGELOG.md
    git commit -s -m "chore: release $version" -- CHANGELOG.md
    echo "Merge this commit to main, then run: just release $version"

# Protect the default branch (no deletion, no force-push, linear history, PRs squash-merged after the always-on checks pass and one approval) and the v* tags. Turn on private vulnerability reporting, CodeQL default setup and Dependabot alerts. Safe to rerun.
repo-settings:
    #!/usr/bin/env bash
    set -euo pipefail
    err=$(mktemp)
    trap 'rm -f "$err"' EXIT
    fail() {
        cat "$err" >&2
        grep -qE 'HTTP (403|404)' "$err" && echo "Rulesets on a private repo need a paid GitHub plan (or the repo does not exist, or you lack admin rights)." >&2
        grep -q 'must be part of the ruleset source' "$err" && echo "The main ruleset lets the Renovate app bypass the review, and GitHub accepts that only once the app is installed on this repo: add it at https://github.com/apps/renovate, then rerun." >&2
        exit 1
    }
    # Merge-method switches live on the repo itself; the ruleset also limits the PR button.
    gh api -X PATCH repos/{owner}/{repo} -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false -F delete_branch_on_merge=true -F web_commit_signoff_required=true >/dev/null 2>"$err" || fail
    # Adopt an existing ruleset by name, else one with the same target that protects the same
    # refs as the file, updating it in place. The list has no conditions, so each candidate is read.
    for name in main main-checks tags; do
        file=.github/rulesets/$name.json
        case "$name" in
            main) want='["~DEFAULT_BRANCH"]' filter='.[] | select(.target == "branch" and (.name | test("checks?") | not)) | .id' ;;
            main-checks) want='["~DEFAULT_BRANCH"]' filter='.[] | select(.target == "branch" and (.name | test("checks?"))) | .id' ;;
            tags) want='["refs/tags/v*"]' filter='.[] | select(.target == "tag") | .id' ;;
        esac
        id=$(gh api "repos/{owner}/{repo}/rulesets?includes_parents=false" --jq "first(.[] | select(.name == \"$name\") | .id) // empty" 2>"$err") || fail
        if [ -z "$id" ]; then
            candidates=$(gh api "repos/{owner}/{repo}/rulesets?includes_parents=false" --jq "$filter" 2>"$err") || fail
            for candidate in $candidates; do
                same=$(gh api "repos/{owner}/{repo}/rulesets/$candidate" --jq ".conditions.ref_name.include == $want" 2>"$err") || fail
                if [ "$same" = true ]; then
                    id=$candidate
                    break
                fi
            done
        fi
        if [ -n "$id" ]; then
            gh api -X PUT "repos/{owner}/{repo}/rulesets/$id" --input "$file" >"$err" 2>&1 || fail
            echo "Updated ruleset '$name' ($id)."
        else
            # gh prints GitHub's reason for a refusal on stdout, so fail() needs both.
            gh api -X POST repos/{owner}/{repo}/rulesets --input "$file" >"$err" 2>&1 || fail
            echo "Created ruleset '$name'."
        fi
    done
    # SECURITY.md sends reports to a private security advisory, which this turns on.
    gh api -X PUT repos/{owner}/{repo}/private-vulnerability-reporting >/dev/null 2>"$err" || fail
    echo "Turned on private vulnerability reporting."
    # CodeQL default setup scans every PR and push to main.
    if gh api -X PATCH repos/{owner}/{repo}/code-scanning/default-setup -f state=configured >"$err" 2>&1; then
        echo "Turned on CodeQL default setup."
    else
        echo "Warning: CodeQL default setup could not be turned on, so code scanning stays off: $(cat "$err")" >&2
    fi
    # Dependabot alerts let Renovate open security PRs and turn on the dependency graph.
    gh api -X PUT repos/{owner}/{repo}/vulnerability-alerts >/dev/null 2>"$err" || fail
    echo "Turned on Dependabot alerts."
    echo "Zenodo: https://zenodo.org/account/settings/github/"

# Set the GitHub About box from your answers: description and a topic per stack. Adds topics, never removes yours. Safe to rerun.
repo-about:
    gh repo edit --description 'Continuous benchmarks for the Brightway LCA stack on seeded synthetic matrices' --add-topic python

# A repo's own recipes that copier updates never touch:
import? 'just/local.just'
