# An event in the trace
import uuid
from typing import Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum


class EventType(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SYSTEM = "system"
    ERROR = "error"



@dataclass(frozen=True)
class Event:
    type: EventType = field(hash=True)
    id: str = field(default_factory=lambda: f"event_{uuid.uuid4().hex[12:]}")
    timestamp: datetime = field(default_factory=datetime.now)
    content: str = ""    # Human-reaable text/tool output goes here
    parent_ids: set[str | object] = field(default_factory=set)      # DAG edges
    metadata: dict[str, Any] = field(default_factory=dict) # cost, tokens, tool_name, etc

    def __post_init__(self) -> None:
        # Ensure that parent_ids is always a frozenset for immutability
        object.__setattr__(self, "parent_ids", frozenset(self.parent_ids))
