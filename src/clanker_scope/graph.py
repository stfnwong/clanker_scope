from collections import deque
from typing import Generator, Self

from clanker_scope.event import Event, EventType


class TraceGraph:
    """ A DAG that represents a full agentic session """

    def __init__(self):
        self._nodes: dict[str, Event] = {}
        self._children: dict[str, set[str]] = {}   # parent_id -> set(children)
        self._parents: dict[str, set[str]] = {}   # chiild_id -> set(parents)
        self._roots: set[str] = set()   # Nodes with no parents

    @property
    def nodes(self) -> dict[str, Event]:
        return self._nodes.copy()

    @property
    def edges(self) -> dict[str, set[str]]:
        return {k: v.copy() for k, v in self._children.items()}

    def get_children(self, event_id: str) -> set[str]:
        return self._children.get(event_id, set())

    def get_parents(self, event_id: str) -> set[str]:
        return self._parents.get(event_id, set())
    
    def add_event(self, event: Event) -> None:
        if event.id in self._nodes:
            raise ValueError(f"event {event} already exists")
            #return     # Could raise here but it depends what signal the caller should have

        # Validate that parent exists 
        for p_id in event.parent_ids:
            if p_id not in self._nodes:
                raise KeyError(f"Parent {p_id} not found in graph")

        # Add node 
        self._nodes[event.id] = event 
        self._children.setdefault(event.id, set())
        self._parents.setdefault(event.id, set())

        # Add edges 
        for p_id in event.parent_ids:
            self._children[p_id].add(event.id)
            self._parents[event.id].add(p_id)

        # Update roots
        if not event.parent_ids:
            self._roots.add(event.id)
        else:
            self._roots.discard(event.id)   # If it was a root before then remove it

        # Cyclic check 
        if self._detect_cycle():
            # Rollback 
            self._nodes.pop(event.id)
            for p_id in event.parent_ids:
                self._children[p_id].discard(event.id)

            self._parents.pop(event.id)
            self._roots = self._calculate_roots()

            raise ValueError(f"Event {event.id} would create a cycle")

    def _detect_cycle(self) -> bool:
        """ Return True if there is a cycle in the graph. """

        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)

            for child in self._children.get(node_id, []):
                if child not in visited:
                    if dfs(child):
                        return True
                elif child in rec_stack:
                    return True

            rec_stack.remove(node_id)

            return False

        for node in self._nodes:
            if node not in visited:
                if dfs(node):
                    return True

        return False

    def _calculate_roots(self) -> set[str]:
        return {nid for nid in self._nodes if not self._parents.get(nid, set())}

    def topological_sort(self) -> list[Event]:
        """ Return a list of events in execution order. """

        in_degree: dict[str, int] = {
            nid: len(self._parents.get(nid, set())) for nid in self._nodes
        }
        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        sorted_ids: list[str] = []

        while queue:
            nid = queue.popleft()
            sorted_ids.append(nid)
            for child in self._children.get(nid, []):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(sorted_ids) != len(self._nodes):
            raise RuntimeError(f"Graph has a cycle")

        return [self._nodes[nid] for nid in sorted_ids]

    def get_ancestors(self, event_id: str) -> set[Event]:
        """ All events that causally preceed this one. """

        result: set[Event] = set()
        stack = list(self._parents.get(event.id, []))
        visited = set()

        while stack:
            p_id = stack.pop()
            if p_id in visited:
                continue
            visited.add(p_id)
            result.add(self._nodes[p_id])
            stack.extend(self._parents.get(p_id, []))

        return result

    def to_jsonl(self) -> str:
        """ Export each evnt as a jsonl line. """
        import json
        lines = []

        for event in self.topological_sort():
            data = {
                "id": event.id,
                "type": event.type,
                "timestamp": event.timestamp.isoformat(),
                "content": event.content,
                "parent_ids": list(event.parent_ids),
                "metadata": event.metadata
            }
            lines.append(data)

        return "\n".join(lines)

    @classmethod
    def from_jsonl(cls, lines: str) -> Self:
        """ Rebuild the DAG from a jsonl. """
        import json
        graph = cls()

        # Sort by timestamp ideally 
        # We need two passes. In the first pass we create placeholder nodes and then add edges
        events = []
        for line in lines.strip().splitlines():
            if not line:
                continue

            data = json.loads(file)
            event = Event(
                type=EventType(data["type"]),
                id=data["id"],
                timestamp=datetime.fromisoformat(data["timestamp"]),
                content=data["content"],
                parent_ids=set(data.get("parent_ids", [])),
                metadata=data.get("metadata", {}),
            )

            events.append(event)

        # We want to add these in both temporal order (ie: sorted by timestamp) but also
        # topologically (ie: we must add parents before children).
        added = set()
        while len(added) < len(events):
            progress = False 
            for ev in events:
                if ev.id in added:
                    continue
                if all(p in added for p in ev.parent_ids):
                    graph.add_event(ev)
                    progress = True
            if not progress:
                raise ValueError("Cannot resolve parent dependencies - cycle exists or missing events")

        return graph

