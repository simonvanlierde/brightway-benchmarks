import { describe, expect, it } from "vitest";
import { ContractError, type Guidance, loadGuidance } from "../src/lib/contract";

const BASE = "https://data.test/viewer/";
const data = (): Guidance => ({
  format_version: 1,
  title: "A tested setup",
  intro: "Evidence for choosing a setup.",
  snapshot: { date: "2026-10-31", run: "https://example.test/runs/7" },
  platforms: [{ id: "linux", label: "Linux", defaultCheck: "latest" }],
  checks: [
    {
      id: "latest",
      platform: "linux",
      python: "3.12",
      label: "Latest",
      kind: "smoke",
      status: "failure",
      coverage: "Small calculations",
      caveats: [],
      run: "https://example.test/runs/7",
      lastPassed: {
        date: "2026-10-30",
        run: "https://example.test/runs/6",
        packages: [{ name: "example-package", version: "1.0" }],
        files: [{ label: "requirements.txt", url: "https://example.test/requirements.txt" }],
        install: "example command",
      },
    },
  ],
});
const serve = (body: unknown): typeof fetch => (async () => new Response(JSON.stringify(body))) as typeof fetch;

describe("loadGuidance", () => {
  it("preserves current failure and prior passing date", async () => {
    const result = await loadGuidance(BASE, serve(data()));
    expect(result?.checks[0]?.status).toBe("failure");
    expect(result?.checks[0]?.lastPassed?.date).toBe("2026-10-30");
  });

  it("returns undefined only when the optional file is absent", async () => {
    await expect(
      loadGuidance(BASE, (async () => new Response("", { status: 404 })) as typeof fetch),
    ).resolves.toBeUndefined();
    await expect(loadGuidance(BASE, (async () => new Response("", { status: 500 })) as typeof fetch)).rejects.toThrow(
      ContractError,
    );
    await expect(
      loadGuidance(BASE, (async () => {
        throw new TypeError("offline");
      }) as typeof fetch),
    ).rejects.toThrow(ContractError);
    await expect(loadGuidance(BASE, (async () => new Response("not json")) as typeof fetch)).rejects.toThrow(
      ContractError,
    );
  });

  it("rejects unsupported versions and broken references", async () => {
    await expect(loadGuidance(BASE, serve({ ...data(), format_version: 2 }))).rejects.toThrow(/format_version/);
    const bad = data();
    if (bad.platforms[0]) bad.platforms[0].defaultCheck = "missing";
    await expect(loadGuidance(BASE, serve(bad))).rejects.toThrow(/defaultCheck/);
    const wrong = data();
    if (wrong.checks[0]) wrong.checks[0].platform = "missing";
    await expect(loadGuidance(BASE, serve(wrong))).rejects.toThrow(/platform/);
  });

  it("rejects executable links but accepts benchmark query links", async () => {
    const bad = data();
    const file = bad.checks[0]?.lastPassed?.files[0];
    if (file) file.url = "javascript:alert(1)";
    await expect(loadGuidance(BASE, serve(bad))).rejects.toThrow(/pattern/);
    const comparison = {
      title: "Solvers",
      context: "Same machine",
      rows: [{ label: "Example", value: 4, unit: "ns", href: "?bench=b&machine=m" }],
    };
    await expect(loadGuidance(BASE, serve({ ...data(), solverComparison: comparison }))).resolves.toBeTruthy();
    if (comparison.rows[0]) comparison.rows[0].href = "data:text/html,bad";
    await expect(loadGuidance(BASE, serve({ ...data(), solverComparison: comparison }))).rejects.toThrow(/pattern/);
  });
});
