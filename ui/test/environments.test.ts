import { describe, expect, it } from "vitest";
import type { BenchmarkIndex } from "../src/lib/contract";
import { envNotes, solverLinks } from "../src/lib/environments";
import type { Line } from "../src/lib/history";

const env = (id: string, extra: object = {}) => ({ id, group: "g", name: id, ...extra });
const index = {
  environments: [
    env("a", { label: "PARDISO", description: "PARDISO: an experimental solver", url: "https://p.test" }),
    env("b", { label: "PARDISO", description: "PARDISO: an experimental solver", url: "https://p.test" }),
    env("c", { description: "Runs on the default stack" }),
    env("d", { label: "UMFPACK, MKL", url: "https://u.test" }),
    env("e", { label: "UMFPACK on Linux", url: "https://u.test" }),
    env("f", { label: "SuperLU", url: "https://s.test" }),
    env("g"),
  ],
} as unknown as BenchmarkIndex;
const shown = (...ids: string[]) => ids.map((env) => ({ env }) as Line);

describe("envNotes", () => {
  it("gives each description once and drops the name it starts with", () => {
    expect(envNotes(index, shown("a", "b", "c"))).toEqual([
      { name: "PARDISO", text: "an experimental solver", url: "https://p.test" },
      { name: "c", text: "Runs on the default stack", url: undefined },
    ]);
  });

  it("is empty for environments without a description, or without an index", () => {
    expect(envNotes(index, shown("d", "g"))).toEqual([]);
    expect(envNotes(undefined, shown("a"))).toEqual([]);
  });
});

describe("solverLinks", () => {
  it("links each solver page once, by the name before a comma or 'on'", () => {
    expect(solverLinks(index, shown("d", "e", "f", "g"), [])).toEqual([
      { url: "https://u.test", label: "UMFPACK" },
      { url: "https://s.test", label: "SuperLU" },
    ]);
  });

  it("leaves out a page a note already links", () => {
    const notes = envNotes(index, shown("a"));
    expect(solverLinks(index, shown("a", "f"), notes)).toEqual([{ url: "https://s.test", label: "SuperLU" }]);
  });
});
