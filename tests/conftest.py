import pytest
from datetime import datetime, timedelta
from clanker_scope.event import Event, EventType
from clanker_scope.graph import TraceGraph


@pytest.fixture
def base_time() -> datetime:
    """ Fixed timestamp for deterministic tests. """
    return datetime(2026, 9, 16, 12, 0, 0)


@pytest.fixture
def make_event(base_time):
    """ Event factory with useful defaults. """
    counter = {"n": 0}

    def _make(
        event_type: EventType=EventType.ASSISTANT,
        content: str="",
        parent_ids: set[str] | None = None,
        seconds_offset: int = 0,
        metadata: dict | None = None,
        event_id: str | None = None,
    ) -> Event:
        counter["n"] += 1

        return Event(
            id=event_id or f"evt_{counter['n']:03d}",
            type=event_type,
            timestamp=base_time + timedelta(seconds=seconds_offset),
            content=content or f"event {counter['n']}",
            parent_ids=parent_ids or set(),
            metadata=metadata or {}
        )

    return _make



@pytest.fixture
def linear_graph(make_event) -> TraceGraph:
    """ A -> B -> C -> D """
    g = TraceGraph()
    a = make_event(EventType.USER, "ask", event_id="a")
    b = make_event(EventType.ASSISTANT, "respond", parent_ids={"a"}, event_id="b")
    c = make_event(EventType.TOOL_CALL, "search", parent_ids={"b"}, event_id="c")
    d = make_event(EventType.TOOL_RESULT, "results", parent_ids={"c"}, event_id="d")

    for ev in (a, b, c, d):
        g.add_event(ev)

    return g


@pytest.fixture
def diamond_graph(make_event) -> TraceGraph:
    """
        A
       / \\
      B   C
       \\ /
        D
    """

    g = TraceGraph()
    a = make_event(EventType.USER, "root", event_id="a")
    b = make_event(EventType.TOOL_CALL, "left branch", parent_ids={"a"}, event_id="b")
    c = make_event(EventType.TOOL_CALL, "right branch", parent_ids={"a"}, event_id="c")
    d = make_event(EventType.ASSISTANT, "merge", parent_ids={"b", "c"}, event_id="d")

    for ev in (a, b, c, d):
        g.add_event(ev)

    return g



@pytest.fixture
def fan_out_graph(make_event) -> TraceGraph:
    """ One parent with five children (ie: a parallel tool call) """
    g = TraceGraph()

    root = make_event(EventType.ASSISTANT, "root", event_id="root")
    g.add_event(root)

    for i in range(5):
        child = make_event(
            EventType.TOOL_CALL, 
            f"tool_{i}",
            parent_ids={"root"},
            event_id=f"tool_{i}"
        )
        g.add_event(child)

    return g
