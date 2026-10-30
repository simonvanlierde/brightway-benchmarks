import svelte from "@astrojs/svelte";
import { defineConfig } from "astro/config";

// Static output only: the data is read at run time from PUBLIC_DATA_URL, so no server is needed.
export default defineConfig({
  output: "static",
  // The site serves the viewer under a sub-path (UI_BASE, e.g. /brightway-benchmarks/ui/); "/" elsewhere.
  base: process.env.UI_BASE,
  integrations: [svelte()],
});
