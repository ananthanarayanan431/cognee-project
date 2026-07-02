def compute_weight(logic: float | None, evidence: float | None, rhetoric: float | None) -> float:
    scores = [s for s in (logic, evidence, rhetoric) if s is not None]
    if not scores:
        return 0.5
    avg = sum(scores) / len(scores)
    return round(max(0.0, min(1.0, 1 - avg / 10)), 2)
