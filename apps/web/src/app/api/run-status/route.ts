import { NextResponse } from "next/server";
import { getLastRun } from "@/lib/queries";

export const dynamic = "force-dynamic";

/** Tiny poll target for the status pill: the latest collector run. */
export async function GET() {
  try {
    const run = await getLastRun();
    return NextResponse.json({ run });
  } catch {
    return NextResponse.json(
      { run: null, error: "Can't reach the database — check MONGODB_URI." },
      { status: 503 },
    );
  }
}
