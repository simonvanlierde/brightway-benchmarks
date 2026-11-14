<script lang="ts">
import { type Snippet, untrack } from "svelte";
import { dateLabel, type GuidanceCheck, statusLabel, statusTone } from "../lib/guidance";

type Manager = "uv" | "pip" | "conda" | "pixi";
const MANAGERS: Manager[] = ["uv", "pip", "conda", "pixi"];
const KEY = "bwbench.manager";

let {
  selected,
  checks,
  platform,
  explicitCheck = false,
  onSelectCheck,
  platformChoice,
  pythonNote,
}: {
  selected: GuidanceCheck;
  checks: GuidanceCheck[];
  platform: string;
  explicitCheck?: boolean;
  onSelectCheck?: (check: GuidanceCheck) => void;
  platformChoice?: Snippet;
  /** The Python probe's one-line summary, with a link to its table. */
  pythonNote?: { text: string; href: string } | undefined;
} = $props();

// A command line's words, each flag kept with the word after it ("-c URL"), so the two wrap together.
function wordsOf(line: string): string[] {
  const out: string[] = [];
  for (const word of line.split(" ")) {
    const last = out.at(-1);
    if (last?.startsWith("-") && !last.includes(" ") && !word.startsWith("-")) out[out.length - 1] = `${last} ${word}`;
    else out.push(word);
  }
  return out;
}

function stored(): Manager {
  try {
    const value = localStorage.getItem(KEY);
    return MANAGERS.includes(value as Manager) ? (value as Manager) : "uv";
  } catch {
    return "uv";
  }
}
// The user's own choice; an explicit check may show another manager without changing it.
let picked = stored();
let manager = $state<Manager>(picked);
function remember(next: Manager) {
  picked = next;
  manager = next;
  copied = "";
  try {
    localStorage.setItem(KEY, next);
  } catch {
    // a private window: the choice lasts for this page only
  }
}

const has = (c: GuidanceCheck, m: Manager) => c.lastPassed?.installs.some((i) => i.manager === m) ?? false;
function sourceFor(next: Manager) {
  return has(selected, next) ? selected : checks.find((c) => c.python === selected.python && has(c, next));
}
const pythons = $derived(
  [...new Set(checks.map((c) => c.python))].sort((a, b) => a.localeCompare(b, "en", { numeric: true })),
);
function choosePython(python: string) {
  const matches = checks.filter((c) => c.python === python);
  const check =
    matches.find((c) => c.label === selected.label) ?? matches.find((c) => c.kind === "smoke") ?? matches[0];
  if (check) onSelectCheck?.(check);
}
function choose(next: Manager) {
  remember(next);
  const check = sourceFor(next);
  if (check && check.id !== selected.id) onSelectCheck?.(check);
}
// An explicit check keeps its own set; changing managers can select another check.
const source = $derived(explicitCheck ? selected : sourceFor(manager));
$effect(() => {
  const check = selected;
  const explicit = explicitCheck;
  untrack(() => {
    copied = "";
    if (!explicit || has(check, picked)) manager = picked;
    else if (!has(check, manager)) manager = check.lastPassed?.installs[0]?.manager ?? manager;
  });
});
const saved = $derived(source?.lastPassed);
const install = $derived(saved?.installs.find((i) => i.manager === manager));
const qualifications = $derived(
  source
    ? [
        source,
        ...checks.filter(
          (c) =>
            c !== source &&
            c.python === source.python &&
            ((source.kind === "smoke" && c.kind === "suites") || (source.kind === "suites" && c.kind === "smoke")),
        ),
      ]
    : [],
);
const projectSetup = $derived(
  source && install
    ? `uv init --no-package --python ${source.python} brightway-project\ncd brightway-project\n${install.command}`
    : "",
);

let copied = $state("");
async function copy(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text);
    copied = `Copied ${what}`;
  } catch {
    copied = "Copy failed; select the command instead";
  }
}
</script>

