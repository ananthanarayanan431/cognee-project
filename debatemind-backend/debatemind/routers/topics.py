import json
import logging

from fastapi import APIRouter, HTTPException

from debatemind.agents.client import openrouter
from debatemind.config import settings
from debatemind.schemas.topics import DebatableQuestion, GenerateTopicsIn
from debatemind.types import SuccessResponse

router = APIRouter()

QUESTIONS: list[DebatableQuestion] = [
    # POLICY
    DebatableQuestion(
        id="eu-ai-act-global-standard",
        domain="POLICY",
        title="The EU AI Act should become the global standard for AI governance",
        description=(
            "The EU AI Act imposes strict risk classifications, mandatory audits, and bans "
            "on certain AI applications. Proponents argue it sets a precedent for protecting "
            "citizens globally. Critics contend applying EU-level regulation worldwide stifles "
            "innovation, ignores non-European legal traditions, and creates compliance burdens "
            "that entrench incumbents while locking out smaller nations from the AI economy."
        ),
    ),
    DebatableQuestion(
        id="carbon-tax-over-ets",
        domain="POLICY",
        title="Carbon taxes are more effective than emissions trading schemes",
        description=(
            "Emissions trading schemes cap total emissions and let companies buy and sell permits, "
            "creating market flexibility. Carbon taxes directly price emissions at a fixed rate. "
            "The debate centres on which mechanism better balances economic efficiency, political "
            "feasibility, and emissions certainty — and whether hybrid approaches undermine the "
            "benefits of either."
        ),
    ),
    DebatableQuestion(
        id="platform-liability-amplification",
        domain="POLICY",
        title=(
            "Social platforms should bear legal liability for algorithmically amplified "
            "harmful content"
        ),
        description=(
            "Recommendation algorithms surface content to billions of users, often prioritising "
            "engagement over accuracy or safety. When platforms actively amplify content, some "
            "argue they cross from neutral conduit to active publisher. The debate involves "
            "Section 230 protections, the economics of content moderation, free speech principles, "
            "and whether liability would drive platforms toward over-censorship."
        ),
    ),
    # TECHNOLOGY
    DebatableQuestion(
        id="pause-ai-capability-research",
        domain="TECHNOLOGY",
        title="AI capability research should be paused until alignment is solved",
        description=(
            "The alignment problem — ensuring advanced AI systems reliably pursue beneficial goals "
            "— remains unsolved. Some researchers argue we are racing toward systems we cannot "
            "control, while others contend pausing cedes ground to less safety-conscious actors "
            "and that alignment research benefits from capabilities advances. The debate hinges "
            "on estimates of risk, timelines, and whether a pause is even enforceable."
        ),
    ),
    DebatableQuestion(
        id="open-source-frontier-ai",
        domain="TECHNOLOGY",
        title="Frontier AI models should be open-sourced by default",
        description=(
            "Open-sourcing large AI models accelerates research, democratises access, and allows "
            "independent safety auditing. Opponents warn that open weights for highly capable "
            "models could enable mass-scale misuse — from bioweapons synthesis to disinformation "
            "— and that safety testing is harder once a model is in the wild. The line between "
            "'frontier' and 'open research model' is itself contested."
        ),
    ),
    DebatableQuestion(
        id="ban-algorithmic-hiring",
        domain="TECHNOLOGY",
        title="Algorithmic hiring tools should be banned until bias can be certified away",
        description=(
            "AI-assisted recruitment promises consistent, scalable candidate evaluation but has "
            "repeatedly been found to encode historical biases in race, gender, and class. "
            "Advocates for a ban argue we cannot ethically deploy tools whose failure modes harm "
            "vulnerable candidates. Defenders say imperfect algorithms are still better than "
            "inconsistent human judgment, and that bias audits provide a credible path forward."
        ),
    ),
    # SOCIETY
    DebatableQuestion(
        id="ban-social-media-under-16",
        domain="SOCIETY",
        title="Social media should be legally prohibited for users under 16",
        description=(
            "Several countries are moving to restrict minors from social platforms, citing "
            "evidence linking heavy use to anxiety, depression, and disrupted development. "
            "Opponents argue such bans are unenforceable, strip young people of digital literacy "
            "opportunities, and that harms are driven by design choices that should be regulated "
            "directly. The debate also touches on parental rights versus state intervention."
        ),
    ),
    DebatableQuestion(
        id="ubi-erodes-work-dignity",
        domain="SOCIETY",
        title="Universal basic income undermines the dignity of work",
        description=(
            "UBI proposals promise economic security without conditionality, but critics argue "
            "that decoupling income from contribution erodes the social meaning of work, weakens "
            "communities built around shared labour, and disincentivises participation. Supporters "
            "contend dignity comes from security and choice, not compulsion, and that UBI would "
            "free people to pursue more meaningful forms of contribution."
        ),
    ),
    DebatableQuestion(
        id="competency-based-credentials",
        domain="SOCIETY",
        title="Universities should be replaced by competency-based credentialing",
        description=(
            "Rising tuition costs and the decoupling of degrees from job outcomes have accelerated "
            "interest in stackable credentials, bootcamps, and employer-designed certificates. "
            "Proponents argue competency-based systems are more efficient and equitable. Critics "
            "warn that universities provide irreplaceable intellectual breadth, social capital "
            "formation, and civic functions that narrow credentials cannot replicate."
        ),
    ),
    # LIFE
    DebatableQuestion(
        id="remote-work-harms-cohesion",
        domain="LIFE",
        title="Remote work permanently harms team cohesion and long-term career growth",
        description=(
            "The shift to remote work improved flexibility and removed commuting costs but reduced "
            "spontaneous collaboration, mentorship, and the informal socialisation that builds "
            "trust. Junior employees may miss formative learning from proximity to senior "
            "colleagues. Counter-arguments hold that strong async practices and intentional "
            "culture-building can fully substitute for physical co-location."
        ),
    ),
    DebatableQuestion(
        id="parental-monitoring-adult-finances",
        domain="LIFE",
        title="Parents should not have the right to monitor their adult children's finances",
        description=(
            "Financial oversight by parents over adult children — via shared accounts, location "
            "tracking, or conditional support — raises questions about autonomy, power dynamics, "
            "and healthy boundaries. Supporters of monitoring argue it reflects genuine care and "
            "shared financial risk. Critics contend it prolongs dependency and is a vector for "
            "control in unhealthy family systems."
        ),
    ),
    DebatableQuestion(
        id="work-life-balance-privilege",
        domain="LIFE",
        title="The pursuit of work-life balance is a privilege only the wealthy can afford",
        description=(
            "Discourse around work-life balance assumes workers have schedule discretion, "
            "meaningful savings, and flexible roles. For hourly workers, gig economy participants, "
            "and those in caring roles, 'balance' is a meaningless abstraction. The debate touches "
            "on structural labour conditions, the moral weight of individual choices versus "
            "systemic change, and whether the wellness industry profits from medicalising problems "
            "that require political solutions."
        ),
    ),
]


