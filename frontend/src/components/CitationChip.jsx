import { useState } from 'react'

/**
 * An inline [filename, p.N] marker, rendered as a chip that expands the source
 * chunk underneath the answer.
 *
 * The snippet comes from the search results already streamed into this turn's
 * trace, so checking a citation costs no extra request -- and a citation with
 * no matching retrieved chunk simply has nothing to show, which is itself a
 * useful signal.
 */
export default function CitationChip({ filename, page, snippet }) {
  const [open, setOpen] = useState(false)
  const short = filename.replace(/\.pdf$/i, '')

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={snippet ? 'Show the source text' : `${filename}, page ${page}`}
        className={`mx-0.5 inline-flex items-baseline gap-1 rounded border px-1.5 py-[1px]
                    align-baseline font-mono text-[10.5px] transition-colors
                    ${
                      open
                        ? 'border-indigo-400/60 bg-indigo-400/15 text-indigo-200'
                        : 'border-ink-600 bg-ink-800/80 text-slate-400 hover:border-indigo-400/50 hover:text-indigo-300'
                    }`}
      >
        <span className="max-w-[13rem] truncate">{short}</span>
        <span className="text-slate-500">p.{page}</span>
      </button>

      {open && (
        <span className="my-1.5 block rounded-md border border-ink-700 bg-ink-950/70 p-2.5">
          <span className="mb-1 block font-mono text-[10.5px] text-slate-500">
            {filename} · page {page}
          </span>
          <span className="block text-[12.5px] leading-relaxed text-slate-400">
            {snippet || 'This page was cited but its text was not among the retrieved chunks.'}
          </span>
        </span>
      )}
    </>
  )
}
