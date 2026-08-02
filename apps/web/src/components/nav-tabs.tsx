"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// v7.1: no Trades tab. Spread-finding lives in the CLI / trade-negotiator
// skill, which computes its own board live — the dashboard carries the two
// surfaces that are genuinely a daily read.
const TABS = [
  { href: "/waivers", label: "Waivers" },
  { href: "/league", label: "League" },
] as const;

export function NavTabs() {
  const pathname = usePathname();
  return (
    <nav aria-label="Sections" className="flex items-stretch gap-5 overflow-x-auto">
      {TABS.map((t) => {
        const active = pathname === t.href || pathname.startsWith(`${t.href}/`);
        return (
          <Link
            key={t.href}
            href={t.href}
            className="tab"
            aria-current={active ? "page" : undefined}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
