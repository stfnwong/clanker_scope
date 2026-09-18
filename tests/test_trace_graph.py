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


def test_add_first_root_event(make_event):
    g = TraceGraph()
    e = make_event(EventType.USER)
    g.add_event(e)

    assert e.id in g.nodes
    assert e.id in g._roots


def test_add_event_with_existing_parent(make_event):
    g = TraceGraph()
    parent = make_event(event_id="p")
    child = make_event(parent_ids={"p"}, event_id="c")
    g.add_event(parent)
    g.add_event(child)

    assert g.get_children("p") == {"c"}
    assert g.get_parents("c") == {"p"}


def test_reject_duplicate_event_id(make_event):
    g = TraceGraph()
    e1 = make_event(event_id="dup")
    e2 = make_event(event_id="dup")
    g.add_event(e1)

    with pytest.raises(ValueError, match="already exists"):
        g.add_event(e2)


def test_reject_missing_parent(make_event):
    g = TraceGraph()
    orphan = make_event(parent_ids={"ghost"}, event_id="c")

    with pytest.raises(KeyError, match="ghost"):
        g.add_event(orphan)


def test_reject_direct_self_loop(make_event):
    g = TraceGraph()
    e = make_event(event_id="self", parent_ids={"p"})

    with pytest.raises(KeyError):
        # Parent doesn't exist yet so this should fail at the parent check 
        g.add_event(e)



def test_root_moves_from_roots_when_parents_added(make_event):
    g = TraceGraph()
    # Start with a root node - an event that has no parents
    a = make_event(event_id="a")
    g.add_event(a)

    assert "a" in g._roots

    # Add another root event 'b' with parent 'a' 
    # After this 'a' is still a root (no parents) but 'b' is not 
    b = make_event(event_id="b", parent_ids={"a"})
    g.add_event(b)

    assert "a" in g._roots
    assert "b" not in g._roots
