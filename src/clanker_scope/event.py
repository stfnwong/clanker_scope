# An event in the trace
import uuid
from typing import Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum


def generate_id(prefix: str="event_") -> str:
    return f"{prefix}{uuid.uuid4().hex[12:]}"


class EventType(Enum):
    USER = "user"
    SESSION_START = "session_start"
    ASSISTANT = "assistant"
    THINKING = "thinking"
    TOOL_CALL = "tool"
    TOOL_RESULT = "tool_result"
    LLM_CALL = "llm_call"
    SYSTEM = "system"
    ERROR = "error"



@dataclass(frozen=True)
class Event:
    type: EventType = field(hash=True)
    id: str = field(default_factory=lambda: generate_id())
    timestamp: datetime = field(default_factory=datetime.now)
    content: str = ""    # Human-reaable text/tool output goes here
    parent_ids: set[str | object] = field(default_factory=set)      # DAG edges
    metadata: dict[str, Any] = field(default_factory=dict) # cost, tokens, tool_name, etc

    def __post_init__(self) -> None:
        # Ensure that parent_ids is always a frozenset for immutability
        object.__setattr__(self, "parent_ids", frozenset(self.parent_ids))
