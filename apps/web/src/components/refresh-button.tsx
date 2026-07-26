"use client";

import { useEffect, useState, useTransition } from "react";
import { triggerCollector } from "@/app/actions";

/**
 * Kicks off a collector run via the server action. Completion shows up in the
 * status pill (it polls the runs collection) — this button only starts the run.
 */
export function RefreshButton() {
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!message) return;
    const id = setTimeout(() => setMessage(null), 6000);
    return () => clearTimeout(id);
  }, [message]);

  function onClick() {
    setMessage(null);
    startTransition(async () => {
      try {
        const result = await triggerCollector();
        setMessage(result.message);
      } catch {
        setMessage("Refresh failed to start — check the server logs.");
      }
    });
  }

  return (
    <span className="relative inline-flex items-center gap-2">
      <button
        type="button"
        onClick={onClick}
        disabled={pending}
        className="rounded-md border border-sky-deep bg-surface px-3 py-1.5 text-[12.5px] font-medium text-sky-deep transition-colors hover:bg-chip disabled:opacity-60"
      >
        {pending ? "Starting…" : "Refresh"}
      </button>
      <span role="status" aria-live="polite" className="sr-only">
        {message ?? ""}
      </span>
      {message ? (
        <span className="absolute top-full right-0 z-10 mt-1 w-56 rounded-md border border-line bg-surface p-2 text-[11.5px] text-ink-muted shadow-sm">
          {message}
        </span>
      ) : null}
    </span>
  );
}
