from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from app.llm.local_llm import local_llm


app = FastAPI()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
) -> dict[str, Any]:

    system_prompt = ""
    user_prompt = ""

    for message in request.messages:

        if message.role == "system":
            system_prompt = message.content

        elif message.role == "user":
            user_prompt = message.content

    answer = await local_llm.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_new_tokens=request.max_tokens or 256,
    )

    return {
        "id": "local-qwen-memory",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": answer,
                },
                "finish_reason": "stop",
            }
        ],
    }