<section class="install-set" aria-labelledby="install-heading">
  <h2 id="install-heading" tabindex="-1">Install</h2>
  <div class="setup-controls">
    <div class="platform-choice">{@render platformChoice?.()}</div>
    <div class="python-choice">
      <label class="control-label" for="setup-python">Python version</label>
      <select id="setup-python" value={selected.python} onchange={(e) => choosePython(e.currentTarget.value)}>
        {#each pythons as python (python)}<option value={python}>{python}</option>{/each}
      </select>
    </div>
    <div class="manager-choice">
      <label class="control-label" for="setup-manager">Package manager</label>
      <select id="setup-manager" value={manager} onchange={(e) => choose(e.currentTarget.value as Manager)}>
        {#each MANAGERS as m (m)}<option value={m}>{m}</option>{/each}
      </select>
    </div>
  </div>
  {#if pythonNote?.text}<p class="install-note python-note">{pythonNote.text} <a href={pythonNote.href}>All Python versions</a></p>{/if}
  {#if source && saved && install}
    {@const suites = qualifications.find((c) => c.kind === "suites" && c !== source && c.status !== "success")}
    <ul class="result-line" aria-label="Check results on {platform}">
      {#each qualifications as c (c.id)}
        <li><a class={statusTone(c.status)} href={c.run} title="Open the check's run">{statusLabel(c.status)}</a> {c.kind === "smoke" ? "Small test calculations · " : ""}{c.label} · Python {c.python}</li>
      {/each}
    </ul>
    {#if source.status !== "success"}<p class="saved-warning">The latest run of {source.label} did not pass; this is the set that passed on {dateLabel(saved.date)}.</p>{/if}
    {#if source.caveats.length}<ul class="caveats">{#each source.caveats as caveat (caveat)}<li>{caveat}</li>{/each}</ul>{/if}
    <div class="install-command">
      <pre><code>{@render words(install.command)}</code></pre>
      <button type="button" class="copy" onclick={() => copy(install.command, "command")}>Copy</button>
    </div>
    <p class="install-meta">
      Passed {dateLabel(saved.date)}{#if manager === "uv"}, for a uv project that needs Python {source.python} or later{/if}{#if source !== selected}, from the {source.label} check{/if}.
      <span role="status">{copied}</span>
    </p>
    {#if suites}<p class="install-note status-note">{suites.label} did not pass on the latest releases. They run each package's own tests, which cover more than these calculation checks. The command above still stands: it is the last set that passed the {source.label} check.</p>{/if}
    {#if !qualifications.some((c) => c.kind === "suites")}<p class="install-note">No upstream test-suite result is published for this check.</p>{/if}
    <div class="install-details">
    {#if manager === "uv"}
      <details class="new-project">
        <summary>No project yet? Create one</summary>
        <p>With uv installed, run these in the folder where you keep your projects. They create <code>brightway-project</code> with Python {source.python} and add this tested set.</p>
        <div class="install-command"><pre><code>{@render words(projectSetup)}</code></pre><button type="button" class="copy" onclick={() => copy(projectSetup, "project setup")}>Copy project setup</button></div>
      </details>
    {/if}
    <details class="package-pins">
      <summary>What's in this set: {saved.packages.length} packages, files</summary>
      <table aria-label="Tested package versions"><tbody>{#each saved.packages as pkg (pkg.name)}<tr><th scope="row">{pkg.name}</th><td>{pkg.version}</td></tr>{/each}</tbody></table>
      <p class="install-files"><span class="files-label">Files</span> {#each saved.files as file (file.url)}<a href={file.url}>{file.label}</a>{/each}<a href={saved.run}>Passing run</a></p>
      {#if saved.pinned && install.latest}
        {@const latest = install.latest}
        <p class="install-meta">Pinned to {dateLabel(saved.pinned)}. For the same packages unpinned: <button type="button" class="secondary" onclick={() => copy(latest, "latest")}>Copy latest</button></p>
      {/if}
    </details>
    </div>
  {:else if explicitCheck && !selected.lastPassed}
    <p class="no-saved">No passing install set is published for {selected.label} on Python {selected.python}. <a href={selected.run}>Open the check's run</a> or choose another check.</p>
  {:else}
    <p class="no-saved">No {manager} set has passed on {platform} on Python {selected.python}. Choose another package manager or check.</p>
  {/if}
</section>

<!-- Each word in a box of its own, so a line breaks at a space and never inside a flag such as -c. -->
{#snippet words(text: string)}{#each text.split("\n") as line, l (l)}{l ? "\n" : ""}{#each wordsOf(line) as word, i (i)}{i ? " " : ""}<span class="word">{word}</span>{/each}{/each}{/snippet}
