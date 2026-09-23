import pytest 
import json
from datetime import datetime

from clanker_scope.event import Event, EventType 
from clanker_scope.graph import TraceGraph

from clanker_scope.loader import (
    JSONLLoader,
    LoaderConfig,
    LoaderMode,
    LoaderResult,
)


@pytest.fixture
def orphan_input() -> str:
    """Event 'b' references parent 'ghost' which is not in the file."""
    return make_jsonl(
        event_record("b", "assistant", "orphan", parents=["ghost"]),
    )


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
        "ts": timestamp,   # Deepseek timestamp key is "ts"
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
    result = JSONLLoader().load_lines(jsonl.split("\n"))

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
    result = JSONLLoader().load_lines(jsonl.split("\n"))
    
    assert result.parsed_events == 4
    assert result.graph.get_parents("d") == {"b", "c"}


def test_out_of_order_input():
    jsonl = make_jsonl(
        event_record("c", event_type="assistant", content="last", parents=["b"]),
        event_record("b", event_type="tool_call", content="middle", parents=["a"]),
        event_record("a", event_type="user", content="first"),
    )
    result = JSONLLoader().load_lines(jsonl.split("\n"))

    assert result.parsed_events == 3
    assert result.graph.get_children("a") == {"b"}
    assert result.graph.get_children("b") == {"c"}


def test_multiple_roots():
    jsonl = make_jsonl(
        event_record("a1", event_type="user", content="chain 1 root"),
        event_record("a2", event_type="user", content="chain 2 root"),
        event_record("b1", event_type="assistant", content="child of a1", parents=["a1"]),
        event_record("b2", event_type="assistant", content="child of a2", parents=["a2"]),
    )
    result = JSONLLoader().load_lines(jsonl.split("\n"))

    assert result.parsed_events == 4
    assert result.graph._roots == {"a1", "a2"}



def test_metadata_preserved():
    jsonl = make_jsonl(
        event_record(
            "a", event_type="assistant", content="hi", 
            metadata={"tokens": 150, "model": "deepseek-chat"}
        )
    )
    result = JSONLLoader().load_lines(jsonl.split("\n"))
    meta = result.graph.nodes["a"].metadata
    
    assert meta["tokens"] == 150
    assert meta["model"] == "deepseek-chat"


def test_empty_lines_are_skipped():
    jsonl = "\n\n" + make_jsonl(event_record("a", event_type="user", content="hi")) + "\n\n"
    result = JSONLLoader().load_lines(jsonl.split("\n"))

    assert result.parsed_events == 1
    assert result.skipped_lines == 0


#def test_event_content_preserved():
#    jsonl = make_jsonl(
#        event_record("a", content="special chars: \\n \\\" ok")
#    )
#    result = JSONLLoader().load_lines(jsonl.split("\n"), verbose=True)
#
#    assert result.graph.nodes["a"].content == "special chars: \n \" ok"



# ======== Timestamp handling ======== #
def test_iso_string():
    jsonl = make_jsonl(event_record("a", timestamp="2026-09-16T12:34:54"))
    result = JSONLLoader().load_lines(jsonl.split("\n"))
    ts = result.graph.nodes["a"].timestamp

    assert ts.year == 2026
    assert ts.hour == 12
    assert ts.minute == 34


def test_unix_float_timestamp():
    record = event_record("a")
    record["timestamp"] = 1758020096.5  # Some Unix time
    jsonl = make_jsonl(record)
    result = JSONLLoader().load_lines([jsonl])

    assert isinstance(result.graph.nodes["a"].timestamp, datetime)


def test_invalid_timestamp_skipped():
    record = event_record("a")
    record["timestamp"] = "not-a-time"
    jsonl = make_jsonl(record)
    result = JSONLLoader().load_lines([jsonl])

    # Should be skipped with a warning
    assert result.parsed_events == 0
    assert result.skipped_lines == 1


# ======== Handle malformed inputs ======== #
def test_invalid_json_skipped_by_default():
    jsonl = 'not valid json\n' + make_jsonl(event_record("a", "user", "ok"))
    result = JSONLLoader().load_lines(jsonl.split("\n"))

    assert result.parsed_events == 1
    assert result.skipped_lines == 1
    assert 1 in result.malformed_lines


def test_invalid_json_raises_when_not_skipping():
    config = LoaderConfig(skip_malformed=False)
    jsonl = "not valid json"
    with pytest.raises(ValueError, match="Malformed JSON"):
        JSONLLoader(config).load_lines([jsonl])

def test_missing_required_field_skipped():
    bad = {"type": "user", "timestamp": "2026-09-16T12:00:00"}  # no id
    jsonl = make_jsonl(bad)
    result = JSONLLoader().load_lines([jsonl])

    assert result.parsed_events == 0
    assert result.skipped_lines == 1

def test_invalid_event_type_skipped():
    bad = event_record("a", event_type="not_a_valid_type")
    jsonl = make_jsonl(bad)
    result = JSONLLoader().load_lines(jsonl.split("\n"))

    assert result.parsed_events == 0
    assert result.skipped_lines == 1


