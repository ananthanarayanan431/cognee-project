from app.agents.state import DebateState

MASTERY_THRESHOLD = 3


async def check_mastery(state: DebateState) -> DebateState:
    state.setdefault("mastery_events", [])
    if state.get("outcome") == "Won":
        state["consecutive_wins"] = state.get("consecutive_wins", 0) + 1
        if state["consecutive_wins"] >= MASTERY_THRESHOLD and state.get("extracted_pattern"):
            state["mastery_events"].append(state["extracted_pattern"])
            state["consecutive_wins"] = 0
    else:
        state["consecutive_wins"] = 0
    return state
