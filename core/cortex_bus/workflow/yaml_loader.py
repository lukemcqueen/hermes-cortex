"""
YAML workflow loader — safe_load + validate → Workflow dataclass.

Always uses yaml.safe_load(). Never yaml.load().
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Optional

import yaml

from . import Workflow, WorkflowStep, RouteIf


class WorkflowLoadError(Exception):
    """Raised when a workflow YAML fails validation."""


def load_workflow(path: str | Path) -> Workflow:
    """Load and validate a workflow from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise WorkflowLoadError(f"Workflow file not found: {path}")
    
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise WorkflowLoadError("Workflow YAML must be a mapping (dict) at top level")
    
    return _parse_workflow(raw, source=str(path))


def parse_workflow_yaml(yaml_str: str, source: str = "<inline>") -> Workflow:
    """Parse a workflow from a YAML string (for testing without files)."""
    raw = yaml.safe_load(yaml_str)
    if not isinstance(raw, dict):
        raise WorkflowLoadError("Workflow YAML must be a mapping (dict) at top level")
    return _parse_workflow(raw, source=source)


def _parse_workflow(raw: dict, source: str = "") -> Workflow:
    """Parse validated YAML dict into Workflow dataclass."""
    errors = []
    
    name = raw.get("name", "")
    if not name:
        errors.append("workflow.name is required")
    
    steps_raw = raw.get("steps", [])
    if not isinstance(steps_raw, list) or not steps_raw:
        errors.append("workflow.steps must be a non-empty list")
    
    start_step = raw.get("start_step", "start")
    
    if errors:
        raise WorkflowLoadError(f"Workflow validation errors ({source}): " + "; ".join(errors))
    
    # Parse steps
    step_names = set()
    steps = []
    for i, s in enumerate(steps_raw):
        step_name = s.get("name", f"step_{i}")
        if step_name in step_names:
            errors.append(f"Duplicate step name: '{step_name}'")
        step_names.add(step_name)
        
        route_if = None
        if "route_if" in s:
            route_if = RouteIf.from_dict(s["route_if"])
        
        step = WorkflowStep(
            name=step_name,
            assigned_to=s.get("assigned_to", "moses"),
            prompt=s.get("prompt"),
            skills=s.get("skills", []),
            timeout_seconds=s.get("timeout_seconds", 300),
            max_retries=s.get("max_retries", 2),
            depends_on=s.get("depends_on", []),
            route_if=route_if,
            parallel=s.get("parallel", False),
            human_review=s.get("human_review", False),
        )
        steps.append(step)
    
    # Validate DAG
    errors += _validate_dag(steps, start_step, source)
    
    if errors:
        raise WorkflowLoadError(f"Workflow validation errors ({source}): " + "; ".join(errors))
    
    return Workflow(
        name=name,
        version=raw.get("version", "1.0.0"),
        description=raw.get("description"),
        steps=steps,
        start_step=start_step,
        deadline_seconds=raw.get("deadline_seconds"),
        tags=raw.get("tags", {}),
    )


def _validate_dag(steps: list[WorkflowStep], start_step: str, source: str) -> list[str]:
    """Validate workflow DAG structure."""
    errors = []
    step_names = {s.name for s in steps}
    
    # Start step must exist
    if start_step not in step_names:
        errors.append(f"start_step '{start_step}' not found in steps")
    
    # All depends_on references must exist
    for s in steps:
        for dep in s.depends_on:
            if dep not in step_names:
                errors.append(f"Step '{s.name}' depends on unknown step '{dep}'")
        if s.route_if:
            for route_target in s.route_if.routes.values():
                if route_target not in step_names and route_target != "_end" and not route_target.startswith("_end:"):
                    errors.append(
                        f"Step '{s.name}' routes to unknown step '{route_target}'"
                    )
    
    # Detect circular dependencies using DFS
    visited = set()  # grey nodes (currently in DFS path)
    completed = set()  # black nodes (fully processed)
    
    def _has_cycle(step_name: str, path: list[str]) -> bool:
        if step_name in completed:
            return False
        if step_name in visited:
            errors.append(f"Circular dependency detected: {' → '.join(path + [step_name])}")
            return True
        if step_name not in step_names:
            return False
        
        visited.add(step_name)
        step = next(s for s in steps if s.name == step_name)
        
        for dep in step.depends_on:
            if _has_cycle(dep, path + [step_name]):
                return True
        
        visited.remove(step_name)
        completed.add(step_name)
        return False
    
    for s in steps:
        _has_cycle(s.name, [])
    
    return errors
