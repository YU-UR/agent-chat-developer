import { create } from "zustand"

import {
  createChatRun
} from "../api/chatApi"

import {
  subscribeChatRun,
  type ChatStreamEvent
} from "../services/chatStream"

import type {
  ChatMessage
} from "../types/chat"


interface ChatState {

  userId: string

  conversationId: string

  messages: ChatMessage[]

  currentRunId:
    string | null

  status:
    | "idle"
    | "accepted"
    | "running"
    | "completed"
    | "failed"

  thinkingMessage:
    string | null

  sendMessage: (
    text: string
  ) => Promise<void>
}

// memory 分user存储
const getOrCreateUserId = (): string => {
  const key = "agent_chat_user_id"

  const existing =
    localStorage.getItem(key)

  if (existing) {
    return existing
  }

  const userId =
    crypto.randomUUID()

  localStorage.setItem(
    key,
    userId
  )

  return userId
}


// --------------------------------------------------
// SSE 已处理事件
//
// 不放进 Zustand state。
// 这是运行时去重数据，不是 UI 状态。
// --------------------------------------------------

const processedEventIds =
  new Set<string>()


export const useChatStore =
  create<ChatState>(
    (set, get) => ({
      userId: getOrCreateUserId(),

      conversationId:
        crypto.randomUUID(),

      messages: [],

      currentRunId:
        null,

      status:
        "idle",

      thinkingMessage:
        null,


      sendMessage:
        async (text) => {

          // ------------------------------------------------
          // 新 run 开始
          // 清理上一轮 SSE 去重记录
          // ------------------------------------------------

          processedEventIds.clear()


          // ------------------------------------------------
          // 1. 用户消息立即显示
          // ------------------------------------------------

          const userMessage:
            ChatMessage = {

              id:
                crypto.randomUUID(),

              role:
                "user",

              content:
                text
            }


          set(
            state => ({

              messages: [
                ...state.messages,
                userMessage
              ],

              status:
                "accepted"

            })
          )


          // ------------------------------------------------
          // 2. POST /api/chat
          // ------------------------------------------------

          const response =
            await createChatRun({
              user_id:
                get().userId,

              conversation_id:
                get().conversationId,

              message:
                text

            })


          const runId =
            response.run_id


          set({

            currentRunId:
              runId

          })

          const assistantMessageId =
            `${runId}:assistant`

          let activeAttemptId:
            string | null = null

          let activeGeneration = 0

          let lastChunkIndex = 0
          // ------------------------------------------------
          // 3. SSE
          // ------------------------------------------------

          subscribeChatRun(

            runId,

            {

              // --------------------------------------------
              // thinking
              // --------------------------------------------

              onThinking(
                event:
                  ChatStreamEvent<{
                    message: string
                  }>
              ) {

                if (
                  processedEventIds.has(
                    event.event_id
                  )
                ) {
                  return
                }

                processedEventIds.add(
                  event.event_id
                )


                set({

                  status:
                    "running",

                  thinkingMessage:
                    event.data.message

                })
              },

              // --------------------------------------------
              // thinking
              // --------------------------------------------
              onDraftStart(
                event:
                  ChatStreamEvent<{
                    attempt_id: string
                    generation: number
                  }>
              ) {

                if (
                  processedEventIds.has(
                    event.event_id
                  )
                ) {
                  return
                }

                processedEventIds.add(
                  event.event_id
                )

                const attemptId =
                  event.data.attempt_id

                const generation =
                  event.data.generation

                // --------------------------------------------
                // 同一个 attempt 中，
                // 老 generation 不允许覆盖新 generation。
                // --------------------------------------------

                if (
                  activeAttemptId === attemptId
                  &&
                  generation < activeGeneration
                ) {
                  return
                }

                // --------------------------------------------
                // 新 Worker attempt
                // 或 Review 新 generation
                //
                // 都代表旧 draft 已失效。
                // --------------------------------------------

                activeAttemptId =
                  attemptId

                activeGeneration =
                  generation

                lastChunkIndex = 0

                set(
                  state => {

                    const existing =
                      state.messages.some(
                        message =>
                          message.id
                          === assistantMessageId
                      )

                    if (existing) {

                      return {
                        messages:
                          state.messages.map(
                            message => {

                              if (
                                message.id
                                !== assistantMessageId
                              ) {
                                return message
                              }

                              return {
                                ...message,
                                content: ""
                              }
                            }
                         ),

                        status:
                          "running",

                        thinkingMessage:
                          null
                      }
                    }

                    return {
                      messages: [
                        ...state.messages,

                        {
                          id:
                            assistantMessageId,

                          role:
                            "assistant",

                          content:
                            ""
                        }
                      ],

                      status:
                        "running",

                      thinkingMessage:
                        null
                    }
                  }
                )
              },

              // --------------------------------------------
              // token
              // --------------------------------------------

              onToken(
                event:
                  ChatStreamEvent<{
                    attempt_id: string
                    generation: number
                    chunk_index: number
                    content: string
                  }>
              ) {

                if (
                  processedEventIds.has(
                    event.event_id
                  )
                ) {
                  return
                }

                processedEventIds.add(
                  event.event_id
                )

                const{
                  attempt_id,
                  generation,
                  chunk_index,
                  content
                } = event.data

                // --------------------------------------------
                // 旧 Worker attempt 的残留 token
                // 不允许污染当前 draft。
                // --------------------------------------------

                if (
                  attempt_id
                  !== activeAttemptId
                ) {
                  return
                }
                // --------------------------------------------
                // Review 旧 generation 的 token
                // 不允许追加到新 draft。
                // --------------------------------------------

                if (
                  generation
                  !== activeGeneration
                ) {
                  return
                }

                 // --------------------------------------------
                 // chunk 顺序保护
                 // --------------------------------------------

                 if (
                   chunk_index
                   <= lastChunkIndex
                 ) {
                   return
                 }

                 if (
                   chunk_index
                   !== lastChunkIndex + 1
                 ) {

                   console.warn(
                     "Token chunk gap:",
                     {
                       expected:
                         lastChunkIndex + 1,

                       actual:
                         chunk_index,

                       generation
                     }
                   )
                 }

                 lastChunkIndex =
                   chunk_index

                 // --------------------------------------------
                 // 更新同一条 assistant draft
                 // --------------------------------------------
                set(
                  state => ({
                    messages:
                    state.messages.map(
                      message => {
                        if(
                          message.id !== assistantMessageId
                        ){
                          return message
                        }
                        return{
                          ...message,
                          content:
                            message.content + content
                        }
                      }
                    ),
                   status: "running",
                   thinkingMessage: null

                  })
                )
              },


              // --------------------------------------------
              // completed
              // --------------------------------------------

              onCompleted(
                event
              ) {

                if (
                  processedEventIds.has(
                    event.event_id
                  )
                ) {
                  return
                }

                processedEventIds.add(
                  event.event_id
                )


                set({

                  status:
                    "completed",

                  currentRunId:
                    null,

                  thinkingMessage:
                    null

                })
              },


              // --------------------------------------------
              // failed
              // --------------------------------------------

              onFailed(
                event:
                  ChatStreamEvent<{
                    message: string
                  }>
              ) {

                if (
                  processedEventIds.has(
                    event.event_id
                  )
                ) {
                  return
                }

                processedEventIds.add(
                  event.event_id
                )


                set({
                  messages:
                   state.messages.filter(
                     message =>
                       message.id
                       !== assistantMessageId
                   ),

                  status:
                    "failed",

                  currentRunId:
                    null,

                  thinkingMessage:
                    null

                })


                console.error(
                  "Chat run failed:",
                  event.data.message
                )
              },


              // --------------------------------------------
              // SSE error
              // --------------------------------------------

              onError(
                error
              ) {

                console.error(
                  "SSE error:",
                  error
                )

                set({

                  status:
                    "failed"

                })
              }

            }
          )
        }

    })
  )