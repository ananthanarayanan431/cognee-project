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
        },
        "required": ["reasoning", "pattern_type", "fallacy", "evidence_quality"],
        "additionalProperties": False,
    },
}


def extractor_prompt(topic: str, argument: str) -> str:  # noqa: E501
    pattern_list = "\n".join(
        f"- {name}: {desc}" for name, desc in PATTERN_TYPE_DESCRIPTIONS.items()
    )
    return f"""You are a rigorous debate-pattern classifier. You read one
argument turn and identify its dominant rhetorical pattern, any logical
fallacy present, and the strength of its evidence — strictly as the
argument was written, not as you'd ideally want it written.

<pattern_types>
{pattern_list}
</pattern_types>

<examples>
<example>
<topic>Should cities ban single-use plastic bags?</topic>
<argument>My neighbor switched to reusable bags and said her grocery bill went down, so banning plastic bags clearly saves families money.</argument>
<output>{{"reasoning": "Generalizes a policy-wide economic claim from one neighbor's anecdote.", "pattern_type": "AnecdotalEvidence", "fallacy": "Hasty Generalization", "evidence_quality": "Weak"}}</output>
</example>
<example>
<topic>Should remote work be the default for office jobs?</topic>
<argument>A 2023 Stanford study tracking 16,000 workers found remote employees were 13% more productive and had measurably lower attrition.</argument>
<output>{{"reasoning": "Cites a specific, named, measurable study directly supporting the claim.", "pattern_type": "EvidenceBased", "fallacy": null, "evidence_quality": "Strong"}}</output>
</example>
<example>
<topic>Should the voting age be lowered to 16?</topic>
<argument>Anyone who opposes this clearly doesn't trust young people or believe in democracy.</argument>
<output>{{"reasoning": "Recasts opponents' position as bad faith rather than engaging their actual argument.", "pattern_type": "StrawMan", "fallacy": "Strawman", "evidence_quality": "Absent"}}</output>
</example>
</examples>

<topic>{topic}</topic>
<argument>{argument}</argument>

Classify the argument above using only the pattern types listed."""  # noqa: E501
