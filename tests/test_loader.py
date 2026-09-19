import pytest 
import json

from clanker_scope.event import Event, EventType 
from clanker_scope.graph import TraceGraph

from clanker_scope.loader import (
    JSONLLoader,
    LoaderConfig,
    LoaderMode,
    LoaderResult,
)

@pytest.fixture
def stub_config() -> LoaderConfig:
    return LoaderConfig(mode=LoaderMode.STUB)


def make_jsonl(*records: dict) -> str:
    """Build a JSONL string from dicts, one per line."""
    return "\n".join(json.dumps(r) for r in records)


def event_record(
    id: str,
    event_type: str = "assistant",
    content: str = "x",
    parents: list[str] | None = None,
    timestamp: str = "2026-09-16T12:00:00",
    metadata: dict | None = None,
) -> dict:
    """Build a well-formed event record for tests."""
    return {
        "id": id,
        "type": event_type,
        "timestamp": timestamp,
        "content": content,
        "parent_ids": parents or [],
        "metadata": metadata or {},
    }



# ======== Tests on well-formed input ======== #
def test_single_event():
    lines = [make_jsonl(event_record("a", "user", "hello"))]
    result = JSONLLoader().load_lines(lines)

    assert result.success == True
    assert result.total_lines == 1 
    assert result.parsed_events == 1 
    assert result.skipped_lines == 0 
    assert len(result.graph.nodes) == 1


def test_linear_chain():
    jsonl = make_jsonl(
        event_record("a", event_type="user", content="ask"),
        event_record("b", event_type="assistant", content="reply", parents=["a"]),
        event_record("c", event_type="tool_call", content="search", parents=["b"]),
    )
    result = JSONLLoader().load_lines(jsonl.split("\n"), verbose=True)

    g = result.graph 
    assert result.parsed_events == 3
    assert g.get_children("a") == {"b"}
    assert g.get_children("b") == {"c"}


def test_diamond_dependencies():
    jsonl = make_jsonl(
        event_record("a", event_type="user", content="start"),
        event_record("b", event_type="tool_call", content="left", parents=["a"]),
        event_record("c", event_type="tool_call", content="right", parents=["a"]),
        event_record("d", event_type="assistant", content="merge", parents=["b", "c"]),
    )
    result = JSONLLoader().load_lines(jsonl.split("\n"), verbose=True)
    
    assert result.parsed_events == 4
    assert result.graph.get_parents("d") == {"b", "c"}


def test_out_of_order_input():
    jsonl = make_jsonl(
        event_record("c", event_type="assistant", content="last", parents=["b"]),
        event_record("b", event_type="tool_call", content="middle", parents=["a"]),
        event_record("a", event_type="user", content="first"),
    )
    result = JSONLLoader().load_lines(jsonl.split("\n"), verbose=True)

    assert result.parsed_events == 3
    assert result.graph.get_children("a") == {"b"}
    assert result.graph.get_children("b") == {"c"}


def test_multiple_roots(stub_config):
    jsonl = make_jsonl(
        event_record("a1", event_type="user", content="chain 1 root"),
        event_record("a2", event_type="user", content="chain 2 root"),
        event_record("b1", event_type="assistant", content="child of a1", parents=["a1"]),
        event_record("b2", event_type="assistant", content="child of a2", parents=["a2"]),
    )
    result = JSONLLoader(stub_config).load_lines(jsonl.split("\n"), verbose=True)

    assert result.parsed_events == 4
    assert result.graph._roots == {"a1", "a2"}



def test_metadata_preserved():
    jsonl = make_jsonl(
        event_record(
            "a", event_type="assistant", content="hi", 
            metadata={"tokens": 150, "model": "deepseek-chat"}
        )
    )
    result = JSONLLoader().load_lines(jsonl.split("\n"), verbose=True)
    meta = result.graph.nodes["a"].metadata
    
    assert meta["tokens"] == 150
    assert meta["model"] == "deepseek-chat"


def test_empty_lines_are_skipped():
    jsonl = "\n\n" + make_jsonl(event_record("a", event_type="user", content="hi")) + "\n\n"
    result = JSONLLoader().load_lines(jsonl.split("\n"), verbose=True)

    assert result.parsed_events == 1
    assert result.skipped_lines == 0


#def test_event_content_preserved():
#    jsonl = make_jsonl(
#        event_record("a", content="special chars: \\n \\\" ok")
#    )
#    result = JSONLLoader().load_lines(jsonl.split("\n"), verbose=True)
#
#    assert result.graph.nodes["a"].content == "special chars: \n \" ok"
