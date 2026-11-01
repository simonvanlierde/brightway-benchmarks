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

/** The colour class a check result takes: passed is better, failed or timed out is worse. */
export function statusTone(status: string): "better" | "worse" | undefined {
  if (status === "success") return "better";
  if (status === "failure" || status === "timed_out") return "worse";
  return undefined;
}

export function dateLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("en", { dateStyle: "medium", timeZone: "UTC" }).format(date);
}
