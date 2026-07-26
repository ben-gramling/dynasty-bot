import type { Metadata } from "next";
import { Big_Shoulders, IBM_Plex_Mono, Public_Sans } from "next/font/google";
import "./globals.css";
import { NavTabs } from "@/components/nav-tabs";
import { RefreshButton } from "@/components/refresh-button";
import { RunStatus } from "@/components/run-status";
import { Star } from "@/components/star";
import { getLastRun, type CollectorRun } from "@/lib/queries";

// Every page reads live Mongo state — never prerender at build time.
export const dynamic = "force-dynamic";

const bigShoulders = Big_Shoulders({
  subsets: ["latin"],
  variable: "--font-big-shoulders",
});

const publicSans = Public_Sans({
  subsets: ["latin"],
  variable: "--font-public-sans",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-mono",
});

export const metadata: Metadata = {
  title: "Chicago Dynasty — front office",
  description:
    "Waiver claims, trade offers, and league standing for the Chicago Dynasty team what would it take.",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  let lastRun: CollectorRun | null = null;
  let dbDown = false;
  try {
    lastRun = await getLastRun();
  } catch {
    dbDown = true;
  }

  return (
    <html
      lang="en"
      className={`${bigShoulders.variable} ${publicSans.variable} ${plexMono.variable}`}
    >
      <body>
        <div className="flag-band" aria-hidden />
        <header className="masthead">
          <div className="mx-auto flex max-w-[1200px] flex-wrap items-center gap-x-8 gap-y-0 px-4 sm:px-6">
            <a href="/waivers" className="wordmark flex items-center gap-3 py-3">
              <span className="flex gap-1" aria-hidden>
                <Star size={11} />
                <Star size={11} />
                <Star size={11} />
                <Star size={11} />
              </span>
              <span>
                Chicago Dynasty
                <span className="wordmark-sub">Front office</span>
              </span>
            </a>
            <NavTabs />
            <div className="ml-auto flex items-center gap-2 py-2">
              {dbDown ? (
                <span className="pill" role="status">
                  <span className="pill-dot is-error" aria-hidden />
                  Can&apos;t reach the database — check MONGODB_URI
                </span>
              ) : (
                <RunStatus initialRun={lastRun} />
              )}
              <RefreshButton />
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-[1200px] px-4 py-6 sm:px-6">{children}</main>
      </body>
    </html>
  );
}
