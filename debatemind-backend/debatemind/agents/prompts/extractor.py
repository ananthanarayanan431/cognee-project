from debatemind.agents.constants import PATTERN_TYPE_DESCRIPTIONS, PATTERN_TYPES
from debatemind.cognee._base import COGNITIVE_BIASES, REASONING_APPROACHES

# Ontology individuals (debate_domain.owl); null is valid for non-arguments.
_REASONING_ENUM = sorted(REASONING_APPROACHES) + [None]
_BIAS_ENUM = sorted(COGNITIVE_BIASES) + [None]

EXTRACTOR_RESPONSE_SCHEMA = {
    "name": "argument_classification",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": (  # noqa: E501
                    "One sentence: what about this argument drives the classification below."
                ),
            },
            "pattern_type": {"type": "string", "enum": PATTERN_TYPES},
            "fallacy": {"type": ["string", "null"]},
            "reasoning_approach": {
                "type": ["string", "null"],
                "enum": _REASONING_ENUM,
                "description": (  # noqa: E501
                    "The dominant mode of inference the argument uses to reach its "
                    "conclusion; null when the message makes no real argument."
                ),
            },
            "cognitive_bias": {
                "type": ["string", "null"],
                "enum": _BIAS_ENUM,
                "description": (  # noqa: E501
                    "The single cognitive bias most clearly evident in the reasoning, "
                    "or null when none is clearly present. Never force one."
                ),
            },
            "evidence_quality": {
                "type": "string",
                "enum": ["Strong", "Moderate", "Weak", "Absent"],
            },
            "personal_facts": {
                "type": "array",
                "items": {"type": "string"},
                "description": (  # noqa: E501
                    "Short standalone third-person facts the user revealed about "
                    "themselves in this message, unrelated to argument classification "
                    "(name, likes/dislikes, occupation, background, interests). "
                    "Empty array if none."
                ),
            },
        },
        "required": [
            "reasoning",
            "pattern_type",
            "fallacy",
            "reasoning_approach",
            "cognitive_bias",
            "evidence_quality",
            "personal_facts",
        ],
        "additionalProperties": False,
    },
}


