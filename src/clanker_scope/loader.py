# JSONL Loader layer

import json
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from clanker_scope.logger import make_logger
from clanker_scope.graph import TraceGraph
from clanker_scope.event import EventType, Event


logger = make_logger(__name__)


class LoaderMode(Enum):
    STRICT = "strict"
    STUB = "stub"
    DROP = "drop"
    WARN = "warn"


@dataclass
class LoaderConfig:
    """ How to load a JSON """
    # Originally this was WARN but I found that unless we pass in topological order 
    # that the graph ends up incomplete.
    mode: LoaderMode = LoaderMode.STUB
    strict_timestamps: bool = False    # Require monotonically increasing times
    max_lines: int = 0                 # Limit lines (for debugging)
    skip_malformed: bool = True        # Skip over invalid lines
    encoding: str = "utf-8"
    log_missing_parents: bool = True



@dataclass
class LoaderResult:
    """ Output of a load operation """
    graph: TraceGraph
    total_lines: int
    parsed_events: int
    skipped_lines: int
    # Node status during load
    stubbed_parents: set[str] = field(default_factory=set)
    dropped_orphans: set[str] = field(default_factory=set)
    malformed_lines: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """ True if the load worked, even with warnings. """
        return self.skipped_lines == 0 or self.malformed_lines == 0



