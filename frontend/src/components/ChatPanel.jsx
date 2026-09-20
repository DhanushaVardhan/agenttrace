import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import TraceTimeline from './TraceTimeline.jsx'
import CitationChip from './CitationChip.jsx'

const CITATION_RE = /\[\s*([^[\],]+?)\s*,?\s*p\.?\s*(\d+)\s*\]/gi

const EXAMPLES = [
  "What's the customer due diligence threshold, and if a bank processes 40 transactions at that exact amount, what's the total?",
  'How long must customer identification records be retained after a relationship ends?',
  'What extra steps apply to a politically exposed person, and who has to approve the account?',
  'Compare the wire transfer thresholds across the documents.',
]

/**
 * Build filename|page -> snippet from the search results already streamed into
 * this turn, so a citation chip can show its source without another request.
 */
function buildSourceMap(steps) {
  const map = new Map()
  for (const step of steps) {
    const preview = step?.result?.preview
    if (!Array.isArray(preview)) continue
    for (const hit of preview) {
      const key = `${String(hit.filename).toLowerCase()}|${hit.page_num}`
      if (!map.has(key)) map.set(key, hit.snippet)
    }
  }
  return map
}

/** Split the answer on [filename, p.N] markers and render them as chips. */
function renderAnswer(text, sourceMap) {
  const nodes = []
  let lastIndex = 0
  let match
  let key = 0

  CITATION_RE.lastIndex = 0
  while ((match = CITATION_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(<span key={`t${key++}`}>{text.slice(lastIndex, match.index)}</span>)
    }
    const filename = match[1].trim()
    const page = Number(match[2])
    nodes.push(
      <CitationChip
        key={`c${key++}`}
        filename={filename}
        page={page}
        snippet={sourceMap.get(`${filename.toLowerCase()}|${page}`)}
      />,
    )
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < text.length) {
    nodes.push(<span key={`t${key++}`}>{text.slice(lastIndex)}</span>)
  }
  return nodes
}

function Answer({ text, steps }) {
  const sourceMap = buildSourceMap(steps)
  const paragraphs = text.split(/\n{2,}/).filter((p) => p.trim())

  return (
    <div className="rounded-xl border border-ink-700 bg-ink-900/40 px-4 py-3.5">
      {paragraphs.map((paragraph, i) => (
        <p key={i} className="mb-2.5 text-[13.5px] leading-[1.7] text-slate-200 last:mb-0">
          {renderAnswer(paragraph, sourceMap)}
        </p>
      ))}
    </div>
  )
}

function Turn({ turn }) {
  return (
    <article className="space-y-2.5">
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-xl rounded-br-sm bg-indigo-500/15 px-3.5 py-2
                      text-[13.5px] leading-relaxed text-indigo-100">
          {turn.question}
        </p>
      </div>

      <TraceTimeline
        steps={turn.steps}
        running={turn.status === 'running'}
        stepCount={turn.stepCount}
        elapsedMs={turn.elapsedMs}
        truncated={turn.truncated}
      />

      {turn.answer && <Answer text={turn.answer} steps={turn.steps} />}

      {turn.status === 'error' && !turn.answer && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-500/5 px-4 py-3">
          <p className="text-[13px] leading-relaxed text-rose-300">{turn.errorMessage}</p>
        </div>
      )}
    </article>
  )
}

export default function ChatPanel({ turns, streaming, onSend, onStop, onClear, hasDocuments }) {
  const [draft, setDraft] = useState('')
  const scrollRef = useRef(null)
  const inputRef = useRef(null)

  // Follow the stream, but only while the reader is already near the bottom,
  // so scrolling up to inspect an earlier step is not yanked away.
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 220
    if (nearBottom) el.scrollTop = el.scrollHeight
  }, [turns])

  useEffect(() => {
    if (!streaming) inputRef.current?.focus()
  }, [streaming])

  const submit = (event) => {
    event?.preventDefault()
    const text = draft.trim()
    if (!text || streaming) return
    setDraft('')
    onSend(text)
  }

  const onKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-6 overflow-y-auto px-1 pb-4">
        {turns.length === 0 && (
          <div className="mx-auto mt-10 max-w-xl px-2 text-center">
            <h2 className="text-lg font-semibold text-slate-200">
              Ask the corpus a question
            </h2>
            <p className="mx-auto mt-2 max-w-md text-[13px] leading-relaxed text-slate-500">
              The agent searches before it answers, reformulates the query when retrieval
              comes back weak, and calls a calculator rather than doing arithmetic in its
              head. Every one of those steps appears below as it happens.
            </p>

            <div className="mt-6 space-y-2 text-left">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  disabled={!hasDocuments}
                  onClick={() => onSend(example)}
                  className="w-full rounded-lg border border-ink-700 bg-ink-900/60 px-3.5 py-2.5
                             text-[12.5px] leading-relaxed text-slate-400 transition-colors
                             hover:border-indigo-400/50 hover:text-slate-200
                             disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {example}
                </button>
              ))}
            </div>

            {!hasDocuments && (
              <p className="mt-4 text-[12px] text-amber-400/90">
                Upload a PDF first — the agent has nothing to search.
              </p>
            )}
          </div>
        )}

        {turns.map((turn) => (
          <Turn key={turn.id} turn={turn} />
        ))}
      </div>

      <form onSubmit={submit} className="shrink-0 pt-2">
        <div className="panel flex items-end gap-2 p-2">
          <textarea
            ref={inputRef}
            rows={1}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={
              hasDocuments ? 'Ask about the indexed documents…' : 'Upload a PDF to get started…'
            }
            disabled={streaming}
            className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2
                       text-[13.5px] leading-relaxed text-slate-200 placeholder:text-slate-600
                       focus:outline-none disabled:opacity-50"
          />
          {streaming ? (
            <button type="button" onClick={onStop} className="btn-ghost">
              Stop
            </button>
          ) : (
            <button type="submit" disabled={!draft.trim()} className="btn-primary">
              Ask
            </button>
          )}
        </div>

        <div className="flex items-center justify-between px-1 pt-1.5">
          <span className="text-[11px] text-slate-600">
            Enter to send · Shift+Enter for a new line
          </span>
          {turns.length > 0 && (
            <button
              type="button"
              onClick={onClear}
              className="text-[11px] text-slate-600 transition-colors hover:text-slate-400"
            >
              Clear conversation
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
