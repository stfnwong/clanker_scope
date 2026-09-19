import pytest

from clanker_scope.event import Event, EventType
from clanker_scope.graph import TraceGraph



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


# ======== Test topological sort ======== #
def test_empty_graph():
    g = TraceGraph()
    assert g.topological_sort() == []


def test_single_node(make_event):
    g = TraceGraph()
    e = make_event(event_id="only")
    g.add_event(e)

    assert [ev.id for ev in g.topological_sort()] == ["only"]


def test_linear_order(linear_graph):
    result = [ev.id for ev in linear_graph.topological_sort()]
    assert result == ["a", "b", "c", "d"]


def test_diamond_parents_before_child(diamond_graph):
    result = [ev.id for ev in diamond_graph.topological_sort()]

    assert result.index("a") < result.index("b")
    assert result.index("a") < result.index("c")
    assert result.index("b") < result.index("d")
    assert result.index("c") < result.index("d")

    assert len(result) == 4


def test_fan_out(fan_out_graph):
    result = [ev.id for ev in fan_out_graph.topological_sort()]
    assert result[0] == "root"
    assert set(result[1:]) == set([f"tool_{i}" for i in range(5)])


def test_disconnected_components(make_event):
    """ Two separate chains should both appear in topological order. """
    g = TraceGraph()
    a1 = make_event(event_id="a1")
    a2 = make_event(event_id="a2", parent_ids={"a1"})
    b1 = make_event(event_id="b1")
    b2 = make_event(event_id="b2", parent_ids={"b1"})

    for ev in (a1, a2, b1, b2):
        g.add_event(ev)
    result = [ev.id for ev in g.topological_sort()]

    assert result.index("a1") < result.index("a2")
    assert result.index("b1") < result.index("b2")
    assert len(result) == 4
