import { useCallback, useRef, useState } from 'react'

const MAX_BYTES = 20 * 1024 * 1024

function DocIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-500">
      <path
        d="M11.5 2.5H6a1.5 1.5 0 0 0-1.5 1.5v12A1.5 1.5 0 0 0 6 17.5h8a1.5 1.5 0 0 0 1.5-1.5V6.5l-4-4Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
      <path d="M11.5 2.5v4h4" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  )
}

export default function UploadPanel({ documents, onChanged, onError, loading }) {
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [progressName, setProgressName] = useState('')
  const inputRef = useRef(null)

  const upload = useCallback(
    async (files) => {
      const list = Array.from(files || []).filter((f) => f.name.toLowerCase().endsWith('.pdf'))
      if (!list.length) {
        onError('Only PDF files are accepted.')
        return
      }

      setUploading(true)
      try {
        for (const file of list) {
          if (file.size > MAX_BYTES) {
            onError(`${file.name} is ${(file.size / 1e6).toFixed(1)} MB; the limit is 20 MB.`)
            continue
          }
          setProgressName(file.name)
          const body = new FormData()
          body.append('file', file)

          const response = await fetch('/api/upload', { method: 'POST', body })
          if (!response.ok) {
            let detail = `Upload failed (${response.status})`
            try {
              const parsed = await response.json()
              if (typeof parsed?.detail === 'string') detail = parsed.detail
            } catch {
              /* keep the status-code message */
            }
            onError(`${file.name}: ${detail}`)
            continue
          }
          await onChanged()
        }
      } catch (error) {
        onError(error.message || 'Upload failed.')
      } finally {
        setProgressName('')
        setUploading(false)
        if (inputRef.current) inputRef.current.value = ''
      }
    },
    [onChanged, onError],
  )

  const remove = useCallback(
    async (docId, filename) => {
      try {
        const response = await fetch(`/api/documents/${encodeURIComponent(docId)}`, {
          method: 'DELETE',
        })
        if (!response.ok) throw new Error(`Could not remove ${filename}.`)
        await onChanged()
      } catch (error) {
        onError(error.message)
      }
    },
    [onChanged, onError],
  )

  const totalChunks = documents.reduce((sum, d) => sum + d.num_chunks, 0)

  return (
    <div className="flex h-full flex-col gap-3">
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          upload(e.dataTransfer.files)
        }}
        className={`panel flex flex-col items-center justify-center gap-2 px-4 py-7 text-center
                    transition-colors ${
                      dragging ? 'border-indigo-400 bg-indigo-400/5' : 'border-dashed'
                    }`}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" className="h-6 w-6 text-slate-500">
          <path
            d="M12 16V4m0 0L8 8m4-4 4 4M4 17v1.5A2.5 2.5 0 0 0 6.5 21h11a2.5 2.5 0 0 0 2.5-2.5V17"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <p className="text-[13px] text-slate-400">
          Drop PDFs here, or{' '}
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="font-medium text-indigo-400 underline-offset-2 hover:underline"
          >
            browse
          </button>
        </p>
        <p className="text-[11px] text-slate-600">Text-based PDFs, up to 20 MB each</p>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          className="hidden"
          onChange={(e) => upload(e.target.files)}
        />
      </div>

      {uploading && (
        <div className="flex items-center gap-2 rounded-lg border border-indigo-400/30 bg-indigo-400/5 px-3 py-2">
          <span className="h-1.5 w-1.5 animate-pulse-ring rounded-full bg-indigo-400" />
          <span className="truncate text-[12px] text-indigo-200">
            Chunking and embedding {progressName || 'document'}…
          </span>
        </div>
      )}

      <div className="flex items-baseline justify-between px-0.5">
        <h2 className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-slate-500">
          corpus
        </h2>
        <span className="font-mono text-[11px] text-slate-600">
          {documents.length} docs · {totalChunks} chunks
        </span>
      </div>

      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-0.5">
        {loading && <p className="px-1 text-[12px] text-slate-600">Loading…</p>}

        {!loading && documents.length === 0 && (
          <div className="rounded-lg border border-ink-700 bg-ink-900/60 px-3 py-4">
            <p className="text-[12.5px] leading-relaxed text-slate-500">
              No documents indexed. Upload a PDF to begin — the demo corpus is three
              AML/KYC documents, and the agent will refuse to answer from anything else.
            </p>
          </div>
        )}

        {documents.map((doc) => (
          <div
            key={doc.doc_id}
            className="group flex items-start gap-2 rounded-lg border border-ink-700 bg-ink-900/60 px-2.5 py-2"
          >
            <DocIcon />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[12.5px] text-slate-300" title={doc.filename}>
                {doc.filename}
              </p>
              <p className="mt-0.5 font-mono text-[10.5px] text-slate-600">
                {doc.num_pages} pages · {doc.num_chunks} chunks
              </p>
            </div>
            <button
              type="button"
              onClick={() => remove(doc.doc_id, doc.filename)}
              title={`Remove ${doc.filename}`}
              aria-label={`Remove ${doc.filename}`}
              className="shrink-0 rounded p-1 text-slate-600 opacity-0 transition
                         hover:bg-rose-500/10 hover:text-rose-400 focus-visible:opacity-100
                         group-hover:opacity-100"
            >
              <svg viewBox="0 0 20 20" aria-hidden="true" className="h-3.5 w-3.5">
                <path
                  d="M5 5l10 10M15 5L5 15"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
