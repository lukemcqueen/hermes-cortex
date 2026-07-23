#!/usr/bin/env python3
"""
handoff_schema — JSON Schema definitions for typed agent-to-agent handoff payloads.

Every bus EXEC carries a typed payload with expected output schema.
Output validation runs at the orchestrator before the next wave proceeds.

Schemas are registered and looked up by name. Pre-registered schemas:

    EXEC          — Outbound EXEC command payload
    EXEC_RESULT   — Inbound EXEC result payload
    WAVE_RESULT   — Wave output (aggregated results from multiple agents)

Usage:
    from handoff_schema import get_schema, register_schema, validate_payload

    schema = get_schema("EXEC")
    valid, errors = validate_payload(payload, "EXEC")
"""

import json
import os
from pathlib import Path

# ── Schema Registry ─────────────────────────────────────────────────

_SCHEMAS = {}


def register_schema(name: str, schema: dict):
    """Register a JSON Schema by name."""
    _SCHEMAS[name] = schema


def get_schema(name: str) -> dict | None:
    """Look up a registered schema by name."""
    return _SCHEMAS.get(name)


def list_schemas() -> list[str]:
    """List all registered schema names."""
    return list(_SCHEMAS.keys())


def validate_payload(payload: dict, schema_name: str) -> tuple[bool, list[str]]:
    """Validate a payload against a registered schema.

    Returns (valid: bool, errors: list[str]).
    """
    schema = get_schema(schema_name)
    if not schema:
        return False, [f"Unknown schema: '{schema_name}'"]

    errors = _validate_against_schema(payload, schema)
    return len(errors) == 0, errors


# ── Built-in JSON Schema validator (lightweight, no deps) ──────────

def _validate_against_schema(data, schema, path="$") -> list[str]:
    """Recursive JSON Schema validator. Supports draft-04 subset.

    Handles: type, properties, required, items, enum, pattern,
    minimum/maximum, minLength/maxLength, additionalProperties.
    """
    errors = []

    # Check type
    expected_type = schema.get("type")
    if expected_type:
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "object": dict,
            "array": list,
            "null": type(None),
        }
        if expected_type == "array" and isinstance(data, list):
            pass  # ok
        elif expected_type == "integer" and isinstance(data, bool):
            errors.append(f"{path}: expected integer, got boolean")
        elif expected_type in type_map and not isinstance(data, type_map[expected_type]):
            errors.append(f"{path}: expected {expected_type}, got {type(data).__name__}")
        elif expected_type not in type_map:
            pass  # unknown type, skip

    # Check enum
    enum_values = schema.get("enum")
    if enum_values is not None and data not in enum_values:
        errors.append(f"{path}: must be one of {enum_values}, got '{data}'")

    # Check pattern (string)
    pattern = schema.get("pattern")
    if pattern and isinstance(data, str):
        import re
        if not re.match(pattern, data):
            errors.append(f"{path}: does not match pattern '{pattern}'")

    # Check minLength/maxLength (string)
    min_len = schema.get("minLength")
    max_len = schema.get("maxLength")
    if isinstance(data, str):
        if min_len is not None and len(data) < min_len:
            errors.append(f"{path}: length {len(data)} < minimum {min_len}")
        if max_len is not None and len(data) > max_len:
            errors.append(f"{path}: length {len(data)} > maximum {max_len}")

    # Check minimum/maximum (number)
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if minimum is not None and data < minimum:
            errors.append(f"{path}: {data} < minimum {minimum}")
        if maximum is not None and data > maximum:
            errors.append(f"{path}: {data} > maximum {maximum}")

    # Check properties (object)
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    additional = schema.get("additionalProperties", True)

    if isinstance(data, dict):
        # Check required fields
        for field in required:
            if field not in data:
                errors.append(f"{path}.{field}: missing required field")
            elif data[field] is None:
                errors.append(f"{path}.{field}: required field is null")

        # Check each property
        for field, field_schema in properties.items():
            if field in data and data[field] is not None:
                sub_errors = _validate_against_schema(
                    data[field], field_schema, path=f"{path}.{field}"
                )
                errors.extend(sub_errors)

        # Check additional properties
        if not additional:
            allowed = set(properties.keys())
            extra = set(data.keys()) - allowed
            for field in sorted(extra):
                errors.append(f"{path}.{field}: unexpected field (additionalProperties=false)")

    # Check items (array)
    items_schema = schema.get("items")
    if isinstance(data, list) and items_schema:
        for i, item in enumerate(data):
            sub_errors = _validate_against_schema(item, items_schema, path=f"{path}[{i}]")
            errors.extend(sub_errors)

    return errors


