import { useCallback, useRef, useState } from 'react'

/**
 * Consumes the SSE stream from POST /api/chat.
 *
 * EventSource is not an option here: it only issues GET requests, and the chat
 * call carries a JSON body. So the response body is read as a stream and the
 * frames are parsed by hand.
 *
 * The important detail is the buffer. TCP chunk boundaries have nothing to do
 * with message boundaries, so a single read() can deliver half an event, or
 * three and a half events. Everything is appended to `buffer` and only
 * complete frames -- those terminated by a blank line -- are parsed out of it.
 */

const FRAME_SEPARATOR = '\n\n'

function newTurn(id, question) {
  return {
    id,
    question,
    steps: [],
    answer: null,
    citations: [],
    status: 'running', // running | done | error
    stepCount: 0,
    elapsedMs: null,
    truncated: false,
    errorMessage: null,
  }
}

export function useAgentStream(sessionId) {
  const [turns, setTurns] = useState([])
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef(null)
  const counterRef = useRef(0)

  const patchTurn = useCallback((turnId, patch) => {
    setTurns((prev) =>
      prev.map((turn) =>
        turn.id === turnId ? { ...turn, ...(typeof patch === 'function' ? patch(turn) : patch) } : turn,
      ),
    )
  }, [])

  const applyEvent = useCallback(
    (turnId, event) => {
      switch (event.type) {
        case 'thinking':
        case 'tool_call':
        case 'tool_result':
          // Each event becomes its own card, appended the moment it arrives.
          // That progressive build is the entire point of the UI.
          patchTurn(turnId, (turn) => ({ steps: [...turn.steps, event] }))
          break
        case 'answer':
          patchTurn(turnId, { answer: event.content, citations: event.citations || [] })
          break
        case 'done':
          patchTurn(turnId, {
            status: 'done',
            stepCount: event.steps ?? 0,
            elapsedMs: event.elapsed_ms ?? null,
            truncated: Boolean(event.truncated),
          })
          break
        case 'error':
          patchTurn(turnId, (turn) => ({
            steps: [...turn.steps, event],
            status: 'error',
            errorMessage: event.message || 'The agent failed.',
          }))
          break
        default:
          break
      }
    },
    [patchTurn],
  )

  const send = useCallback(
    async (message) => {
      const text = (message || '').trim()
      if (!text || streaming) return

      counterRef.current += 1
      const turnId = `t${counterRef.current}`
      setTurns((prev) => [...prev, newTurn(turnId, text)])
      setStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller

      try {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId, message: text }),
          signal: controller.signal,
        })

        if (!response.ok) {
          let detail = `Request failed (${response.status})`
          try {
            const body = await response.json()
            if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : detail
          } catch {
            /* body was not JSON; keep the status-code message */
          }
          throw new Error(detail)
        }
        if (!response.body) {
          throw new Error('This browser does not support streaming responses.')
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        for (;;) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })

          let boundary = buffer.indexOf(FRAME_SEPARATOR)
          while (boundary !== -1) {
            const frame = buffer.slice(0, boundary)
            buffer = buffer.slice(boundary + FRAME_SEPARATOR.length)

            const dataLine = frame.split('\n').find((line) => line.startsWith('data:'))
            if (dataLine) {
              try {
                applyEvent(turnId, JSON.parse(dataLine.slice(5).trim()))
              } catch {
                // A malformed frame should not tear down a working stream.
              }
            }
            boundary = buffer.indexOf(FRAME_SEPARATOR)
          }
        }
      } catch (error) {
        if (error.name === 'AbortError') {
          patchTurn(turnId, { status: 'done', truncated: true })
        } else {
          patchTurn(turnId, {
            status: 'error',
            errorMessage: error.message || 'Could not reach the agent.',
          })
        }
      } finally {
        abortRef.current = null
        setStreaming(false)
      }
    },
    [applyEvent, patchTurn, sessionId, streaming],
  )

  const stop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const clear = useCallback(async () => {
    abortRef.current?.abort()
    setTurns([])
    try {
      await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/reset`, { method: 'POST' })
    } catch {
      /* clearing the local transcript is the part that matters */
    }
  }, [sessionId])

  return { turns, streaming, send, stop, clear }
}
