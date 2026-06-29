from debatemind.agents.constants import PATTERN_TYPES


def extractor_prompt(topic: str, argument: str) -> str:
    return f"""Analyze this debate argument and return JSON only.

Topic: {topic}
Argument: {argument}

Return exactly:
{{
  "pattern_type": "<one of: {", ".join(PATTERN_TYPES)}>",
  "fallacy": "<fallacy name or null>",
  "evidence_quality": "<Strong|Moderate|Weak|Absent>"
}}"""
