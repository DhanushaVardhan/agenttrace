import { useCallback, useEffect, useState } from 'react'
import UploadPanel from './components/UploadPanel.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import { useAgentStream } from './hooks/useAgentStream.js'

function makeSessionId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `s-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function Logo() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className="h-7 w-7">
      <rect width="32" height="32" rx="7" className="fill-ink-800" />
      <circle cx="9" cy="9" r="3" className="fill-indigo-400" />
      <circle cx="9" cy="23" r="3" className="fill-emerald-400" />
      <circle cx="23" cy="16" r="3" className="fill-slate-400" />
      <path d="M9 9h6l8 7-8 7H9" fill="none" strokeWidth="1.6" className="stroke-ink-600" />
    </svg>
  )
}

function Toast({ message, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, 7000)
    return () => clearTimeout(timer)
  }, [message, onDismiss])

  return (
    <div
      role="alert"
      className="fixed bottom-5 left-1/2 z-50 w-[min(30rem,calc(100vw-2rem))] -translate-x-1/2
                 animate-fade-up rounded-lg border border-rose-500/40 bg-ink-850 px-4 py-3
                 shadow-xl shadow-black/40"
    >
      <div className="flex items-start gap-3">
        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-rose-500" />
        <p className="flex-1 text-[12.5px] leading-relaxed text-slate-300">{message}</p>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="shrink-0 rounded p-0.5 text-slate-600 hover:text-slate-300"
        >
          <svg viewBox="0 0 20 20" aria-hidden="true" className="h-3.5 w-3.5">
            <path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
          </svg>
        </button>
      </div>
    </div>
  )
}

export default function App() {
  const [sessionId] = useState(makeSessionId)
  const [documents, setDocuments] = useState([])
  const [loadingDocs, setLoadingDocs] = useState(true)
  const [health, setHealth] = useState(null)
  const [toast, setToast] = useState(null)

  const { turns, streaming, send, stop, clear } = useAgentStream(sessionId)

  const refreshDocuments = useCallback(async () => {
    try {
      const response = await fetch('/api/documents')
      if (!response.ok) throw new Error('Could not load the document list.')
      setDocuments(await response.json())
    } catch (error) {
      setToast(error.message)
    } finally {
      setLoadingDocs(false)
    }
  }, [])

  useEffect(() => {
    refreshDocuments()
    fetch('/api/health')
      .then((r) => (r.ok ? r.json() : null))
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [refreshDocuments])

  // The sample corpus is embedded in the background at startup, so a freshly
  // booted instance fills in a few seconds after the page first loads.
  useEffect(() => {
    if (documents.length > 0) return undefined
    const timer = setInterval(refreshDocuments, 4000)
    return () => clearInterval(timer)
  }, [documents.length, refreshDocuments])

  const missingKey = health?.status === 'missing_api_key'

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 items-center gap-3 border-b border-ink-800 px-4 py-3 sm:px-6">
        <Logo />
        <div className="min-w-0">
          <h1 className="text-[15px] font-semibold leading-tight text-slate-100">AgentTrace</h1>
          <p className="truncate text-[11.5px] text-slate-500">
            Agentic RAG over PDFs, with the reasoning shown
          </p>
        </div>

        <div className="ml-auto flex items-center gap-3">
          {health && (
            <span className="hidden font-mono text-[11px] text-slate-600 sm:inline">
              {health.model}
            </span>
          )}
          <span
            className={`badge ${
              missingKey ? 'bg-amber-400/10 text-amber-300' : 'bg-emerald-400/10 text-emerald-300'
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${missingKey ? 'bg-amber-400' : 'bg-emerald-400'}`}
            />
            {missingKey ? 'no API key' : 'ready'}
          </span>
        </div>
      </header>

      {missingKey && (
        <div className="shrink-0 border-b border-amber-400/20 bg-amber-400/5 px-4 py-2 sm:px-6">
          <p className="text-[12px] text-amber-200/90">
            GEMINI_API_KEY is not set on the server. Uploads and questions will fail until it is.
          </p>
        </div>
      )}

      <main className="grid min-h-0 flex-1 gap-4 px-4 py-4 sm:px-6 lg:grid-cols-[minmax(17rem,30%)_1fr]">
        <aside className="min-h-0 lg:h-full">
          <UploadPanel
            documents={documents}
            onChanged={refreshDocuments}
            onError={setToast}
            loading={loadingDocs}
          />
        </aside>

        <section className="min-h-0 lg:h-full">
          <ChatPanel
            turns={turns}
            streaming={streaming}
            onSend={send}
            onStop={stop}
            onClear={clear}
            hasDocuments={documents.length > 0}
          />
        </section>
      </main>

      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}
    </div>
  )
}
