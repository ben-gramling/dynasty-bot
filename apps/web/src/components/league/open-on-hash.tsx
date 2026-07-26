"use client";

import { useEffect } from "react";

/**
 * Progressive enhancement: when the URL hash targets a front-office
 * details card (from the headline table or a chart bar), open it so the
 * browser's anchor scroll lands on expanded content. Without JS the links
 * still scroll to the closed card.
 */
export function OpenOnHash() {
  useEffect(() => {
    const open = () => {
      const id = decodeURIComponent(window.location.hash.slice(1));
      if (!id) return;
      const el = document.getElementById(id);
      if (el instanceof HTMLDetailsElement) el.open = true;
    };
    open();
    window.addEventListener("hashchange", open);
    return () => window.removeEventListener("hashchange", open);
  }, []);
  return null;
}