@router.get(
    "/suggest",
    response_model=SuccessResponse[list[DebatableQuestion]],
    summary="Get debate question suggestions",
)
async def suggest():
    return SuccessResponse(data=QUESTIONS)


_logger = logging.getLogger(__name__)

_GENERATE_SYSTEM = (
    "You are a debate-question writer. Return ONLY valid JSON with a single key "
    '"questions" whose value is an array of debate question objects. '
    "Each object must have exactly these keys: "
    '"id" (kebab-case slug derived from the title), '
    '"domain" (the domain string passed in), '
    '"title" (a concise debatable statement), '
    '"description" (3-5 sentences explaining the stakes, main angles, and why it is contested). '
    "Do not include any text outside the JSON."
)


@router.post(
    "/generate",
    response_model=SuccessResponse[list[DebatableQuestion]],
    summary="Generate debate questions for a domain",
)
async def generate(body: GenerateTopicsIn):
    count = min(body.count, 10)
    user_prompt = (
        f"Generate {count} original, debatable questions for the domain: {body.domain}. "
        "Each question should be thought-provoking, contestable, and distinct from the others."
    )
    try:
        completion = await openrouter.chat.completions.create(
            model=settings.main_model,
            max_tokens=1500,
            messages=[
                {"role": "system", "content": _GENERATE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = completion.choices[0].message.content or ""
        parsed = json.loads(raw)
        questions = [DebatableQuestion(**q) for q in parsed["questions"]]
    except Exception as exc:
        _logger.error("Topic generation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Topic generation failed. Please try again.")
    return SuccessResponse(data=questions)
