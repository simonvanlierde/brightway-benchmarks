import svelte from "@astrojs/svelte";
import { defineConfig } from "astro/config";

// Static output only: the data is read at run time from PUBLIC_DATA_URL, so no server is needed.
export default defineConfig({
  output: "static",
  integrations: [svelte()],
});