# ── Schema Definitions ─────────────────────────────────────────────

# EXEC — outbound command payload
# Sent from orchestrator to target agent's inbox
EXEC_SCHEMA = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "EXEC",
    "description": "Execute a script on a remote agent. Sent by orchestrator, processed by agent-message-handler.",
    "type": "object",
    "required": ["command", "timeout"],
    "additionalProperties": False,
    "properties": {
        "command": {
            "type": "string",
            "description": "Script path relative to ~/.hermes-cortex/scripts/ on target agent",
            "minLength": 1,
            "pattern": r"^[a-zA-Z0-9_./-]+$"
        },
        "params": {
            "type": "array",
            "description": "Command-line arguments passed to the script",
            "items": {"type": "string"}
        },
        "timeout": {
            "type": "integer",
            "description": "Max execution time in seconds",
            "minimum": 5,
            "maximum": 300
        },
        "workdir": {
            "type": "string",
            "description": "Optional working directory on target agent",
            "pattern": r"^~?/[a-zA-Z0-9_./-]*$"
        },
        "output_schema": {
            "type": "string",
            "description": "Name of the expected output schema for result validation",
            "enum": ["EXEC_RESULT", "WAVE_RESULT", "RAW"]
        }
    }
}

# EXEC_RESULT — inbound result from agent after running EXEC
EXEC_RESULT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "EXEC_RESULT",
    "description": "Result of an EXEC command. Sent by agent-message-handler back to orchestrator's inbox.",
    "type": "object",
    "required": ["command", "success", "exit_code"],
    "additionalProperties": False,
    "properties": {
        "command": {
            "type": "string",
            "description": "The command that was executed",
            "minLength": 1
        },
        "success": {
            "type": "boolean",
            "description": "True if exit_code == 0"
        },
        "exit_code": {
            "type": "integer",
            "description": "Process exit code",
            "minimum": -1,
            "maximum": 255
        },
        "stdout": {
            "type": "string",
            "description": "Standard output (first 10000 chars)",
            "maxLength": 10000
        },
        "stderr": {
            "type": "string",
            "description": "Standard error (first 5000 chars)",
            "maxLength": 5000
        },
        "duration_ms": {
            "type": "integer",
            "description": "Execution duration in milliseconds",
            "minimum": 0
        }
    }
}

# WAVE_RESULT — aggregated result from one wave step across agents
WAVE_RESULT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "WAVE_RESULT",
    "description": "Aggregated results from one wave step across one or more agents.",
    "type": "object",
    "required": ["wave_name", "agents", "all_passed"],
    "additionalProperties": False,
    "properties": {
        "wave_name": {
            "type": "string",
            "description": "Name of the wave (e.g. 'discovery', 'impl-core', 'quality')",
            "minLength": 1
        },
        "correlation_id": {
            "type": "string",
            "description": "Correlation ID linking back to the original task",
            "minLength": 1
        },
        "agents": {
            "type": "array",
            "description": "Per-agent results",
            "items": {
                "type": "object",
                "required": ["agent", "success", "exit_code"],
                "properties": {
                    "agent": {"type": "string", "minLength": 1},
                    "success": {"type": "boolean"},
                    "exit_code": {"type": "integer", "minimum": -1, "maximum": 255},
                    "stdout": {"type": "string", "maxLength": 10000},
                    "stderr": {"type": "string", "maxLength": 5000},
                    "duration_ms": {"type": "integer", "minimum": 0}
                }
            }
        },
        "all_passed": {
            "type": "boolean",
            "description": "True if ALL agents succeeded"
        },
        "summary": {
            "type": "string",
            "description": "Human-readable summary of the wave results",
            "maxLength": 2000
        }
    }
}

