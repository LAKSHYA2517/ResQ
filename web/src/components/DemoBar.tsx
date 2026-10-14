import { useState } from "react";
import { goToStep, STEPS } from "../demo";
import { useUi } from "../store/ui";
import { Btn } from "./ui";

export function DemoBar() {
  const step = useUi((s) => s.demoStep);
  const setStep = useUi((s) => s.setDemoStep);
  const [working, setWorking] = useState(false);
  if (step === null) return null;
  const s = STEPS[step];
  if (!s) return null;

  const go = async (i: number, execute: boolean) => {
    setWorking(true);
    try {
      await goToStep(i, execute);
    } finally {
      setWorking(false);
    }
  };

  return (
    <section aria-label="Guided demo" className="border-b border-accent/60 bg-accent/10 px-4 py-2">
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="text-xs font-medium text-accent">
            Guided demo · step {step + 1} of {STEPS.length}
          </div>
          <div className="text-base font-semibold">{s.title}</div>
          <p className="text-sm text-dim">
            {s.later ? `Not built yet: arrives in ${s.later}. ${s.caption}` : s.caption}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Btn disabled={working || step === 0} onClick={() => void go(step - 1, false)}>
            ← Back
          </Btn>
          <Btn
            tone="primary"
            disabled={working || step === STEPS.length - 1}
            onClick={() => void go(step + 1, true)}
          >
            {working ? "Working…" : "Next →"}
          </Btn>
          <Btn tone="ghost" onClick={() => setStep(null)}>
            Exit
          </Btn>
        </div>
      </div>
    </section>
  );
}
