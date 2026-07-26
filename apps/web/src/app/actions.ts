"use server";

import { spawn } from "node:child_process";
import path from "node:path";
import { getLastRun } from "@/lib/queries";

/**
 * Kick off a collector run.
 *
 * In AWS (COLLECTOR_LAMBDA_NAME set): async Event invocation of the collector
 * Lambda. Locally: detached spawn of `uv run python -m app` in apps/collector
 * (same command as `just collect`; it inherits MONGODB_URI from this process).
 * We wait only for the process to start (Lambda accept / spawn event), not for
 * the run — the status pill's polling of the runs collection shows completion.
 * A spawn failure (uv missing) returns started:false so the user sees it.
 *
 * Double-run guard: the runs collection's last run started-at (a run logs on
 * completion, so "started recently" means one just landed) plus an in-memory
 * marker for a spawn that has not landed yet.
 */

const COOLDOWN_MS = 2 * 60 * 1000;

let lastTriggeredAt = 0;

export async function triggerCollector(): Promise<{ started: boolean; message: string }> {
  const sinceTrigger = Date.now() - lastTriggeredAt;
  if (sinceTrigger < COOLDOWN_MS) {
    return {
      started: false,
      message: "A refresh is already in flight — the pill updates when it lands.",
    };
  }

  let lastRun = null;
  try {
    lastRun = await getLastRun();
  } catch {
    // If the DB is unreachable the run itself will surface the same problem;
    // let the trigger proceed.
  }
  if (lastRun && Date.now() - new Date(lastRun.started).getTime() < COOLDOWN_MS) {
    return {
      started: false,
      message: `Data is fresh — the last run started less than ${COOLDOWN_MS / 60000} minutes ago.`,
    };
  }

  const lambdaName = process.env.COLLECTOR_LAMBDA_NAME;
  if (lambdaName) {
    const { LambdaClient, InvokeCommand } = await import("@aws-sdk/client-lambda");
    const client = new LambdaClient({});
    await client.send(
      new InvokeCommand({ FunctionName: lambdaName, InvocationType: "Event" }),
    );
  } else {
    const collectorDir = path.resolve(process.cwd(), "..", "collector");
    try {
      // Resolve on the 'spawn' event (process actually started) so a missing
      // uv or exec failure reports as a failure instead of a false success.
      await new Promise<void>((resolve, reject) => {
        const child = spawn("uv", ["run", "python", "-m", "app"], {
          cwd: collectorDir,
          detached: true,
          stdio: "ignore",
          env: process.env as NodeJS.ProcessEnv,
        });
        child.once("spawn", () => {
          child.unref();
          resolve();
        });
        child.once("error", reject);
      });
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      return {
        started: false,
        message: `Couldn't start the local collector (${detail}) — is uv installed?`,
      };
    }
  }

  lastTriggeredAt = Date.now();
  return { started: true, message: "Refresh started — the pill updates when it lands." };
}
