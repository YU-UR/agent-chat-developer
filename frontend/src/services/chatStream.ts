export interface ChatStreamEvent<T = unknown> {
  event_id: string
  event_key: string
  seq: number
  data: T
}

export interface ChatStreamHandlers {

  onThinking: (
    event: ChatStreamEvent<{
      message: string
    }>
  ) => void

   onDraftStart: (
    event: ChatStreamEvent<{
      attempt_id: string
      generation: number
    }>
  ) => void

  onToken: (
    event: ChatStreamEvent<{
      attempt_id: string
      generation: number
      chunk_index: number
      content: string
    }>
  ) => void

  onCompleted: (
    event: ChatStreamEvent<Record<string, never>>
  ) => void

  onFailed: (
    event: ChatStreamEvent<{
      message: string
    }>
  ) => void

  onError: (
    error: Event
  ) => void
}


export function subscribeChatRun(
  runId: string,
  handlers: ChatStreamHandlers
) {

  const eventSource = new EventSource(
    `/api/chat/${runId}/events`
  )


  function parseEvent<T>(
    event: Event
  ): ChatStreamEvent<T> {

    const messageEvent =
      event as MessageEvent<string>

    const parsed =
      JSON.parse(
        messageEvent.data
      )

    return parsed as ChatStreamEvent<T>
  }


  eventSource.addEventListener(
    "thinking",
    (event) => {

      const parsed =
        parseEvent<{
          message: string
        }>(event)

      console.log(
        "thinking:",
        parsed
      )

      console.log(
        "event id:",
        parsed.event_id
      )

      console.log(
        "seq:",
        parsed.seq
      )

      handlers.onThinking(
        parsed
      )
    }
  )

  eventSource.addEventListener(
  "draft_start",
  (event) => {

    const parsed =
      parseEvent<{
        attempt_id: string
        generation: number
      }>(event)

    console.log(
      "draft_start:",
      parsed
    )

    handlers.onDraftStart(
      parsed
    )
  }
)


  eventSource.addEventListener(
    "token",
    (event) => {

      const parsed =
        parseEvent<{
          attempt_id: string
          generation: number
          chunk_index: number
          content: string
        }>(event)

      console.log(
        "token:",
        parsed.data.content
      )

      console.log(
        "event id:",
        parsed.event_id
      )

      console.log(
        "seq:",
        parsed.seq
      )

      handlers.onToken(
        parsed
      )
    }
  )


  eventSource.addEventListener(
    "completed",
    (event) => {

      const parsed =
        parseEvent<Record<string, never>>(
          event
        )

      console.log(
        "completed:",
        parsed
      )

      handlers.onCompleted(
        parsed
      )

      eventSource.close()
    }
  )


  eventSource.addEventListener(
    "failed",
    (event) => {

      const parsed =
        parseEvent<{
          message: string
        }>(event)

      console.error(
        "failed:",
        parsed
      )

      handlers.onFailed(
        parsed
      )

      eventSource.close()
    }
  )


  eventSource.onerror =
    (error) => {

      console.error(
        "SSE error:",
        error
      )

      handlers.onError(
        error
      )
    }


  return eventSource
}