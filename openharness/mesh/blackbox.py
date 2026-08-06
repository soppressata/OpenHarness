"""
Reproducible Causality Layer ("The Black Box").

Captures process/network/file/syscall-like events for test runs, supports
hermetic replay and first-divergence delta diffs. Schema-versioned for
cross-minor-release replay (AC-16).
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from openharness.mesh.identity import PeerIdentity, _canonical_json
from openharness.mesh.events import EventType, make_event


SCHEMA_VERSION = "1.0.0"


class TraceEvent(BaseModel):
    """A single captured causality event."""

    seq: int
    kind: str  # process | network | file | syscall | marker
    name: str
    args: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
    result: Any = None

    def fingerprint(self) -> str:
        """Stable identity of this event for divergence comparison."""
        body = {"kind": self.kind, "name": self.name, "args": self.args, "result": self.result}
        return hashlib.sha256(_canonical_json(body)).hexdigest()[:16]


class BlackBoxRecording(BaseModel):
    """Schema-versioned recording of a test execution."""

    schema_version: str = SCHEMA_VERSION
    recording_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    test_id: str
    peer_id: str = ""
    started_at: float = Field(default_factory=time.time)
    finished_at: Optional[float] = None
    events: List[TraceEvent] = Field(default_factory=list)
    env_digest: str = ""
    input_digest: str = ""
    output: Any = None
    passed: bool = True
    signature: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def body_for_signing(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "recording_id": self.recording_id,
            "test_id": self.test_id,
            "peer_id": self.peer_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "events": [e.model_dump() for e in self.events],
            "env_digest": self.env_digest,
            "input_digest": self.input_digest,
            "output": self.output,
            "passed": self.passed,
            "metadata": self.metadata,
        }

    def content_digest(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_for_signing())).hexdigest()


class BlackBoxRecorder:
    """Zero-config capture of abstract causality events during a test."""

    def __init__(self, identity: Optional[PeerIdentity] = None, test_id: str = "test"):
        self.identity = identity
        self.test_id = test_id
        self._events: List[TraceEvent] = []
        self._seq = 0
        self._started = time.time()
        self.env_digest = hashlib.sha256(
            json.dumps({"cwd": str(Path.cwd()), "schema": SCHEMA_VERSION}, sort_keys=True).encode()
        ).hexdigest()[:16]

    def record(
        self,
        kind: str,
        name: str,
        args: Optional[Dict[str, Any]] = None,
        result: Any = None,
    ) -> TraceEvent:
        """Append a causality event to the recording."""
        self._seq += 1
        ev = TraceEvent(
            seq=self._seq,
            kind=kind,
            name=name,
            args=args or {},
            result=result,
        )
        self._events.append(ev)
        return ev

    def syscall(self, name: str, **kwargs: Any) -> TraceEvent:
        return self.record("syscall", name, args=kwargs)

    def network(self, name: str, **kwargs: Any) -> TraceEvent:
        return self.record("network", name, args=kwargs)

    def file_op(self, name: str, **kwargs: Any) -> TraceEvent:
        return self.record("file", name, args=kwargs)

    def process(self, name: str, **kwargs: Any) -> TraceEvent:
        return self.record("process", name, args=kwargs)

    def marker(self, name: str, **kwargs: Any) -> TraceEvent:
        return self.record("marker", name, args=kwargs)

    def finalize(
        self,
        output: Any = None,
        passed: bool = True,
        input_data: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BlackBoxRecording:
        """Seal the recording and optionally sign it."""
        input_digest = hashlib.sha256(_canonical_json(input_data if input_data is not None else "")).hexdigest()[:16]
        rec = BlackBoxRecording(
            test_id=self.test_id,
            peer_id=self.identity.peer_id if self.identity else "",
            started_at=self._started,
            finished_at=time.time(),
            events=list(self._events),
            env_digest=self.env_digest,
            input_digest=input_digest,
            output=output,
            passed=passed,
            metadata=metadata or {},
        )
        if self.identity:
            rec.signature = self.identity.sign_payload(rec.body_for_signing())
            event = make_event(
                EventType.BLACKBOX_CAPTURE,
                self.identity,
                payload={"recording_id": rec.recording_id, "test_id": rec.test_id, "digest": rec.content_digest()},
            )
            rec.metadata["capture_event_id"] = event.event_id
        return rec


def replay_recording(
    recording: BlackBoxRecording,
    sandbox_env_digest: Optional[str] = None,
    event_handler: Optional[Callable[[TraceEvent], Any]] = None,
) -> BlackBoxRecording:
    """Replay a recording hermetically, producing a new recording (AC-13).

    Byte-identical event stream when no drift is injected. Optional
    ``event_handler`` may return a substituted result to simulate drift.
    """
    env = sandbox_env_digest or recording.env_digest
    recorder = BlackBoxRecorder(test_id=recording.test_id)
    recorder.env_digest = env
    for ev in recording.events:
        result = ev.result
        if event_handler is not None:
            maybe = event_handler(ev)
            if maybe is not None:
                result = maybe
        recorder.record(ev.kind, ev.name, args=dict(ev.args), result=result)
    return recorder.finalize(
        output=recording.output,
        passed=recording.passed,
        metadata={"replay_of": recording.recording_id, "hermetic": True},
    )


def delta_diff(
    original: BlackBoxRecording,
    replayed: BlackBoxRecording,
) -> Dict[str, Any]:
    """Identify the first diverging event between two recordings (AC-14)."""
    n = min(len(original.events), len(replayed.events))
    first_idx: Optional[int] = None
    first_original: Optional[Dict[str, Any]] = None
    first_replayed: Optional[Dict[str, Any]] = None

    for i in range(n):
        a, b = original.events[i], replayed.events[i]
        if a.fingerprint() != b.fingerprint():
            first_idx = i
            first_original = a.model_dump()
            first_replayed = b.model_dump()
            break

    if first_idx is None and len(original.events) != len(replayed.events):
        first_idx = n
        if len(original.events) > n:
            first_original = original.events[n].model_dump()
            first_replayed = None
        else:
            first_original = None
            first_replayed = replayed.events[n].model_dump()

    identical = first_idx is None and len(original.events) == len(replayed.events)
    env_drift = original.env_digest != replayed.env_digest

    return {
        "identical": identical,
        "first_divergence_index": first_idx,
        "first_original_event": first_original,
        "first_replayed_event": first_replayed,
        "env_drift": env_drift,
        "original_event_count": len(original.events),
        "replayed_event_count": len(replayed.events),
        "original_digest": original.content_digest(),
        "replayed_digest": replayed.content_digest(),
        "cause": _infer_cause(first_original, first_replayed, env_drift, identical),
    }


def _infer_cause(
    orig: Optional[Dict[str, Any]],
    rep: Optional[Dict[str, Any]],
    env_drift: bool,
    identical: bool,
) -> str:
    if identical:
        return "none"
    if env_drift and (orig is None or rep is None or orig.get("kind") == rep.get("kind")):
        return "env_drift"
    if orig and rep:
        if orig.get("kind") == "network" or rep.get("kind") == "network":
            return "network"
        if orig.get("name") != rep.get("name"):
            return "timing_or_ordering"
        if orig.get("result") != rep.get("result"):
            return "data"
        if orig.get("args") != rep.get("args"):
            return "data"
    if orig is None or rep is None:
        return "timing_or_ordering"
    return "unknown"


def write_recording(path: str | Path, recording: BlackBoxRecording) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(recording.model_dump_json(indent=2), encoding="utf-8")
    return str(p.resolve())


def read_recording(path: str | Path) -> BlackBoxRecording:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return BlackBoxRecording(**data)


def is_compatible_schema(recording: BlackBoxRecording, major_only: bool = True) -> bool:
    """Check recording schema compatibility with this runtime (AC-16)."""
    remote = recording.schema_version.split(".")
    local = SCHEMA_VERSION.split(".")
    if major_only:
        return remote[0] == local[0]
    return recording.schema_version == SCHEMA_VERSION
