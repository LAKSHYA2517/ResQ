import type { ButtonHTMLAttributes, ReactNode } from "react";

type Tone = "default" | "primary" | "danger" | "ghost";

const TONES: Record<Tone, string> = {
  default: "bg-raised border-line text-ink hover:border-accent",
  primary:
    "bg-accent text-bg border-accent font-semibold hover:brightness-110 disabled:border-line disabled:bg-raised disabled:text-dim",
  danger: "bg-raised border-bad text-bad hover:bg-bad hover:text-bg",
  ghost: "bg-transparent border-transparent text-dim hover:text-ink",
};

export function Btn({
  tone = "default",
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: Tone }) {
  return (
    <button
      type="button"
      {...rest}
      className={`rounded-md border px-3 py-1.5 text-sm transition disabled:cursor-not-allowed disabled:opacity-40 ${TONES[tone]} ${className}`}
    />
  );
}

export function Chip({
  children,
  tone = "default",
}: {
  children: ReactNode;
  tone?: "default" | "go" | "warn" | "bad" | "accent";
}) {
  const map = {
    default: "border-line text-dim",
    go: "border-go text-go",
    warn: "border-warn text-warn",
    bad: "border-bad text-bad",
    accent: "border-accent text-accent",
  } as const;
  return (
    <span className={`inline-block rounded-full border px-2 py-0.5 text-xs ${map[tone]}`}>
      {children}
    </span>
  );
}

export function Section({
  title,
  children,
  right,
}: {
  title: string;
  children: ReactNode;
  right?: ReactNode;
}) {
  return (
    <section className="border-b border-line px-3 py-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-dim">{title}</h3>
        {right}
      </div>
      {children}
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="px-3 py-4 text-sm text-dim">{children}</p>;
}

export const fmt = (n: number | null | undefined, digits = 1) =>
  n === null || n === undefined ? "–" : Number.isInteger(n) ? String(n) : n.toFixed(digits);
