from debatemind.agents.constants import PATTERN_TYPE_DESCRIPTIONS, PATTERN_TYPES

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

<examples>
<example>
<topic>Should cities ban single-use plastic bags?</topic>
<argument>My neighbor switched to reusable bags and said her grocery bill went down, so banning plastic bags clearly saves families money.</argument>
<output>{{"reasoning": "Generalizes a policy-wide economic claim from one neighbor's anecdote.", "pattern_type": "AnecdotalEvidence", "fallacy": "Hasty Generalization", "evidence_quality": "Weak", "personal_facts": []}}</output>
</example>
<example>
<topic>Should remote work be the default for office jobs?</topic>
<argument>A 2023 Stanford study tracking 16,000 workers found remote employees were 13% more productive and had measurably lower attrition.</argument>
<output>{{"reasoning": "Cites a specific, named, measurable study directly supporting the claim.", "pattern_type": "EvidenceBased", "fallacy": null, "evidence_quality": "Strong", "personal_facts": []}}</output>
</example>
<example>
<topic>Should the voting age be lowered to 16?</topic>
<argument>Anyone who opposes this clearly doesn't trust young people or believe in democracy.</argument>
<output>{{"reasoning": "Recasts opponents' position as bad faith rather than engaging their actual argument.", "pattern_type": "StrawMan", "fallacy": "Strawman", "evidence_quality": "Absent", "personal_facts": []}}</output>
</example>
<example>
<topic>Universal basic income should be implemented globally</topic>
<argument>hey im anantha, please use this name to call me</argument>
<output>{{"reasoning": "No argument was made; this is a personal introduction.", "pattern_type": "EvidenceBased", "fallacy": null, "evidence_quality": "Absent", "personal_facts": ["The user's name is Anantha."]}}</output>
</example>
<example>
<topic>Universal basic income should be implemented globally</topic>
<argument>okay fine, why we need the universal income and I feel the people stay in home and don't go to the job. also I don't really follow sports.</argument>
<output>{{"reasoning": "Concedes a labor-disincentive point without evidence.", "pattern_type": "AnecdotalEvidence", "fallacy": null, "evidence_quality": "Weak", "personal_facts": ["The user does not follow sports."]}}</output>
</example>
</examples>
{context_block}
<topic>{topic}</topic>
<argument>{argument}</argument>

Classify the message above using only the pattern types listed, and separately list any personal facts."""  # noqa: E501