# Update_REQUEST — update payload schema
UPDATE_REQUEST_SCHEMA = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "UPDATE_REQUEST",
    "description": "Request a fleet agent to update its cortex deployment.",
    "type": "object",
    "required": ["target_sha", "run_doctor"],
    "additionalProperties": False,
    "properties": {
        "target_sha": {
            "type": "string",
            "description": "Git SHA to check out",
            "minLength": 7,
            "maxLength": 40
        },
        "target_version": {
            "type": "string",
            "description": "Optional semantic version tag"
        },
        "run_doctor": {
            "type": "boolean",
            "description": "Whether to run doctor after update"
        }
    }
}

# UPDATE_RESULT — result from an agent after UPDATE_REQUEST
UPDATE_RESULT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "UPDATE_RESULT",
    "description": "Result of an UPDATE_REQUEST operation on a fleet agent.",
    "type": "object",
    "required": ["success", "sha"],
    "additionalProperties": False,
    "properties": {
        "success": {"type": "boolean"},
        "sha": {"type": "string", "minLength": 7, "maxLength": 40},
        "doctor_passed": {"type": "boolean"},
        "doctor_output": {"type": "string", "maxLength": 5000},
        "error": {"type": "string", "maxLength": 2000}
    }
}

# KILL — kill signal for fleet-wide rollback / emergency stop
KILL_SCHEMA = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "KILL",
    "description": "Emergency kill signal for a fleet agent. Stops work, rolls back, records evidence.",
    "type": "object",
    "required": ["reason"],
    "additionalProperties": False,
    "properties": {
        "reason": {"type": "string", "minLength": 1, "maxLength": 2000},
        "correlation_id": {"type": "string"},
        "rollback": {"type": "boolean"},
        "evidence_id": {"type": "string"},
        "target": {"type": "string", "maxLength": 64},
        "wave_session_id": {"type": "string"}
    }
}

KILL_ACK_SCHEMA = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "KILL_ACK",
    "description": "Acknowledgment from a fleet agent after processing a KILL signal.",
    "type": "object",
    "required": ["agent", "status"],
    "additionalProperties": False,
    "properties": {
        "agent": {"type": "string"},
        "status": {"type": "string", "enum": ["killed", "error", "not_found", "already_stopped"]},
        "rollback_status": {"type": "string", "enum": ["rolled_back", "nothing_to_rollback", "failed", "not_attempted"]},
        "running_task": {"type": "string"},
        "evidence_id": {"type": "string"},
        "wave_session_id": {"type": "string"}
    }
}


# ── Load schemas into registry ─────────────────────────────────────

def init():
    """Register all built-in schemas."""
    register_schema("EXEC", EXEC_SCHEMA)
    register_schema("EXEC_RESULT", EXEC_RESULT_SCHEMA)
    register_schema("WAVE_RESULT", WAVE_RESULT_SCHEMA)
    register_schema("UPDATE_REQUEST", UPDATE_REQUEST_SCHEMA)
    register_schema("UPDATE_RESULT", UPDATE_RESULT_SCHEMA)
    register_schema("KILL", KILL_SCHEMA)
    register_schema("KILL_ACK", KILL_ACK_SCHEMA)


# Auto-init
init()


# ── CLI for testing ────────────────────────────────────────────────

def main():
    """CLI for testing schema validation."""
    import sys
    if len(sys.argv) < 2:
        print("Usage: handoff_schema.py <schema_name> [json_file]")
        print(f"Available schemas: {', '.join(list_schemas())}")
        sys.exit(1)

    schema_name = sys.argv[1]
    schema = get_schema(schema_name)
    if not schema:
        print(f"Unknown schema: '{schema_name}'")
        sys.exit(1)

    print(f"📋 Schema: {schema_name}")
    print(json.dumps(schema, indent=2))

    if len(sys.argv) >= 3:
        file_path = sys.argv[2]
        try:
            with open(file_path) as f:
                payload = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading {file_path}: {e}")
            sys.exit(1)

        valid, errors = validate_payload(payload, schema_name)
        print()
        if valid:
            print("✅ Payload is valid.")
        else:
            print("❌ Validation errors:")
            for err in errors:
                print(f"   - {err}")
            sys.exit(1)


if __name__ == "__main__":
    main()
