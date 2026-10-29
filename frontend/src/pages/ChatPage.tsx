import { useState } from "react"
import { useChatStore } from "../stores/chatStore"
import "./ChatPage.css"


export default function ChatPage() {

  const [input, setInput] = useState("")

  const messages = useChatStore(
    state => state.messages
  )

  const status = useChatStore(
    state => state.status
  )

  const thinkingMessage = useChatStore(
    state => state.thinkingMessage
  )

  const sendMessage = useChatStore(
    state => state.sendMessage
  )


  async function handleSend() {

    const value = input.trim()

    if (!value)
      return

    setInput("")

    await sendMessage(value)
  }


  return (

    <div className="chat-page">

      <div className="chat-container">

        {/* Header */}
        <div className="chat-header">

          <div className="chat-logo">
            AI
          </div>

          <div>
            <div className="chat-title">
              AI Assistant
            </div>

            <div className="chat-subtitle">
              Ask me anything
            </div>
          </div>

        </div>


        {/* Messages */}
        <div className="message-area">

          {messages.length === 0 && (

            <div className="empty-state">

              <div className="empty-icon">
                ✦
              </div>

              <h2>
                How can I help you?
              </h2>

              <p>
                Start a conversation with your AI assistant.
              </p>

            </div>

          )}


          {messages.map(message => {

            const isUser =
              message.role === "user"

            return (

              <div
                key={message.id}
                className={
                  `message-row ${
                    isUser
                      ? "message-row-user"
                      : "message-row-assistant"
                  }`
                }
              >

                {!isUser && (
                  <div className="assistant-avatar">
                    AI
                  </div>
                )}


                <div
                  className={
                    `message-wrapper ${
                      isUser
                        ? "message-wrapper-user"
                        : ""
                    }`
                  }
                >

                  <div className="message-name">
                    {
                      isUser
                        ? "You"
                        : "Assistant"
                    }
                  </div>


                  <div
                    className={
                      `message-bubble ${
                        isUser
                          ? "user-bubble"
                          : "assistant-bubble"
                      }`
                    }
                  >
                    {message.content}
                  </div>

                </div>

              </div>

            )
          })}


          {/* Thinking */}
          {status === "running" && (

            <div className="message-row">

              <div className="assistant-avatar">
                AI
              </div>

              <div className="message-wrapper">

                <div className="message-name">
                  Assistant
                </div>

                <div className="message-bubble thinking-bubble">

                  <span className="thinking-dot">
                    ●
                  </span>

                  {thinkingMessage}

                </div>

              </div>

            </div>

          )}

        </div>


        {/* Input */}
        <div className="input-section">

          <div className="input-box">

            <textarea
              value={input}
              placeholder="Type your message..."

              onChange={
                event =>
                  setInput(
                    event.target.value
                  )
              }
            />


            <button
              onClick={handleSend}
              className="send-button"
            >
              Send

              <span>
                →
              </span>
            </button>

          </div>

          <div className="footer-text">
            AI Assistant
          </div>

        </div>

      </div>

    </div>

  )
}