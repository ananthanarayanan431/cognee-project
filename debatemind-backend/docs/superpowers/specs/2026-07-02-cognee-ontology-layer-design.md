# Cognee Ontology Layer — Design

**Date:** 2026-07-02
**Status:** Approved for planning

## Problem

Cognee currently builds each user's knowledge graph via pure LLM-driven
extraction. Every `cognee.cognify()` call in `debatemind/cognee/fingerprint.py`
omits the `ontology_file_path` argument, so `gpt-4.1-mini` invents entity and
relationship labels ad hoc on each run. The result is inconsistent entity typing
across sessions, which weakens the topic-aware recall that the opponent and
progress views depend on.

Cognee (v0.1.40) supports guiding extraction with a formal OWL/RDF ontology:
`cognee.cognify(..., ontology_file_path=<path>)`. We want to supply a
domain ontology for debate so the extractor uses a controlled vocabulary.

## How Cognee consumes the ontology (verified)

- `cognify()` signature: `ontology_file_path: Optional[str] = None`.
- `OntologyResolver.__init__` (`cognee/modules/ontology/rdf_xml/OntologyResolver.py`)
  only **reads** the file: `if ontology_file and os.path.exists(ontology_file): get_ontology(ontology_file).load()`.
- If the path is `None` or the file is missing, it logs a warning and falls back
  to an empty ontology (`http://example.org/empty_ontology`) — **no crash**.
- The parser is `owlready2`, already installed as a Cognee dependency.

**Conclusion on file location (the deployability question):** Cognee never
*creates* the file. It is a static, hand-authored, version-controlled schema —
read-only at runtime. We commit it inside the `debatemind/` package so it ships
in the Docker image automatically via the existing `COPY debatemind/ debatemind/`
line; no Dockerfile or CWD assumptions. `owlready2` is already present, so no new
dependency.

## Design

### 1. Static asset — `debatemind/cognee/ontology/debate_domain.owl`

An RDF/XML OWL file with a **focused** schema matching exactly what
`fingerprint.py` writes today:

Classes and named individuals:
- `ArgumentPattern` — `EvidenceBased`, `Emotional`, `Analogical`, `Statistical`, `Rhetorical`
- `Fallacy` — `AdHominem`, `StrawMan`, `SlipperySlope`, `FalseDichotomy`, `AppealToEmotion`, `HastyGeneralization`
- `EvidenceQuality` — `Strong`, `Moderate`, `Weak`
- `Outcome` — `Won`, `Lost`, `Draw`
- `ThinkingStyle` — `Logic`, `Evidence`, `Rhetoric`
- `MasteryStatus` — `Mastered`, `Reactivated`, `Active`

Object properties (relations):
- `usesPattern` (Argument → ArgumentPattern)
- `exhibitsFallacy` (Argument → Fallacy)
- `hasEvidenceQuality` (Argument → EvidenceQuality)
- `hasOutcome` (Argument/Session → Outcome)
- `hasMasteryStatus` (ArgumentPattern → MasteryStatus)

Scope guard (YAGNI): no broad fallacy taxonomy, no topic hierarchy, no
per-user ontologies, no build/generation step. One committed file.

### 2. Resolver helper — `debatemind/cognee/_base.py`

```python
from pathlib import Path

ONTOLOGY_PATH = Path(__file__).parent / "ontology" / "debate_domain.owl"

def ontology_file() -> str | None:
    """Absolute path to the debate ontology, or None if absent.

    Returning None makes cognify() behave exactly as before (empty-ontology
    fallback), so a missing asset degrades gracefully instead of crashing.
    """
    return str(ONTOLOGY_PATH) if ONTOLOGY_PATH.exists() else None
```

Path is resolved from `__file__`, independent of the process working directory.

### 3. Wiring — `debatemind/cognee/fingerprint.py`

All five `cognee.cognify(datasets=dataset, ...)` calls gain
`ontology_file_path=ontology_file()`:
- `remember_argument`
- `remember_session_summary`
- `improve_fingerprint`
- `forget_pattern`
- `reactivate_pattern_fact`

Import `ontology_file` from `debatemind.cognee._base`. No signature or behavior
change to any public function in `debatemind/cognee/__init__.py`.

## Error handling / production safety

- **Missing file:** `ontology_file()` returns `None`; cognify proceeds with the
  empty-ontology fallback exactly as today. No exception.
- **Malformed OWL:** guarded by a test that loads it via `owlready2` in CI, so a
  broken file never reaches production. At runtime a parse failure would raise
  `OntologyInitializationError` inside cognify — same failure surface as any
  cognify error, already wrapped in `asyncio.wait_for(..., COGNIFY_TIMEOUT)` and
  the existing try/except in the worker/task callers.
- **No new runtime dependency, no Dockerfile change, no env var.**

## Testing

New `tests/test_ontology.py`:
1. `ONTOLOGY_PATH` exists and `ontology_file()` returns a non-None path.
2. The `.owl` file parses via `owlready2.get_ontology(path).load()` and exposes
   the expected classes (e.g. `Fallacy`, `ArgumentPattern`).

Regression: existing `tests/test_cognee_*.py` continue to pass (they mock cognee,
so the new kwarg must not break their assertions — update mocks/assertions if
they assert exact `cognify` call args).

## Out of scope

- Dynamic or per-user ontologies
- Fallacy taxonomy expansion / topic hierarchy
- Any change to search/recall behavior
- Build-time ontology generation
