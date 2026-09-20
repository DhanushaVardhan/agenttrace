import { useEffect, useState } from 'react'

/**
 * One card in the trace. The visual language is load-bearing: a reader should
 * be able to tell reasoning from action from observation at a glance, without
 * reading a word.
 */

const STYLES = {
  thinking: {
    border: 'border-l-slate-400',
    dot: 'bg-slate-400',
    label: 'reasoning',
    chip: 'bg-slate-400/10 text-slate-300',
  },
  tool_call: {
    border: 'border-l-indigo-400',
    dot: 'bg-indigo-400',
    label: 'tool call',
    chip: 'bg-indigo-400/10 text-indigo-300',
  },
  tool_result: {
    border: 'border-l-emerald-400',
    dot: 'bg-emerald-400',
    label: 'result',
    chip: 'bg-emerald-400/10 text-emerald-300',
  },
  error: {
    border: 'border-l-rose-500',
    dot: 'bg-rose-500',
    label: 'error',
    chip: 'bg-rose-500/10 text-rose-300',
  },
}

function Chevron({ open }) {
  return (
    <svg
      viewBox="0 0 20 20"
      aria-hidden="true"
      className={`h-3.5 w-3.5 shrink-0 text-slate-500 transition-transform ${open ? 'rotate-90' : ''}`}
    >
      <path d="M7 5l6 5-6 5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function summarise(step) {
  if (step.type === 'thinking') return step.content || ''
  if (step.type === 'error') return step.message || 'failed'
  if (step.type === 'tool_call') {
    const args = step.args || {}
    if (args.query) return `"${args.query}"`
    if (args.expression) return args.expression
    if (args.doc_id) return `${args.doc_id} pp.${args.page_start}-${args.page_end}`
    return Object.keys(args).length ? JSON.stringify(args) : 'no arguments'
  }
  const result = step.result || {}
  if (result.error) return result.error
  if (result.value !== undefined) return `= ${result.value}`
  if (result.hits !== undefined) {
    return result.hits === 0
      ? 'no matches'
      : `${result.hits} chunks, best score ${result.top_score ?? '-'}`
  }
  if (result.chars !== undefined) return `${result.chars} characters`
  return 'returned'
}

function SearchHits({ preview }) {
  return (
    <ul className="space-y-2">
      {preview.map((hit, i) => (
        <li key={`${hit.filename}-${hit.page_num}-${i}`} className="rounded-md bg-ink-950/60 p-2.5">
          <div className="flex items-baseline justify-between gap-3">
            <span className="font-mono text-[11px] text-emerald-300/90">
              {hit.filename} · p.{hit.page_num}
            </span>
            <span className="font-mono text-[11px] text-slate-500">{hit.score}</span>
          </div>
          <p className="mt-1 text-[12px] leading-relaxed text-slate-400">{hit.snippet}</p>
        </li>
      ))}
    </ul>
  )
}

function ResultBody({ result }) {
  if (!result) return null
  if (result.error) {
    return <p className="text-[12.5px] leading-relaxed text-rose-300">{result.error}</p>
  }
  if (Array.isArray(result.preview)) {
    return result.preview.length ? (
      <SearchHits preview={result.preview} />
    ) : (
      <p className="text-[12.5px] text-slate-400">No chunks matched this query.</p>
    )
  }
  if (result.value !== undefined) {
    return <p className="font-mono text-base text-emerald-300">{String(result.value)}</p>
  }
  if (typeof result.preview === 'string') {
    return (
      <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-slate-300">
        {result.preview}
      </p>
    )
  }
  return (
    <pre className="overflow-x-auto font-mono text-[11.5px] leading-relaxed text-slate-400">
      {JSON.stringify(result, null, 2)}
    </pre>
  )
}

export default function TraceStep({ step, index, active }) {
  const [open, setOpen] = useState(active)
  const [touched, setTouched] = useState(false)

  // Completed steps collapse to one line so the timeline stays readable,
  // unless the reader has deliberately opened one.
  useEffect(() => {
    if (!touched) setOpen(active)
  }, [active, touched])

  const style = STYLES[step.type] || STYLES.thinking
  const failed = step.type === 'tool_result' && step.result?.error
  const tone = failed ? STYLES.error : style
  const expandable = step.type !== 'thinking' || (step.content || '').length > 110

  const toggle = () => {
    setTouched(true)
    setOpen((v) => !v)
  }

  return (
    <div
      className={`animate-fade-up rounded-r-lg border-l-2 bg-ink-850/70 ${tone.border}`}
      style={{ animationDelay: `${Math.min(index, 8) * 18}ms` }}
    >
      <button
        type="button"
        onClick={expandable ? toggle : undefined}
        className={`flex w-full items-center gap-2.5 px-3 py-2 text-left ${
          expandable ? 'cursor-pointer hover:bg-ink-800/60' : 'cursor-default'
        }`}
        aria-expanded={expandable ? open : undefined}
      >
        <span
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${tone.dot} ${
            active ? 'animate-pulse-ring' : ''
          }`}
        />
        <span className={`badge shrink-0 ${tone.chip}`}>{failed ? 'error' : tone.label}</span>
        {step.tool && (
          <span className="shrink-0 rounded bg-ink-950/80 px-1.5 py-0.5 font-mono text-[11px] text-slate-300">
            {step.tool}
          </span>
        )}
        <span className="min-w-0 flex-1 truncate text-[12.5px] text-slate-400">
          {summarise(step)}
        </span>
        {typeof step.duration_ms === 'number' && (
          <span className="shrink-0 font-mono text-[11px] text-slate-500">{step.duration_ms} ms</span>
        )}
        {expandable && <Chevron open={open} />}
      </button>

      {open && expandable && (
        <div className="space-y-2 border-t border-ink-700/70 px-3 py-2.5">
          {step.type === 'thinking' && (
            <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-slate-300">
              {step.content}
            </p>
          )}
          {step.type === 'error' && (
            <p className="text-[12.5px] leading-relaxed text-rose-300">{step.message}</p>
          )}
          {step.type === 'tool_call' && (
            <>
              <p className="font-mono text-[10.5px] uppercase tracking-wider text-slate-500">
                arguments
              </p>
              <pre className="overflow-x-auto rounded-md bg-ink-950/70 p-2.5 font-mono text-[11.5px] leading-relaxed text-indigo-200/90">
                {JSON.stringify(step.args || {}, null, 2)}
              </pre>
            </>
          )}
          {step.type === 'tool_result' && <ResultBody result={step.result} />}
        </div>
      )}
    </div>
  )
}
