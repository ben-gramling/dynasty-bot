/** Small shared helpers for the League tab (server- and client-safe). */

/** "1st", "2nd", "3rd", "4th"… */
export function ord(n: number): string {
  const rem100 = n % 100;
  if (rem100 >= 11 && rem100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

/** Stable anchor id for a team's front-office card. */
export function slugFor(team: string): string {
  return `team-${team.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

/** ω rendered "0.60" (two decimals, data face applied by caller). */
export function fmtOmega(n: number): string {
  return n.toFixed(2);
}
