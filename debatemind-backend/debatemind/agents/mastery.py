from typing import Optional

from debatemind.agents.state import DebateState

MASTERY_THRESHOLD = 3


async def check_mastery(state: DebateState) -> DebateState:
    # Always start with a fresh mastery_events list for this turn (Bug 1)
    state["mastery_events"] = []

    current_pattern: Optional[str] = state.get("extracted_pattern")

    # Bug 2: per-pattern win tracking using a dict key in state.
    # If the pattern changed since last turn, reset wins for the new pattern.
    prev_pattern = state.get("_prev_pattern")
    if current_pattern and current_pattern != prev_pattern:
        # Pattern changed — reset the win counter for the new pattern
        state[f"wins_{current_pattern}"] = 0

    # Track the current pattern for next turn comparison
    state["_prev_pattern"] = current_pattern

    if state.get("outcome") == "Won" and current_pattern:
        pattern_key = f"wins_{current_pattern}"
        state[pattern_key] = state.get(pattern_key, 0) + 1
        if state[pattern_key] >= MASTERY_THRESHOLD:
            state["mastery_events"].append(current_pattern)
            state[pattern_key] = 0
    elif state.get("outcome") != "Won" and current_pattern:
        # Reset per-pattern wins on a non-win turn
        state[f"wins_{current_pattern}"] = 0

    # Keep top-level consecutive_wins in sync for any legacy readers
    state["consecutive_wins"] = state.get(f"wins_{current_pattern}", 0) if current_pattern else 0

    return state
