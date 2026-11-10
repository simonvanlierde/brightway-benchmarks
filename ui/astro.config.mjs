import svelte from "@astrojs/svelte";
import { defineConfig } from "astro/config";

// Static output only: the data is read at run time from PUBLIC_DATA_URL, so no server is needed.
export default defineConfig({
  output: "static",
  site: "https://simonvanlierde.com",
  // The site serves the viewer under a sub-path (UI_BASE, e.g. /brightway-benchmarks/ui/); "/" elsewhere.
  base: process.env.UI_BASE,
  integrations: [svelte()],
  // GitHub Pages sends no headers, so Astro writes the policy into a <meta> in every page, with
  // a hash for each script and style it emits. The rest is same-origin: the data is read from
  // the site's own /ui/data/, and nothing loads from another origin.
  security: {
    csp: {
      directives: ["default-src 'self'", "object-src 'none'", "base-uri 'self'", "form-action 'none'"],
      // NOTE: ajv builds each schema validator with Function() in the browser (src/lib/contract.ts).
      // Compile them at build time with ajv's standalone mode, then drop 'unsafe-eval'.
      scriptDirective: { resources: ["'self'", "'unsafe-eval'"] },
      // Observable Plot adds two fixed <style> elements to every chart it draws. Their hashes
      // change with the Plot version; e2e/csp.spec.ts prints the new ones when they do.
      styleDirective: {
        hashes: [
          "sha256-jSYQUrW7J0b3jPqhZP9C2Xh1PyJKHKXd4s0fpGGKrww=",
          "sha256-rCZUQsEQJf1DmnfnMZmlj08XC7qbIZySA6bEtitbQ00=",
        ],
      },
    },
  },
});
