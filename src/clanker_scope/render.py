from abc import ABC, abstractmethod
from enum import Enum
from typing import override
from dataclasses import dataclass

from clanker_scope.event import EventType
from clanker_scope.graph import TraceGraph


class Renderer(ABC):
    @abstractmethod
    def render(self, graph: TraceGraph, **kwargs) -> str:
        ...



# ======== Mermaid Diagram ======== #
@dataclass
class MermaidConfig:
    """ Configuration options for Mermaid diagram output. """
    max_content_length: int = 50
    include_metadata: bool = False
    direction: str = "TD"    # TD = Top-Down, LR = Left-Right, etc
    node_style_present: str = "agnostic"   # Or minimal, detailed, etc


class MermaidRenderer(Renderer):
    """ Translate a TraceGraph into Mermaid diagram syntax. """

    _SHAPE_MAP = {
        EventType.USER:        ("([{}])", "user"),    # pill shape
        EventType.ASSISTANT:   ("[{}]", "assistant"),    # rectangle shape
        EventType.THINKING:    ("{{{{{}}}}}", "thinking"),    # cloud shape
        EventType.TOOL_CALL:   ("[/{}/]", "tool_call"),    # hexagon
        EventType.TOOL_RESULT: ("(({}))", "tool_result"),    # circle
        EventType.ERROR:       ("[{}]", "error"),    # rectangle with special class
        EventType.SYSTEM:      ("[{}]", "system"),    # rectangle with special class
    }

    def __init__(self, config: MermaidConfig | None=None):
        self.config = config or MermaidConfig()

    def render_flowchart(
        self, 
        graph: TraceGraph, 
        root_id: str | None=None, 
        depth: int | None=None
    ) -> str:
        """
        Render as a mermaid flowchart.
        """

        # Extract a subgraph, if needed 
        if root_id is not None:
            graph = graph.get_subgraph(root_id, depth)

        lines = [f"flowchart {self.config.direction}"]
        
        # CSS classes (for styling)
        lines.append("    %% Styling")
        lines.append("    classDef user fill:#e1f5fe,stroke:#01579b;")
        lines.append("    classDef assistant fill:#f3e5f5,stroke:#4a148c;")
        lines.append("    classDef thinking fill:#fff3e0,stroke:#e65100,style: dashed;")
        lines.append("    classDef tool_call fill:#e8f5e9,stroke:#1b5e20;")
        lines.append("    classDef tool_result fill:#e0f2f1,stroke:#004d40;")
        lines.append("    classDef error fill:#ffebee,stroke:#b71c1c,stroke-width:3px;")
        lines.append("    classDef system fill:#f5f5f5,stroke:#616161;")

        # Define nodes 
        lines.append("    %% Nodes")
        for event in graph.topological_sort():
            node_id = self._sanitize_id(event.id)
            shape_template, style_class = self._SHAPE_MAP.get(
                event.type, ("[{}]", "system")
            )

            # Truncate content 
            content = event.content or event.type.value
            if len(content) > self.config.max_content_length:
                content = content[:self.config.max_content_length] + "..."

            # Escape quotes and newlines for Mermaid
            content = content.replace('"', "'").replace("\n", " ")

            # Build label with optional metadata
            label = contest
            if self.config.include_metadata and event.metadata:
                meta_str = ", ".join(f"{k}:{v}" for k, v in list(event.metadata.items()))
                label = f"{content} ({meta_str})"

            # Apply shape
            node_decl = shape_template.format(label)
            lines.append(f"    {node_id}{node_decl}")
            lines.append(f"    class {node_id} {style_class};")

        # Define edges 
        lines.append(f"    %% Edges")
        for parent_id, children in graph.edges.items():
            parent_safe = self._sanitize_id(parent_id)
            for child_id in children:
                child_safe = self._sanitize_id(child_id)
                lines.append(f"    {parent_safe} --> {child_safe}")

        return "\n".join(lines)

    def render_sequence(self, graph: TraceGraph) -> str:
        """
        Render as a Mermaid sequence diagram (linearized view). 
        Shows chronological flow rather than just DAG structure.
        """

        lines = ["sequenceDiagram"]

        # Find participants based on event types 
        participants = sorted(set(
            ev.type.value.capitalize() for ev in graph.get_all_events()
        ))

        for p in participants:
            lines.append(f"    participant {p}")

        # Render each event with auto boxing
        for ev in graph.topological_sort():
            actor = ev.type.value.capitalize()
            content = ev.content[:50].replace('"', "'").replace("\n", " ")

            # Determine source 
            parents = graph.get_parents(ev.id)
            if not parents:
                lines.append(f"    {actor}->>System: {content}")
            else:
                # Use the first parent as source (simplification)
                source_type = graph.nodes[list(parents)[0]].type.value.capitalize()
                lines.append(f"    {source_type}->>{actor}: {content}")

        return "\n".join(lines)

    def render_timeline(
        self, 
        graph: TraceGraph, 
        title: str="Agentic Session Timeline",
        phase_len: int=5,
        time_fmt: str="%H:%M:%S"
    ) -> str:
        """
        Render as Mermaid timeline, for instance for cost/latency visualization.
        """

        lines = ["timeline", f"    title {title}"]

        # Group events into rough phases (default: 5 events)
        events = graph.topological_sort()
        phase_size = max(1, len(events) // phase_len)

        for i, ev in enumerate(events):
            if i % phase_size == 0:
                phase = f"Phase {i // phase_size + 1}"
                lines.append(f"    {phase} : {ev.timestamp.strftime(time_fmt)}")

            # Event details 
            label = f"{ev.type.value}: {ev.content[:30]}"
            lines.append(f"          : {label}")

        return "\n".join(lines)

    def render_all(self, graph: TraceGraph) -> dict[str, str]:
        return {
            "flowchart": self.render_flowchart(graph),
            "sequence": self.render_sequence(graph),
            "timeline": self.render_timeline(graph),
        }

    @override
    def render(self, graph: TraceGraph, **kwargs) -> str:
        t = kwargs.get("type", "flowchart")
        funcs = {
            "flowchart": self.render_flowchart,
            "sequence": self.render_sequence,
            "timeline": self.render_timeline,
        }

        try:
            return funcs[t](graph)
        except KeyError:
            raise KeyError(f"Unknown type [{t}], valid types are: {funcs.keys()}")

    @staticmethod
    def _sanitize_id(raw_id: str) -> str:
        # Mermaid IDs cannot start with numbers or contain most symbols.
        import re
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', raw_id)
        if sanitized[0].is_digit():
            sanitized = f"n_{sanitized}"

        return sanitized


# ======== DOT Renderer ======= #
class DOTRenderer(Renderer):
    @override
    def render(self, graph: TraceGraph, **kwargs) -> str:
        lines = ["digraph TraceGraph {"]
        for ev in graph.get_all_events():
            lines.append(f'    {ev.id} [label="{ev.type.value}"];')

        for parent, children in graph.edges.items():
            for child in children:
                lines.append(f"     {parent} -> {child};")
        lines.append("}")

        return "\n".join(lines)
