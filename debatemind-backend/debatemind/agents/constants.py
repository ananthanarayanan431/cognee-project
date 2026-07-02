import os

OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")

PATTERN_TYPES = [
    "EvidenceBased",
    "AppealToAuthority",
    "StrawMan",
    "AdHominem",
    "SlipperySlope",
    "FalseEquivalence",
    "EmotionalAppeal",
    "AnecdotalEvidence",
    "Concession",
]

PATTERN_TYPE_DESCRIPTIONS: dict[str, str] = {
    "EvidenceBased": ("Claim is supported by cited facts, data, or named sources."),
    "AppealToAuthority": (
        "Claim leans on a person's/institution's status rather than the " "reasoning itself."
    ),
    "StrawMan": (
        "Misrepresents or exaggerates the opposing position before refuting "
        "the misrepresentation."
    ),
    "AdHominem": ("Attacks the arguer's character/motives instead of the argument's " "substance."),
    "SlipperySlope": (
        "Asserts an extreme outcome will follow from a moderate action "
        "without showing the causal chain."
    ),
    "FalseEquivalence": (
        "Treats two meaningfully different things as morally/logically " "equivalent."
    ),
    "EmotionalAppeal": ("Leans on fear, outrage, or sympathy in place of evidence or logic."),
    "AnecdotalEvidence": ("Generalizes from a single personal story or isolated case."),
    "Concession": ("Partially or fully accepts the opposing point rather than " "contesting it."),
}

CALIBRATION_TOPICS = [
    "Social media algorithms should be regulated by law.",
    "Standardized testing should be abolished in schools.",
    "Remote work should be the default for knowledge jobs.",
]
