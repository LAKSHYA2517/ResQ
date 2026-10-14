import { CircleHelp } from "lucide-react";
import { type ButtonHTMLAttributes, type ReactNode, useState } from "react";

type Tone = "default" | "primary" | "danger" | "ghost";

const TONES: Record<Tone, string> = {
  default: "bg-panel border-line text-ink hover:border-ink/40 hover:bg-raised",
  primary:
    "bg-accent text-white border-accent font-medium hover:brightness-110 disabled:border-line disabled:bg-raised disabled:text-dim",
  danger: "bg-raised border-bad text-bad hover:bg-bad hover:text-white",
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
      className={`inline-flex items-center justify-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm transition disabled:cursor-not-allowed disabled:opacity-40 ${TONES[tone]} ${className}`}
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
    <span className={`inline-block rounded border px-1.5 py-px text-xs ${map[tone]}`}>
      {children}
    </span>
  );
}

export function Section({
  title,
  children,
  right,
  help,
}: {
  title: string;
  children: ReactNode;
  right?: ReactNode;
  help?: string; // background reading, hidden behind a "?" so the panel shows data first
}) {
  const [open, setOpen] = useState(false);
  return (
    <section className="border-b border-line px-4 py-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-1 text-[13px] font-semibold text-ink">
          {title}
          {help && (
            <button
              type="button"
              aria-label={`About ${title}`}
              aria-expanded={open}
              onClick={() => setOpen(!open)}
              className={`rounded-full p-0.5 ${open ? "text-accent" : "text-dim hover:text-ink"}`}
            >
              <CircleHelp size={14} />
            </button>
          )}
        </h3>
        {right}
      </div>
      {open && <p className="mb-2 border-l-2 border-accent/40 pl-2 text-xs text-dim">{help}</p>}
      {children}
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="px-3 py-4 text-sm text-dim">{children}</p>;
}

export const fmt = (n: number | null | undefined, digits = 1) =>
  n === null || n === undefined ? "–" : Number.isInteger(n) ? String(n) : n.toFixed(digits);

/** A small status dot + label: run state without a pill. */
export function Status({
  tone,
  children,
}: {
  tone: "go" | "warn" | "bad" | "accent" | "dim";
  children: ReactNode;
}) {
  const dot = { go: "bg-go", warn: "bg-warn", bad: "bg-bad", accent: "bg-accent", dim: "bg-dim" }[
    tone
  ];
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <span className={`size-2 rounded-full ${dot}`} aria-hidden />
      {children}
    </span>
  );
}
