/**
 * The Chicago six-pointed star. Used only where emphasis is earned:
 * the wordmark, "recommended" markers, the my-team marker in charts
 * (docs/web-design.md §3). Defaults to star red.
 */
export function Star({
  size = 10,
  className = "",
  title,
}: {
  size?: number;
  className?: string;
  title?: string;
}) {
  // Six sharp points (Chicago's star), outer r=10, inner r=4.
  const points = Array.from({ length: 12 }, (_, i) => {
    const r = i % 2 === 0 ? 10 : 4;
    const a = (Math.PI / 6) * i - Math.PI / 2;
    return `${(10 + r * Math.cos(a)).toFixed(2)},${(10 + r * Math.sin(a)).toFixed(2)}`;
  }).join(" ");

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      className={className}
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      fill="currentColor"
      style={{ color: "var(--color-star)" }}
    >
      {title ? <title>{title}</title> : null}
      <polygon points={points} />
    </svg>
  );
}
