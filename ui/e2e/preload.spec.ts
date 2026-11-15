import { expect, test } from "@playwright/test";

// The island's renderer and component both import the Svelte runtime. Without a preload for each of the three,
// the browser learns of the runtime only after the first two arrive: a round trip on the way to the first draw.
test("the viewer page preloads its island's modules from the HTML", async ({ request }) => {
  const html = await (await request.get("/")).text();
  const preloaded = [...html.matchAll(/<link rel="modulepreload" href="([^"]+)">/g)].map((m) => m[1]);
  const island = [...html.matchAll(/\b(?:component|renderer)-url="([^"]+)"/g)].map((m) => m[1]);
  expect(island).toHaveLength(2);
  expect(preloaded).toEqual(expect.arrayContaining(island));
  expect(preloaded.length).toBeGreaterThan(island.length); // the shared runtime chunk
  // After the stylesheets, so the first paint does not wait for them.
  expect(html.lastIndexOf('rel="stylesheet"')).toBeLessThan(html.indexOf('rel="modulepreload"'));
});
