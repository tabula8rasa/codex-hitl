"""Strict shared wire contracts. No agent identity or lifecycle state here."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

RequestType = Literal["approval", "question", "manual_action"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Request(StrictModel):
    type: RequestType
    title: str
    description: str


class Message(Request):
    request_id: str

    @field_validator("request_id")
    @classmethod
    def canonical_uuid(cls, value: str) -> str:
        parsed = UUID(value)
        if parsed.version != 4 or str(parsed) != value:
            raise ValueError("request_id must be a canonical UUIDv4")
        return value


class Decision(StrictModel):
    status: Literal["approved", "rejected", "completed", "unable"]


class TextAnswer(StrictModel):
    status: Literal["answered"]
    answer: str


Answer = Annotated[Decision | TextAnswer, Field(discriminator="status")]


class AnswerRequest(StrictModel):
    request_id: str
    answer: Answer

    _canonical_uuid = field_validator("request_id")(Message.canonical_uuid.__func__)


class TimeoutResult(StrictModel):
    status: Literal["timeout"] = "timeout"
    error_code: Literal["HITL_TIMEOUT"] = "HITL_TIMEOUT"


class MessageResponse(StrictModel):
    message_id: int = Field(gt=0)


class ExpiryNotification(StrictModel):
    message_id: int = Field(gt=0)
    message: Message


class ExpiryResponse(StrictModel):
    updated: Literal[True]

    @field_validator("updated", mode="before")
    @classmethod
    def confirmed_update(cls, value: object) -> bool:
        if value is not True:
            raise ValueError("updated must be true")
        return True


class Acceptance(StrictModel):
    accepted: bool


def answer_matches(request_type: RequestType, answer: Decision | TextAnswer) -> bool:
    return answer.status in {
        "approval": {"approved", "rejected"},
        "question": {"answered"},
        "manual_action": {"completed", "unable"},
    }[request_type]