def extractor_prompt(topic: str, argument: str, description: str = "") -> str:  # noqa: E501
    pattern_list = "\n".join(
        f"- {name}: {desc}" for name, desc in PATTERN_TYPE_DESCRIPTIONS.items()
    )
    reasoning_list = ", ".join(sorted(REASONING_APPROACHES))
    bias_list = ", ".join(sorted(COGNITIVE_BIASES))
    context_block = f"\n<context>{description}</context>" if description else ""
    return f"""You are a rigorous debate-pattern classifier. You read one
message from the user and do two independent jobs:

1. Identify its dominant rhetorical pattern, any logical fallacy present, and
the strength of its evidence — strictly as the argument was written, not as
you'd ideally want it written. If the message contains no argument at all
(small talk, a question, a personal remark), use pattern_type "EvidenceBased",
fallacy null, evidence_quality "Absent" as a neutral default.

2. Separately, and with an eagle eye — err on the side of catching too much
rather than too little — pull out any personal facts the user reveals about
themselves: their name, things they like or dislike, their job, hobbies,
background, or life circumstances. These have nothing to do with the debate
topic itself and should be captured even when the message is otherwise pure
small talk. Write each as one short standalone third-person sentence.

<pattern_types>
{pattern_list}
</pattern_types>

<classification_rules>
Work in this order: first write the one-sentence `reasoning`, then let it drive
the labels — never pick a label first and justify it afterward.

Dominant pattern: a message can show more than one move. Choose the single
pattern that carries the most persuasive weight — the one the argument would
collapse without. Use "EvidenceBased" only when cited facts, data, or named
sources are the load-bearing element, not merely mentioned in passing.

Pattern vs. fallacy: `pattern_type` is HOW the message tries to persuade;
`fallacy` is a distinct, named reasoning error. Name a fallacy only when one is
clearly committed — leave it null when the reasoning is merely thin or unsourced
but commits no specific fallacy. Do not invent a fallacy just because the
evidence is weak, and do not reflexively pick the fallacy that shares a name
with the pattern.

Reasoning approach — the dominant mode of inference, chosen ONLY from:
{reasoning_list}. Pick the one the conclusion most depends on (e.g. Causal for
"X causes Y", Inductive for generalizing from cases, Analogical for "like X so
Y", Deductive for rule-then-instance). Use null when the message makes no real
argument (small talk, a bare question, a personal remark) or when none of the
listed modes clearly fits (e.g. a purely rhetorical move like a strawman).

Cognitive bias — the single systematic bias most clearly on display, ONLY from:
{bias_list}. Name one only when the reasoning genuinely exhibits it
(ConfirmationBias: only cites what fits their side; Overconfidence: states a
contested claim as settled fact; MotivatedReasoning: conclusion is driven by
what they want to be true; AnchoringBias: fixates on one figure/reference;
AvailabilityBias: leans on a vivid recent example as if typical). Use null when
none is clearly present — this is the common case; never force one.

Evidence quality — judge strictly what is offered in THIS message, nothing you
could imagine adding:
  - "Strong": specific, attributable support — a named source, dataset,
    statistic, or a concrete, checkable mechanism.
  - "Moderate": real support that is unsourced, general, or only partly relevant
    (a plausible reason or a real example given without attribution).
  - "Weak": a single anecdote, hearsay, or a bare assertion presented as if it
    were proof.
  - "Absent": no evidentiary support at all — pure opinion, emotion, a question,
    or small talk.

Personal facts: capture only stable facts the user asserts about THEMSELVES
(identity, preferences, occupation, background, life circumstances). Exclude
their stance or claims on the debate topic, passing moods, hypotheticals, and
anything you infer rather than they state outright. Each fact stands alone,
third-person and self-contained ("The user works as a nurse."). De-duplicate,
and return an empty array rather than forcing a marginal one.
</classification_rules>

<examples>
<example>
<topic>Should cities ban single-use plastic bags?</topic>
<argument>My neighbor switched to reusable bags and said her grocery bill went down, so banning plastic bags clearly saves families money.</argument>
<output>{{"reasoning": "Generalizes a policy-wide economic claim from one neighbor's anecdote.", "pattern_type": "AnecdotalEvidence", "fallacy": "Hasty Generalization", "reasoning_approach": "Inductive", "cognitive_bias": "AvailabilityBias", "evidence_quality": "Weak", "personal_facts": []}}</output>
</example>
<example>
<topic>Should remote work be the default for office jobs?</topic>
<argument>A 2023 Stanford study tracking 16,000 workers found remote employees were 13% more productive and had measurably lower attrition.</argument>
<output>{{"reasoning": "Cites a specific, named, measurable study directly supporting the claim.", "pattern_type": "EvidenceBased", "fallacy": null, "reasoning_approach": "Inductive", "cognitive_bias": null, "evidence_quality": "Strong", "personal_facts": []}}</output>
</example>
<example>
<topic>Should the voting age be lowered to 16?</topic>
<argument>Anyone who opposes this clearly doesn't trust young people or believe in democracy.</argument>
<output>{{"reasoning": "Recasts opponents' position as bad faith rather than engaging their actual argument.", "pattern_type": "StrawMan", "fallacy": "Strawman", "reasoning_approach": null, "cognitive_bias": "MotivatedReasoning", "evidence_quality": "Absent", "personal_facts": []}}</output>
</example>
<example>
<topic>Universal basic income should be implemented globally</topic>
<argument>hey im anantha, please use this name to call me</argument>
<output>{{"reasoning": "No argument was made; this is a personal introduction.", "pattern_type": "EvidenceBased", "fallacy": null, "reasoning_approach": null, "cognitive_bias": null, "evidence_quality": "Absent", "personal_facts": ["The user's name is Anantha."]}}</output>
</example>
<example>
<topic>Universal basic income should be implemented globally</topic>
<argument>okay fine, why we need the universal income and I feel the people stay in home and don't go to the job. also I don't really follow sports.</argument>
<output>{{"reasoning": "Concedes a labor-disincentive point without evidence.", "pattern_type": "AnecdotalEvidence", "fallacy": null, "reasoning_approach": "Causal", "cognitive_bias": null, "evidence_quality": "Weak", "personal_facts": ["The user does not follow sports."]}}</output>
</example>
</examples>
{context_block}
<topic>{topic}</topic>
<argument>{argument}</argument>

Classify the message above using only the pattern types listed, and separately list any personal facts."""  # noqa: E501
