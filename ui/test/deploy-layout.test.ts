import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import { STATIC_PAGES } from "../src/lib/pages";

// e2e/serve.mjs serves dist/ at both / and /ui/, so a static page site.yml leaves out of the
// site root still passes the browser tests. This reads the deploy step's copy list instead.
const workflow = readFileSync(new URL("../../.github/workflows/site.yml", import.meta.url), "utf8");

test.each([...new Set(STATIC_PAGES.map((p) => p.path.split("/")[0]))])(
  "site.yml copies %s/ to the site root",
  (dir) => {
    expect(workflow).toContain(`cp -r ui/dist/${dir} site/${dir}`);
  },
);