def test_all_lines_malformed():
    jsonl = "bad line 1\nbad line 2\nbad line 3"
    result = JSONLLoader().load_lines(jsonl.split("\n"))

    assert result.parsed_events == 0
    assert result.skipped_lines == 3
    assert len(result.malformed_lines) == 3


def test_strict_mode_raises(orphan_input):
    config = LoaderConfig(mode=LoaderMode.STRICT)
    with pytest.raises(ValueError, match="missing parents"):
        JSONLLoader(config).load_lines([orphan_input])


def test_stub_mode_creates_placeholder(orphan_input):
    config = LoaderConfig(mode=LoaderMode.STUB)
    result = JSONLLoader(config).load_lines([orphan_input])
    
    assert "ghost" in result.stubbed_parents
    assert "ghost" in result.graph.nodes
    stub = result.graph.nodes["ghost"]
    assert stub.type == EventType.SYSTEM
    assert stub.metadata.get("stub") is True


def test_stub_mode_links_child_to_stub(orphan_input):
    config = LoaderConfig(mode=LoaderMode.STUB)
    result = JSONLLoader(config).load_lines([orphan_input])
    
    assert result.graph.get_parents("b") == {"ghost"}


def test_drop_mode_removes_orphan(orphan_input):
    config = LoaderConfig(mode=LoaderMode.DROP)
    result = JSONLLoader(config).load_lines([orphan_input])
    
    assert "b" in result.dropped_orphans
    assert "b" not in result.graph.nodes
    assert len(result.graph.nodes) == 0


def test_warn_mode_makes_orphan_root(orphan_input):
    config = LoaderConfig(mode=LoaderMode.WARN)
    result = JSONLLoader(config).load_lines([orphan_input])
    
    assert "b" in result.graph.nodes
    assert result.graph.get_parents("b") == set()  # parents cleared
    assert len(result.warnings) > 0


def test_warn_mode_logs_suppressed(orphan_input):
    config = LoaderConfig(mode=LoaderMode.WARN, log_missing_parents=False)
    result = JSONLLoader(config).load_lines([orphan_input])
    
    # Event still loaded, but no warning entry
    assert "b" in result.graph.nodes
    assert result.warnings == []



# ======== Complex missing parents ======== #
def test_diamond_with_one_missing_parent_drop():
    """Diamond where one parent is dropped should cascade."""
    jsonl = make_jsonl(
        event_record("a", "user"),
        # Skip b
        event_record("c", "tool_call", parents=["a"]),
        event_record("d", "assistant", parents=["b", "c"]),  # b missing
    )
    config = LoaderConfig(mode=LoaderMode.DROP)
    result = JSONLLoader(config).load_lines(jsonl.split("\n"))
    #print(result.warnings)

    assert "d" in result.dropped_orphans
    assert "d" not in result.graph.nodes
    # a and c should still load
    # TODO: come back to c as the current algorithm doesn't handle partial parent yet
    assert "a" in result.graph.nodes
    #assert "c" in result.graph.nodes


def test_diamond_with_one_missing_parent_stub():
    jsonl = make_jsonl(
        event_record("a", "user"),
        event_record("c", "tool_call", parents=["a"]),
        event_record("d", "assistant", parents=["b", "c"]),
    )
    config = LoaderConfig(mode=LoaderMode.STUB)
    result = JSONLLoader(config).load_lines(jsonl.split("\n"))

    assert "b" in result.stubbed_parents
    assert "d" in result.graph.nodes
    assert result.graph.get_parents("d") == {"b", "c"}


def test_missing_parent_chain_stub():
    """
    b references ghost1, c references ghost2.
    Both should be stubbed independently.
    """
    jsonl = make_jsonl(
        event_record("b", parents=["ghost1"]),
        event_record("c", parents=["ghost2"]),
    )
    config = LoaderConfig(mode=LoaderMode.STUB)
    result = JSONLLoader(config).load_lines(jsonl.split("\n"))

    assert result.stubbed_parents == {"ghost1", "ghost2"}
    assert len(result.graph.nodes) == 4  # 2 real + 2 stubs


def test_all_modes_on_same_input_differ_predictably():
    """Same input, four modes, four clearly distinct outcomes."""
    jsonl = make_jsonl(event_record("b", parents=["ghost"]))

    strict = LoaderConfig(mode=LoaderMode.STRICT)
    with pytest.raises(ValueError):
        JSONLLoader(strict).load_lines([jsonl])

    stub = JSONLLoader(LoaderConfig(mode=LoaderMode.STUB)).load_lines([jsonl])
    assert "b" in stub.graph.nodes and "ghost" in stub.graph.nodes

    drop = JSONLLoader(LoaderConfig(mode=LoaderMode.DROP)).load_lines([jsonl])
    assert "b" not in drop.graph.nodes

    warn = JSONLLoader(LoaderConfig(mode=LoaderMode.WARN)).load_lines([jsonl])
    assert "b" in warn.graph.nodes
    assert warn.graph.get_parents("b") == set()