# ======== Loader ======== #
class JSONLLoader:
    """
    Loads a JSONL trace file into a TraceGraph with robust error handling.

    """

    def __init__(self, config: LoaderConfig | None = None):
        self.config = config or LoaderConfig()

    def load(self, filepath: Path | str) -> LoaderResult:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Trace file [{filepath}] not found")

        with open(filepath, "r", encoding=self.config.encoding) as f:
            lines = f.readlines()

        return self.load_lines(lines, source=str(path))

    def load_lines(self, lines: list[str], source: str="memory", verbose: bool=False) -> LoaderResult:
        """
        Parse lines in the file and build a DAG.

        Arguments:
            lines (list[str]) - Raw JSONL lines.
            source: Some user-readable source name (used for error logging).
        """

        # Deserialize all lines
        raw_events: dict[str, dict] = {}
        parsed_events: dict[str, Event] = {}
        malformed_lines: list[int] = []
        skipped_count = 0

        for idx, raw_line in enumerate(lines, start=1):
            # Skip line if empty
            if not raw_line.strip():
                continue

            # Possibly apply a line limit
            if self.config.max_lines > 0 and idx > self.config.max_lines:
                break

            try:
                data = json.loads(raw_line.strip())
            except json.JSONDecodeError as e:
                if self.config.skip_malformed:
                    malformed_lines.append(idx)
                    skipped_count += 1
                    if verbose:
                        logger.warning(f"Skipping malformed line {idx} in [{source}]: {e}")
                    continue
                else:
                    raise ValueError(f"Malformed JSON at line {idx} in {source}: {e}")

            # Validate required fields
            if not self._validate_event_data(data, idx, source):
                skipped_count += 1
                if verbose:
                    logger.info(f"Failed to validate data at index {idx}")
                continue

            # Parse into Event object (which may have existing parent ids)
            try:
                event = self._parse_event(data)
                if verbose:
                    logger.info(f"Parsed event {event}")
                # Store raw (for stubbing) and parsed
                raw_events[event.id] = data
                parsed_events[event.id] = event
            except ValueError as e:
                malformed_lines.append(idx)
                skipped_count += 1
                if verbose:
                    logger.info(f"Skipping line {idx} in {source}: {e}")

        # Phase 2 -> build the DAG and resolve dependencies
        graph = TraceGraph()
        stubbed_parents: set[str] = set()
        dropped_orphans: set[str] = set()
        warnings: list[str] = []

        # We repeatedly add events that have all parents resolved
        pending: set[str] = set(parsed_events.keys())
        added: set[str] = set()
        max_iters: int = len(pending) * 2  # If we exceed this something definitely went wrong

        for i in range(max_iters):
            if not pending:
                break

            progress = False
            for event_id in list(pending):
                event = parsed_events[event_id]
                if verbose:
                    logger.info(f"Constructing node for event {event}")

                # Check if all parents exist in graph or can be stubbed
                missing_parents = [p for p in event.parent_ids if p not in added]
                if verbose and missing_parents:
                    logger.info(f"Missing parents in iteration {i}: {missing_parents}")

                if not missing_parents:
                    # All parents are resolved - add this event
                    try:
                        graph.add_event(event)
                        added.add(event_id)
                        pending.remove(event_id)
                        progress = True
                    except ValueError as e:
                        # Cycle detected
                        warnings.append(f"Cycle detected for {event_id}: {e}")
                        pending.remove(event_id)  # Skip this - we don't know what to do with it
                        dropped_orphans.add(event_id)

                elif self.config.mode == LoaderMode.STRICT:
                    # In STRICT mode a missing parent is an error
                    raise ValueError(
                        f"Event {event_id} references missing parents: {missing_parents}"
                    )

                elif self.config.mode == LoaderMode.STUB:
                    # TODO: re-write as closure?
                    # In STUB mode we fill in the gaps with stubs
                    for parent_id in missing_parents:
                        if parent_id not in parsed_events and parent_id not in stubbed_parents:
                            stub = self._create_stub_event(parent_id)
                            try:
                                graph.add_event(stub)
                                added.add(parent_id)
                                stubbed_parents.add(parent_id)
                                warnings.append(f"Stubbed missing parent {parent_id}")
                            except ValueError:
                                # We get here when the stub has dependencies
                                warnings.append(f"Failed to stub parent {parent_id}")

                    # Try adding again in next iteration
                    progress = True   # stubbing is a kind of progress

                elif self.config.mode == LoaderMode.DROP:
                    # Drop orphaned events 
                    dropped_orphans.add(event_id)
                    pending.remove(event_id)
                    progress = True
                    warnings.append(f"Dropped orphan event: {event_id}")

                elif self.config.mode == LoaderMode.WARN:
                    # Log warning, treat event as root (no parents)
                    if self.config.log_missing_parents:
                        warnings.append(f"Event {event_id} has missing parents: {missing_parents}")
                    # Force add with empty parent set
                    modified_event = Event(
                        id=event.id,
                        type=event.type,
                        timestamp=event.timestamp,
                        content=event.content,
                        parent_ids=set(),   # Note: cleared 
                        metadata=event.metadata
                    )

                    try:
                        graph.add_event(modified_event)
                        added.add(event_id)
                        pending.remove(event_id)
                        progress = True
                    except ValueError as e:
                        warnings.append(f"Failed to add event {event_id}: {e}")
                        pending.remove(event_id)

            if not progress:
                warnings.append(f"Deadlock detected: {len(pending)} events cannot be resolved")
                break

        # Final cleanup
        if pending:
            if self.config.mode == LoaderMode.DROP:
                dropped_orphans.update(pending)
            else:
                warnings.append(f"Unresolved events remaining: {pending}")

        return LoaderResult(
            graph=graph,
            total_lines=len(lines),
            parsed_events=len(parsed_events),
            skipped_lines=skipped_count,
            stubbed_parents=stubbed_parents,
            dropped_orphans=dropped_orphans,
            malformed_lines=malformed_lines,
            warnings=warnings
        )

    def _validate_event_data(self, data: dict, line_num: int, source: str) -> bool:
        """ Check that required fields are present and valid. """
        # TODO: should these go into a configuration as well (because they vary between
        # providers)?
        required = ("id", "type", "timestamp")
        for field in required:
            if field not in data:
                if self.config.skip_malformed:
                    logger.warning(f"Line {line_num} missing [{field}]")
                    return False
                else:
                    raise ValueError(f"Line {line_num} missing [{field}]")

        # Validate type enum
        try:
            EventType(data["type"])
        except ValueError:
            if self.config.skip_malformed:
                logger.warning(f"Line {line_num} in {source} has invalid type {data['type']}")
                return False
            else:
                raise ValueError(f"Line {line_num} in {source} has invalid type {data['type']}")

        return True

    def _parse_event(self, data: dict) -> Event:
        """ Convert a JSON dict to an Event, handling type conversions. """

        # Handle the timestamp, which could be a string or float
        timestamp = data["timestamp"]
        if isinstance(timestamp, str):
            try:
                ts = datetime.fromisoformat(timestamp)
            except ValueError:
                # Try common variants
                ts = datetime.strptime(timestamp, "%T-%m-%dT%H:%M%S.%f%z")
        elif isinstance(timestamp, (int, float)):
            ts = datetime.fromtimestamp(timestamp)
        else:
            raise ValueError(f"Unsupported timestamp type: {type(timestamp)} with value {timestamp}")

        # Handle parent_ids (which could be strings, lists, or missing)
        parent_ids_raw = data.get("parent_ids", data.get("parent_id", []))
        if isinstance(parent_ids_raw, str):
            parent_ids = {parent_ids_raw}
        elif isinstance(parent_ids_raw, list):
            parent_ids = set(parent_ids_raw)
        elif isinstance(parent_ids_raw, set):
            parent_ids = parent_ids_raw
        else:
            parent_ids = set()

        return Event(
            id=str(data["id"]),
            type=EventType(data["type"]),
            timestamp=ts,
            content=data.get("content", ""),
            parent_ids=parent_ids,
            metadata=data.get("metadata", {})
        )

    def _create_stub_event(self, event_id: str) -> Event:
        """ Minimal placeholder event for a missing parent. """
        return Event(
            id=event_id,
            type=EventType.SYSTEM,
            timestamp=datetime.now(),
            content=f"[STUB] Missing parent: {event_id}",
            parent_ids=set(),
            metadata={"stub": True, "original_id": event_id}
        )
