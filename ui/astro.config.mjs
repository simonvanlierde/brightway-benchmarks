import { createHash } from "node:crypto";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import svelte from "@astrojs/svelte";
import { defineConfig } from "astro/config";

// Two things Astro's policy <meta> gets wrong for this site, fixed in every built page:
// - It sits at the end of <head>, after the inline theme script, and a meta policy covers only what
//   comes after it. Move it to just after <meta charset>.
// - Astro hashes the scripts it bundles but not an `is:inline` one, which the policy then blocks.
//   Add the hash of each inline script that runs (a JSON-LD block is data and does not). Only a script
//   marked `data-inline-ok` is hashed: any other inline script that Astro did not hash fails the build, so markup that reaches
//   the static HTML (findings.astro renders markdown) cannot run under the policy.
/** The inline <script> elements of HTML as [opening tag, code]; one with src or type is not code that runs here. */
export function inlineScripts(html) {
  return [...html.matchAll(/(<script(?![^>]*\b(?:src|type)=)[^>]*>)([\s\S]*?)<\/script>/g)].map(([, tag, code]) => [
    tag,
    code,
  ]);
}

export const policy = {
  name: "policy",
  hooks: {
    "astro:build:done": ({ dir }) => {
      const root = fileURLToPath(dir);
      for (const name of readdirSync(root, { recursive: true, encoding: "utf8" })) {
        if (!name.endsWith(".html")) continue;
        const file = `${root}/${name}`;
        const html = readFileSync(file, "utf8");
        const meta = html.match(/<meta http-equiv="content-security-policy"[^>]*>/)?.[0];
        const charset = '<meta charset="utf-8">';
        if (!meta || !html.includes(charset)) throw new Error(`${name}: no policy <meta> or charset <meta> to reorder`);
        const hash = (code) => `'sha256-${createHash("sha256").update(code).digest("base64")}'`;
        // Astro's own scripts (its island loader) already have a hash in the policy; any other unmarked one is refused.
        const inline = inlineScripts(html).filter(
          ([tag, code]) => tag.includes("data-inline-ok") || !meta.includes(hash(code)),
        );
        const unmarked = inline.filter(([tag]) => !tag.includes("data-inline-ok"));
        if (unmarked.length)
          throw new Error(`${name}: inline script without data-inline-ok: ${unmarked[0][1].slice(0, 200)}`);
        const missing = inline.map(([, code]) => hash(code)).filter((h) => !meta.includes(h));
        const fixed = meta.replace("script-src 'self'", () => `script-src 'self' ${missing.join(" ")}`);
        writeFileSync(
          file,
          html
            .replace(meta, () => "")
            .replace(charset, () => charset + fixed)
            .replace("</head>", () => `${modulepreloads(root, html)}</head>`),
        );
      }
    },
  },
};

// An island loads its renderer and component in parallel, and both import the Svelte runtime: the
// browser finds that third chunk only after fetching the first two, a round trip later. Preload all
// three from the HTML, after the stylesheets, so the first paint does not wait for them.
function modulepreloads(root, html) {
  const seen = new Set();
  const walk = (url) => {
    if (seen.has(url)) return;
    seen.add(url);
    const code = readFileSync(`${root}/${url.slice(url.indexOf("/_astro/") + 1)}`, "utf8");
    for (const [, name] of code.matchAll(/(?:^|[;}])import[^"'`;]*?from\s*["'`]\.\/([^"'`]+)["'`]/g))
      walk(`${url.slice(0, url.lastIndexOf("/") + 1)}${name}`);
  };
  for (const [, url] of html.matchAll(/\b(?:component|renderer)-url="([^"]+)"/g)) walk(url);
  return [...seen].map((url) => `<link rel="modulepreload" href="${url}">`).join("");
}

// Static output only: the data is read at run time from PUBLIC_DATA_URL, so no server is needed.
export default defineConfig({
  output: "static",
  site: "https://simonvanlierde.com",
  // The site serves the viewer under a sub-path (UI_BASE, e.g. /brightway-benchmarks/ui/); "/" elsewhere.
  base: process.env.UI_BASE,
  integrations: [svelte(), policy],
  // /findings/ renders docs/findings.md. Shiki would colour code blocks with inline styles the policy blocks.
  markdown: { syntaxHighlight: false },
  // GitHub Pages sends no headers, so Astro writes the policy into a <meta> in every page, with
  // a hash for each script and style it emits. The rest is same-origin: the data is read from
  // the site's own /ui/data/, and nothing loads from another origin.
  security: {
    csp: {
      directives: ["default-src 'self'", "object-src 'none'", "base-uri 'self'", "form-action 'self'"],
      // Observable Plot adds two fixed <style> elements to every chart it draws. Their hashes
      // change with the Plot version. When they do, the chart tests in e2e/csp.spec.ts fail, and the
      // console error they show names the blocked style's new hash.
      // Pagefind's search runs as WebAssembly, which the browser compiles only under 'wasm-unsafe-eval'.
      scriptDirective: { resources: ["'self'", "'wasm-unsafe-eval'"] },
      styleDirective: {
        hashes: [
          "sha256-jSYQUrW7J0b3jPqhZP9C2Xh1PyJKHKXd4s0fpGGKrww=",
          "sha256-rCZUQsEQJf1DmnfnMZmlj08XC7qbIZySA6bEtitbQ00=",
        ],
      },
    },
  },
});
