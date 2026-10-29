import { httpClient } from "./httpClient"

import type {
  ChatRequest,
  ChatAcceptedResponse
} from "../types/chat"


export async function createChatRun(
  request: ChatRequest
): Promise<ChatAcceptedResponse> {

  const response =
    await httpClient.post<ChatAcceptedResponse>(
      "/chat",
      request
    )

  return response.data
}