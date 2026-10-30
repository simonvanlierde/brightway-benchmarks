import { defineConfig } from "@playwright/test";

// The built site, with the real fixture data (test/fixtures/real, from `just ui-data`) at data/ (e2e/serve.mjs).
// E2E_PORT lets parallel runs on one host keep their own server.
const port = Number(process.env.E2E_PORT ?? 4417);

export default defineConfig({
  testDir: "e2e",
  reporter: process.env.CI ? "github" : "list",
  use: { baseURL: `http://127.0.0.1:${port}/`, browserName: "chromium" },
  webServer: {
    command: `node e2e/serve.mjs ${port}`,
    url: `http://127.0.0.1:${port}/`,
    reuseExistingServer: !process.env.CI,
  },
});
