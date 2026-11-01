import type { Guidance } from "./contract";

export type GuidanceCheck = Guidance["checks"][number];

export function statusLabel(status: string): string {
  return (
    (
      {
        success: "Passed",
        failure: "Failed",
        cancelled: "Cancelled",
        skipped: "Not run",
        timed_out: "Timed out",
      } as Record<string, string>
    )[status] ?? status.replaceAll("_", " ")
  );
}

export function checkKind(kind: GuidanceCheck["kind"]): string {
  return { smoke: "Smoke calculations", suites: "Upstream test suites", diagnostic: "Diagnostic checks" }[kind];
}

export function dateLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("en", { dateStyle: "medium", timeZone: "UTC" }).format(date);
}
