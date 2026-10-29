// 前端UI数据
export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
}

// 前后的通信协议DTO
export interface ChatRequest {
  user_id: string
  conversation_id: string
  message: string
}


export interface ChatAcceptedResponse {
  run_id: string
  status: "accepted"
}