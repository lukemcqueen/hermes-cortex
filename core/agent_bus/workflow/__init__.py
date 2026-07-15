"""
Workflow engine data models — Step, Workflow, RouteIf, WorkflowPayload.

All immutable dataclasses that define the contract between YAML definitions
and the runtime engine. Used in conjunction with Postgres rows for persistence.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Optional


@dataclass
class RouteIf:
    """Deterministic routing rule: step output status → next step name.
    
    Normalized at load time (case-insensitive keys, _fallback preserved).
    Snapshot into `agent_workflow_steps.route_if` at dispatch — never
    re-read from YAML for in-flight workflows.
    """
    routes: dict[str, str] = field(default_factory=dict)
    fallback: Optional[str] = None
    
    def get_next(self, status: str) -> Optional[str]:
        """Evaluate route for a given status string.
        
        Case-insensitive match with _fallback support.
        Returns:
            Next step name if matched
            _fallback value if no match but _fallback defined
            None if no route found (workflow will fail)
        """
        normalized = status.lower().strip()
        if normalized in self.routes:
            return self.routes[normalized]
        return self.fallback
    
    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.routes.items()}
        if self.fallback is not None:
            d["_fallback"] = self.fallback
        return d
    
    @classmethod
    def from_dict(cls, data: dict[str, str]) -> RouteIf:
        """Build from YAML dict, normalizing keys to lowercase.
        
        _fallback key is preserved as-is.
        """
        routes = {}
        fallback = None
        for k, v in (data or {}).items():
            if k == "_fallback":
                fallback = v
            else:
                routes[k.lower().strip()] = v
        return cls(routes=routes, fallback=fallback)


@dataclass
class WorkflowStep:
    """A single step in a workflow DAG."""
    name: str
    assigned_to: str  # agent name or 'luke' for HIL
    prompt: Optional[str] = None
    skills: list[str] = field(default_factory=list)
    timeout_seconds: int = 300
    max_retries: int = 2
    depends_on: list[str] = field(default_factory=list)  # step names this depends on
    route_if: Optional[RouteIf] = None
    parallel: bool = False
    human_review: bool = False  # True if this step needs human approval


@dataclass
class Workflow:
    """A complete workflow definition.
    
    Loaded from YAML, validated, then snapshotted into Postgres at dispatch.
    After dispatch, NEVER re-read from YAML — routing uses the stored snapshot.
    """
    name: str
    version: str = "1.0.0"
    description: Optional[str] = None
    steps: list[WorkflowStep] = field(default_factory=list)
    start_step: str = "start"
    deadline_seconds: Optional[int] = None  # Overall workflow SLA
    tags: dict[str, str] = field(default_factory=dict)
    
    def get_step(self, name: str) -> Optional[WorkflowStep]:
        for step in self.steps:
            if step.name == name:
                return step
        return None
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "start_step": self.start_step,
            "deadline_seconds": self.deadline_seconds,
            "steps": [
                {
                    "name": s.name,
                    "assigned_to": s.assigned_to,
                    "prompt": s.prompt,
                    "skills": s.skills,
                    "timeout_seconds": s.timeout_seconds,
                    "max_retries": s.max_retries,
                    "depends_on": s.depends_on,
                    "route_if": s.route_if.to_dict() if s.route_if else None,
                    "parallel": s.parallel,
                    "human_review": s.human_review,
                }
                for s in self.steps
            ],
            "tags": self.tags,
        }
