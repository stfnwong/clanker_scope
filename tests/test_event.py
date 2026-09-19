import pytest 
from clanker_scope.event import Event, EventType


def test_event_auto_generates(make_event):
    e1 = Event(type=EventType.USER)
    e2 = Event(type=EventType.USER)

    assert e1.id != e2.id
    assert e1.id.startswith("event_")


def test_event_is_immutable(make_event):
    e = make_event()
    with pytest.raises(Exception):   # FrozenInstanceError
        e.content = "changed"


def test_parent_ids_coerced_to_fronzenset():
    e = Event(type=EventType.USER, parent_ids={"p1", "p2"})
    assert isinstance(e.parent_ids, frozenset)


def test_event_equality_by_value(base_time):
    e1 = Event(id="x", type=EventType.USER, timestamp=base_time, content="hi")
    e2 = Event(id="x", type=EventType.USER, timestamp=base_time, content="hi")
    
    assert e1 == e2


#def test_event_hashable(make_event):
#    e = make_event()
#    #from pudb import set_trace; set_trace()
#    #s = {e, e}
#    s = set([e, e])
#
#    assert len(s) == 1
