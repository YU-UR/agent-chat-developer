from pydantic import BaseModel, Field
from uuid import UUID


class ChatRequest(BaseModel):
    user_id: UUID
    conversation_id: UUID  # str
    message: str = Field(
        min_length=1,
        max_length=10000
    )


class ChatAcceptedResponse(BaseModel):
    run_id: str
    status: str
