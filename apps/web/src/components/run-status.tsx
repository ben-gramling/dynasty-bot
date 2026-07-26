"use client";

import { useEffect, useState } from "react";
import type { CollectorRun } from "@/lib/queries";
import { fmtAge, fmtDateTime } from "@/lib/format";

const POLL_MS = 15_000;

/**
 * Last-collector-run pill. Server renders the initial state (real data in the
 * first HTML byte); the client then polls /api/run-status so a Refresh shows
 * up without a reload. The age text carries suppressHydrationWarning — server
 * and client clocks can straddle a minute boundary.
 */
export function RunStatus({ initialRun }: { initialRun: CollectorRun | null }) {
  const [run, setRun] = useState<CollectorRun | null>(initialRun);
  const [now, setNow] = useState<Date>(() => new Date());

  useEffect(() => {
    const tick = () => {
      fetch("/api/run-status", { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((data: { run: CollectorRun | null } | null) => {
          if (data) setRun(data.run);
          setNow(new Date());
        })
        .catch(() => setNow(new Date()));
    };
    const id = setInterval(tick, POLL_MS);
    return () => clearInterval(id);
  }, []);

  if (!run) {
    return (
      <span className="pill" role="status">
        <span className="pill-dot is-stale" aria-hidden />
        No collector run yet — hit Refresh
      </span>
    );
  }

  const failed = !run.ok;
  return (
    <span className="pill" role="status" title={`Run started ${fmtDateTime(run.started)}`}>
      <span className={`pill-dot${failed ? " is-error" : ""}`} aria-hidden />
      {failed ? (
        <span suppressHydrationWarning>
          Last run failed {fmtAge(run.started, now)} — hit Refresh to retry
        </span>
      ) : (
        <span suppressHydrationWarning>
          {/* Mobile masthead collapses the pill to dot + age (design plan §3). */}
          <span className="hidden sm:inline">{"Data "}</span>
          <span className="num">{fmtAge(run.started, now)}</span>
        </span>
      )}
    </span>
  );
}
