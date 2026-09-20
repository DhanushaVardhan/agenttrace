import TraceStep from './TraceStep.jsx'

const MAX_STEPS = 6

/**
 * The centrepiece. Cards are appended as events arrive rather than rendered in
 * one batch at the end, so the reader watches the agent work. Without that
 * progressive build this is just a log viewer.
 */
export default function TraceTimeline({ steps, running, stepCount, elapsedMs, truncated }) {
  if (!steps.length && !running) return null

  const toolCalls = steps.filter((s) => s.type === 'tool_call').length
  const current = running ? Math.max(1, toolCalls) : stepCount || toolCalls

  // A run that died on a provider error also arrives with truncated: true, but
  // saying "stopped at the step limit" would be a lie -- the error card above
  // already explains what happened.
  const failed = steps.some((s) => s.type === 'error')

  return (
    <section className="rounded-xl border border-ink-700 bg-ink-900/70">
      <header className="flex items-center gap-3 border-b border-ink-700 px-3.5 py-2">
        <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-slate-500">
          agent trace
        </span>

        <span className="ml-auto flex items-center gap-2.5 text-[11.5px] text-slate-500">
          {running && (
            <span className="flex items-center gap-1.5 text-indigo-300">
              <span className="h-1.5 w-1.5 animate-pulse-ring rounded-full bg-indigo-400" />
              working
            </span>
          )}
          <span className="font-mono">
            Step {current} of {MAX_STEPS}
          </span>
          {!running && typeof elapsedMs === 'number' && (
            <span className="font-mono text-slate-600">{(elapsedMs / 1000).toFixed(1)}s</span>
          )}
        </span>
      </header>

      <div className="space-y-1.5 p-2.5">
        {steps.map((step, index) => (
          <TraceStep
            key={`${step.type}-${step.call_id || index}-${index}`}
            step={step}
            index={index}
            active={running && index === steps.length - 1}
          />
        ))}

        {running && steps.length === 0 && (
          <p className="px-1 py-2 text-[12.5px] text-slate-500">Planning the first step…</p>
        )}

        {truncated && !running && !failed && (
          <p className="px-1 pt-1 text-[11.5px] text-amber-400/90">
            Stopped at the {MAX_STEPS}-step limit — the answer below is partial.
          </p>
        )}
      </div>
    </section>
  )
}
