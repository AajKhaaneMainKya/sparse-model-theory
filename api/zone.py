from __future__ import annotations

from datetime import date
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Literal
from urllib import error, request

from engine.retrieval import Match


logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DAILY_DIR = ROOT / "notes" / "daily"
OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b-instruct-q4_K_M"
OPENAI_RESPONSES_PATH = "/responses"
ThinkingMode = Literal["economy", "balanced", "deep"]
VALID_THINKING_MODES = {"economy", "balanced", "deep"}
BALANCED_REASONING_SKILLS = {
    "scope_check",
    "thought_experiment",
    "unit_economics",
    "idea_origin",
    "planning_pass",
    "gap_detection_pass",
    "synthesis_pass",
}
ORCHESTRATION_SKILLS = {
    "planning_pass",
    "gap_detection_pass",
    "followup_pass",
    "synthesis_pass",
}
ALLOWED_SKILLS = [
    "scope_check",
    "first_principles",
    "visualization",
    "thought_experiment",
    "patience_check",
    "idea_origin",
    "unit_economics",
    "experiments_and_poc",
    "projections",
]
CANONICAL_SKILL_ORDER = ALLOWED_SKILLS.copy()

# Native structured-output schema for the planner. The `skills_to_run` enum is the
# actual guarantee against hallucinated skill names: the provider enforces it, so the
# model literally cannot emit a value outside ALLOWED_SKILLS for that field. Any
# free-form analysis the planner wishes existed goes in `suggested_missing_skills`,
# which is explicitly labeled as unimplemented suggestions and never executed.
PLANNER_SCHEMA_NAME = "planner_output"
PLANNER_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "skills_to_run": {
            "type": "array",
            "description": (
                "Real, implemented analysis passes to execute now. Every value MUST be "
                "one of the enum members; there is no other legal value."
            ),
            "items": {
                "type": "string",
                "enum": ALLOWED_SKILLS,
            },
        },
        "suggested_missing_skills": {
            "type": "array",
            "description": (
                "Analysis capabilities that do not exist yet but that this input seems to "
                "want. Free text — these are suggestions only and are NOT executed."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["name", "description"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["skills_to_run", "suggested_missing_skills"],
    "additionalProperties": False,
}

PLANNING_PROMPT = (
    "You are Rahul's bounded second-brain planner. Choose which analysis passes are needed "
    "for this input. Always include scope_check. Prefer fewer passes when the input is simple, "
    "but include deeper passes when the input involves money, strategy, career, risk, sales, "
    "compliance, safety, or unclear assumptions. Put the passes you actually want executed in "
    "`skills_to_run`; you may ONLY use these real, implemented skills there: scope_check, "
    "first_principles, visualization, thought_experiment, patience_check, idea_origin, "
    "unit_economics, experiments_and_poc, projections. Do NOT invent skill names in "
    "`skills_to_run`. If you wish a different kind of analysis existed, describe it in "
    "`suggested_missing_skills` (a name and a short description) instead of forcing it into "
    "`skills_to_run` — those suggestions are recorded but not run. Do not answer the question yet."
)
GAP_DETECTION_PROMPT = (
    "Review the analysis passes already produced. Identify missing information, contradictions, "
    "invented assumptions, and places where the analysis overreached. Decide whether one bounded "
    "follow-up pass is needed. Do not solve everything. If follow-up is needed, name the single focus."
)
FOLLOWUP_PROMPT_TEMPLATE = (
    "Run one bounded follow-up analysis focused only on this issue: {focus}. Use the original input "
    "and prior passes. Correct overreach, fill only what can be filled from input, and clearly mark "
    "what remains unknown."
)
SYNTHESIS_PROMPT = (
    "Create Rahul's final analysis packet from the passes. Keep it compact. Include: (1) core object "
    "of analysis, (2) strongest known claims, (3) highest-risk unknowns, (4) likely failure point, "
    "(5) next questions Rahul should answer. Do not give directives. Do not pretend unknowns are known."
)
SYSTEM_PROMPT = (
    "You are not Rahul's identity or authority over him. You are a judgment-preserving tool "
    "that surfaces his own prior reasoning. Do not tell him what to do — reflect his own "
    "precedent back to him and let him decide. End every answer with a reflective question, "
    "not a statement."
)
SKILL_PROMPTS = {
    "scope_check": (
        "You are Rahul's second-brain Zone. Before any analysis begins, state plainly: "
        "'Here is what I understand the core object of analysis to be: [X].' If there is "
        "real ambiguity about what the actual proposal, product, or aspiration IS - not what "
        "it does, but literally what it is - say so explicitly and ask: 'Is [X] the actual "
        "thing I should be analyzing, or is there a more specific target inside this that "
        "I'm missing?' If today's daily capture is provided and relevant to this input, note "
        "the connection briefly. Do not analyze yet - this step only confirms scope."
    ),
    "first_principles": (
        "Separate the verifiable claim from the narrative in this input. What does this thing "
        "actually do, cost, and produce - stripped of pitch, branding, or framing? State the "
        "claim and the evidence (or lack of it) as two distinct things. Do not editorialize."
    ),
    "visualization": (
        "Describe the structure of this input as a sequence or mapped process, anchor to "
        "anchor - not a flat bullet list. If there's a natural process or flow, lay it out "
        "that way explicitly."
    ),
    "thought_experiment": (
        "What breaks this under stress? Consider: at 2x scale, if a key person leaves, if one "
        "regulatory or market condition changes. Name a specific failure mode, not a generic "
        "risk statement. Pick the single most likely failure point, not an exhaustive list."
    ),
    "patience_check": (
        "Before any conclusion is drawn, state explicitly what is NOT yet known from this "
        "input. Do not fill gaps with assumption. List the specific missing information that "
        "would change the analysis if known."
    ),
    "idea_origin": (
        "Answer three questions directly from the input, stating 'unknown' explicitly if the "
        "input doesn't say: (1) What is the idea, and why does the idea exist? (2) Who is the "
        "idea actually for? (3) Why now - what makes this the right moment, not five years ago "
        "or five years from now?"
    ),
    "unit_economics": (
        "Drill into unit economics two ways, stating 'unknown' where the input doesn't provide "
        "enough to calculate: TOP-DOWN - market size to realistic achievable share. BOTTOM-UP - "
        "per-unit cost and revenue, built from the smallest single transaction. Do not invent "
        "numbers not present or reasonably inferable from the input."
    ),
    "experiments_and_poc": (
        "State plainly, based only on the input: What experiments or trials have actually been "
        "run? Is there a working proof of concept? If the input doesn't say, state 'not stated "
        "in input' rather than guessing."
    ),
    "projections": (
        "State what projections are given in the input, and explicitly name the assumptions "
        "those projections rest on. If no projections are given, say so."
    ),
}
SKILL_ORDER = CANONICAL_SKILL_ORDER


def get_latest_daily_capture() -> str | None:
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    path = DAILY_DIR / f"{date.today().isoformat()}.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _with_daily_capture(input_text: str, daily_capture: str | None) -> str:
    if not daily_capture:
        return input_text
    return (
        f"Today's daily capture:\n{daily_capture}\n\n"
        f"Input to analyze:\n{input_text}"
    )


def _post_json(url: str, payload: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
    encoded = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        url,
        data=encoded,
        headers=headers,
        method="POST",
    )

    with request.urlopen(http_request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _openai_response_text(data: dict[str, object]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output = data.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for content_item in content:
                if not isinstance(content_item, dict):
                    continue
                text = content_item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "\n".join(parts).strip()

    raise KeyError("output_text")


def model_for_skill(skill_name: str, mode: str) -> str:
    if mode not in VALID_THINKING_MODES:
        raise ValueError(f"unsupported thinking mode '{mode}'")

    if mode == "economy":
        return os.environ.get("OPENAI_MODEL_ECONOMY", "gpt-5.6-luna")
    if mode == "deep":
        return os.environ.get("OPENAI_MODEL_DEEP", "gpt-5.6-terra")
    if skill_name in BALANCED_REASONING_SKILLS:
        return os.environ.get("OPENAI_MODEL_BALANCED_REASONING", "gpt-5.6-terra")
    return os.environ.get("OPENAI_MODEL_ECONOMY", "gpt-5.6-luna")


def _extract_json_object(text: str) -> dict[str, object] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    return data if isinstance(data, dict) else None


def _skills_from_planner_output(text: str) -> list[str] | None:
    data = _extract_json_object(text)
    if data:
        # `skills_to_run` is the schema-constrained field; `recommended_skills` is the
        # legacy key kept only so older cached/free-text output still parses.
        for key in ("skills_to_run", "recommended_skills"):
            raw_skills = data.get(key)
            if isinstance(raw_skills, list):
                skills = [item for item in raw_skills if isinstance(item, str)]
                if skills:
                    return skills

    found = [name for name in SKILL_ORDER if re.search(rf"\b{re.escape(name)}\b", text)]
    return found or None


def _suggested_missing_skills_from_output(text: str) -> list[dict[str, str]]:
    data = _extract_json_object(text)
    if not data:
        return []
    raw = data.get("suggested_missing_skills")
    if not isinstance(raw, list):
        return []

    suggestions: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        description = item.get("description")
        suggestions.append(
            {
                "name": name.strip(),
                "description": description.strip() if isinstance(description, str) else "",
            }
        )
    return suggestions


def _sanitize_planner_skills(
    planner_skills: list[str] | None,
    skip_set: set[str],
) -> tuple[list[str], list[str]]:
    raw_skills = planner_skills or CANONICAL_SKILL_ORDER.copy()
    normalized_raw = [skill.strip() for skill in raw_skills if isinstance(skill, str) and skill.strip()]
    allowed_set = set(ALLOWED_SKILLS)
    discarded: list[str] = []

    for skill in normalized_raw:
        if skill not in allowed_set and skill not in discarded:
            discarded.append(skill)

    valid_requested = {skill for skill in normalized_raw if skill in allowed_set}
    valid_requested.add("scope_check")
    selected = [
        skill
        for skill in CANONICAL_SKILL_ORDER
        if skill in valid_requested and skill not in skip_set
    ]

    non_scope_selected = [skill for skill in selected if skill != "scope_check"]
    if not non_scope_selected:
        selected = [
            skill
            for skill in CANONICAL_SKILL_ORDER
            if skill not in skip_set
        ]

    return selected, discarded


def _format_skill_results(skill_results: list[dict[str, str]]) -> str:
    return "\n\n".join(
        f"Pass: {result.get('skill', 'unknown')}\n"
        f"Mode: {result.get('mode', 'unknown')}\n"
        f"Model: {result.get('model', 'unknown')}\n"
        f"Output:\n{result.get('output', '')}"
        for result in skill_results
    )


def _parse_gap_result(output: str) -> tuple[list[str], bool, str | None]:
    data = _extract_json_object(output)
    if data:
        raw_gaps = data.get("gaps")
        gaps = [item for item in raw_gaps if isinstance(item, str)] if isinstance(raw_gaps, list) else []
        needs_followup = bool(data.get("needs_followup"))
        raw_focus = data.get("followup_focus")
        focus = raw_focus if isinstance(raw_focus, str) and raw_focus.strip() else None
        return gaps, needs_followup, focus

    if output.startswith("Zone unavailable:"):
        return [], False, None

    gap_lines = [
        line.strip("-* 1234567890.").strip()
        for line in output.splitlines()
        if any(term in line.lower() for term in ("missing", "unknown", "contradiction", "overreach", "assumption"))
    ]
    needs_followup = "follow-up" in output.lower() and not re.search(r"\b(no|not)\s+follow-up\b", output.lower())
    focus = gap_lines[0] if needs_followup and gap_lines else None
    return gap_lines, bool(needs_followup and focus), focus


def _model_for_provider(skill_name: str | None, mode: str) -> str:
    provider = os.environ.get("ZONE_PROVIDER", "openai").lower()
    if provider == "ollama":
        return os.environ.get("SMT_ZONE_MODEL", DEFAULT_OLLAMA_MODEL)
    if skill_name is None:
        return os.environ.get("OPENAI_MODEL", "gpt-5.6-terra")
    return model_for_skill(skill_name, mode)


def _call_openai_model(
    system_prompt: str,
    input_text: str,
    model: str,
    json_schema: dict[str, object] | None = None,
    schema_name: str = "structured_output",
) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "Zone unavailable: OPENAI_API_KEY is required when ZONE_PROVIDER=openai."

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload: dict[str, object] = {
        "model": model,
        "instructions": system_prompt,
        "input": input_text,
        "reasoning": {
            "effort": os.environ.get("OPENAI_REASONING_EFFORT", "low"),
        },
    }
    if json_schema is not None:
        # Responses API structured outputs: text.format with a strict json_schema.
        # `strict: True` is what makes the enum a hard constraint rather than a hint.
        payload["text"] = {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": json_schema,
            }
        }
    headers = {
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }

    try:
        data = _post_json(f"{base_url}{OPENAI_RESPONSES_PATH}", payload, headers)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return f"Zone unavailable: OpenAI returned HTTP {exc.code}: {detail}"
    except error.URLError as exc:
        return f"Zone unavailable: could not connect to OpenAI at {base_url}: {exc.reason}"
    except TimeoutError:
        return "Zone unavailable: OpenAI request timed out."
    except OSError as exc:
        return f"Zone unavailable: OpenAI request failed: {exc}"

    try:
        return _openai_response_text(data)
    except (KeyError, TypeError) as exc:
        return f"Zone unavailable: unexpected OpenAI response shape: {exc}"


def _call_ollama_model(
    system_prompt: str,
    input_text: str,
    json_schema: dict[str, object] | None = None,
    schema_name: str = "structured_output",
) -> str:
    payload: dict[str, object] = {
        "model": os.environ.get("SMT_ZONE_MODEL", DEFAULT_OLLAMA_MODEL),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": input_text},
        ],
        "temperature": 0.2,
        "stream": False,
    }
    if json_schema is not None:
        # Chat Completions structured outputs (Ollama's OpenAI-compatible endpoint).
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": json_schema,
            },
        }
    headers = {"content-type": "application/json"}

    try:
        data = _post_json(OLLAMA_URL, payload, headers)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return f"Zone unavailable: Ollama returned HTTP {exc.code}: {detail}"
    except error.URLError as exc:
        return f"Zone unavailable: could not connect to Ollama at {OLLAMA_URL}: {exc.reason}"
    except TimeoutError:
        return "Zone unavailable: Ollama request timed out."
    except OSError as exc:
        return f"Zone unavailable: Ollama request failed: {exc}"

    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        return f"Zone unavailable: unexpected Ollama response shape: {exc}"


def call_zone_model(
    system_prompt: str,
    input_text: str,
    daily_capture: str | None = None,
    skill_name: str | None = None,
    mode: str = "balanced",
    json_schema: dict[str, object] | None = None,
    schema_name: str = "structured_output",
) -> str:
    provider = os.environ.get("ZONE_PROVIDER", "openai").lower()
    user_text = _with_daily_capture(input_text, daily_capture)
    model = _model_for_provider(skill_name, mode)

    if provider == "ollama":
        return _call_ollama_model(system_prompt, user_text, json_schema, schema_name)
    if provider != "openai":
        return f"Zone unavailable: unsupported ZONE_PROVIDER '{provider}'."
    return _call_openai_model(system_prompt, user_text, model, json_schema, schema_name)


def _run_skill(
    name: str,
    input_text: str,
    daily_capture: str | None,
    mode: str = "balanced",
) -> dict[str, str]:
    model = _model_for_provider(name, mode)
    return {
        "skill": name,
        "output": call_zone_model(SKILL_PROMPTS[name], input_text, daily_capture, name, mode),
        "mode": mode,
        "model": model,
    }


def scope_check(
    input_text: str,
    daily_capture: str | None,
    mode: str = "balanced",
) -> dict[str, str]:
    return _run_skill("scope_check", input_text, daily_capture, mode)


def first_principles(
    input_text: str,
    daily_capture: str | None,
    mode: str = "balanced",
) -> dict[str, str]:
    return _run_skill("first_principles", input_text, daily_capture, mode)


def visualization(
    input_text: str,
    daily_capture: str | None,
    mode: str = "balanced",
) -> dict[str, str]:
    return _run_skill("visualization", input_text, daily_capture, mode)


def thought_experiment(
    input_text: str,
    daily_capture: str | None,
    mode: str = "balanced",
) -> dict[str, str]:
    return _run_skill("thought_experiment", input_text, daily_capture, mode)


def patience_check(
    input_text: str,
    daily_capture: str | None,
    mode: str = "balanced",
) -> dict[str, str]:
    return _run_skill("patience_check", input_text, daily_capture, mode)


def idea_origin(
    input_text: str,
    daily_capture: str | None,
    mode: str = "balanced",
) -> dict[str, str]:
    return _run_skill("idea_origin", input_text, daily_capture, mode)


def unit_economics(
    input_text: str,
    daily_capture: str | None,
    mode: str = "balanced",
) -> dict[str, str]:
    return _run_skill("unit_economics", input_text, daily_capture, mode)


def experiments_and_poc(
    input_text: str,
    daily_capture: str | None,
    mode: str = "balanced",
) -> dict[str, str]:
    return _run_skill("experiments_and_poc", input_text, daily_capture, mode)


def projections(
    input_text: str,
    daily_capture: str | None,
    mode: str = "balanced",
) -> dict[str, str]:
    return _run_skill("projections", input_text, daily_capture, mode)


SKILL_FUNCTIONS = {
    "scope_check": scope_check,
    "first_principles": first_principles,
    "visualization": visualization,
    "thought_experiment": thought_experiment,
    "patience_check": patience_check,
    "idea_origin": idea_origin,
    "unit_economics": unit_economics,
    "experiments_and_poc": experiments_and_poc,
    "projections": projections,
}


def answer_with_context(query: str, matches: list[Match]) -> str:
    top_matches = matches[:1]
    context = "\n\n".join(
        f"Prior precedent from Rahul's own history #{index}\n"
        f"Title: {match.note.title}\n"
        f"Body:\n{match.note.body}"
        for index, match in enumerate(top_matches, start=1)
    )
    input_text = (
        "User query:\n"
        f"{query}\n\n"
        "Context below is prior precedent from Rahul's own history, not general knowledge.\n\n"
        f"{context}\n\n"
        "Reflect the relevant precedent back compactly. Do not give commands or decide for Rahul."
    )
    return call_zone_model(SYSTEM_PROMPT, input_text)


def second_brain_analysis(
    input_text: str,
    daily_capture: str | None = None,
    skip_skills: list[str] | None = None,
    mode: str = "balanced",
) -> dict[str, list[dict[str, str]]]:
    if mode not in VALID_THINKING_MODES:
        raise ValueError(f"unsupported thinking mode '{mode}'")

    if daily_capture is None:
        daily_capture = get_latest_daily_capture()

    skip_set = set(skip_skills or [])
    results: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for name in SKILL_ORDER:
        if name in skip_set:
            skipped.append({"skill": name, "reason": "explicitly skipped by request"})
            continue
        results.append(SKILL_FUNCTIONS[name](input_text, daily_capture, mode))

    return {"results": results, "skipped": skipped}


def planning_pass(
    input_text: str,
    daily_capture: str | None,
    mode: str,
    skip_skills: list[str] | None = None,
) -> dict[str, object]:
    model = _model_for_provider("planning_pass", mode)
    output = call_zone_model(
        PLANNING_PROMPT,
        input_text,
        daily_capture,
        "planning_pass",
        mode,
        json_schema=PLANNER_OUTPUT_SCHEMA,
        schema_name=PLANNER_SCHEMA_NAME,
    )
    skip_set = set(skip_skills or [])
    planner_skills = _skills_from_planner_output(output)
    recommended_skills, discarded_planner_skills = _sanitize_planner_skills(planner_skills, skip_set)

    # With the enum-constrained schema in place, skills_to_run is valid by construction,
    # so this filter is a defensive net, not the primary defense. If it ever discards a
    # name, the schema constraint itself failed (or was bypassed) — surface that loudly.
    if discarded_planner_skills:
        logger.warning(
            "planning_pass: %d skill name(s) survived the enum-constrained schema and had to "
            "be filtered post-hoc: %s. This should be impossible while the json_schema is "
            "enforced; investigate the schema/provider configuration.",
            len(discarded_planner_skills),
            discarded_planner_skills,
        )

    suggested_missing_skills = _suggested_missing_skills_from_output(output)

    data = _extract_json_object(output) or {}
    raw_rationale = data.get("rationale")
    rationale = raw_rationale if isinstance(raw_rationale, dict) else {}

    return {
        "skill": "planning_pass",
        "output": output,
        "recommended_skills": recommended_skills,
        "discarded_planner_skills": discarded_planner_skills,
        "suggested_missing_skills": suggested_missing_skills,
        "rationale": rationale,
        "mode": mode,
        "model": model,
    }


def gap_detection_pass(
    input_text: str,
    skill_results: list[dict[str, str]],
    daily_capture: str | None,
    mode: str,
) -> dict[str, object]:
    model = _model_for_provider("gap_detection_pass", mode)
    input_with_context = (
        f"Original input:\n{input_text}\n\n"
        f"Prior analysis passes:\n{_format_skill_results(skill_results)}"
    )
    output = call_zone_model(
        GAP_DETECTION_PROMPT,
        input_with_context,
        daily_capture,
        "gap_detection_pass",
        mode,
    )
    gaps, needs_followup, followup_focus = _parse_gap_result(output)

    return {
        "skill": "gap_detection_pass",
        "output": output,
        "gaps": gaps,
        "needs_followup": needs_followup,
        "followup_focus": followup_focus,
        "mode": mode,
        "model": model,
    }


def followup_pass(
    input_text: str,
    skill_results: list[dict[str, str]],
    gap_result: dict[str, object],
    daily_capture: str | None,
    mode: str,
) -> dict[str, object]:
    focus = str(gap_result.get("followup_focus") or "the single highest-risk gap")
    model = _model_for_provider("followup_pass", mode)
    input_with_context = (
        f"Original input:\n{input_text}\n\n"
        f"Prior analysis passes:\n{_format_skill_results(skill_results)}\n\n"
        f"Gap detection output:\n{gap_result.get('output', '')}"
    )
    output = call_zone_model(
        FOLLOWUP_PROMPT_TEMPLATE.format(focus=focus),
        input_with_context,
        daily_capture,
        "followup_pass",
        mode,
    )

    return {
        "skill": "followup_pass",
        "output": output,
        "focus": focus,
        "mode": mode,
        "model": model,
    }


def synthesis_pass(
    input_text: str,
    skill_results: list[dict[str, str]],
    gap_result: dict[str, object],
    followup_result: dict[str, object] | None,
    daily_capture: str | None,
    mode: str,
) -> dict[str, object]:
    model = _model_for_provider("synthesis_pass", mode)
    input_with_context = (
        f"Original input:\n{input_text}\n\n"
        f"Prior analysis passes:\n{_format_skill_results(skill_results)}\n\n"
        f"Gap detection output:\n{gap_result.get('output', '')}\n\n"
        f"Follow-up output:\n{(followup_result or {}).get('output', 'No follow-up pass was run.')}"
    )
    output = call_zone_model(
        SYNTHESIS_PROMPT,
        input_with_context,
        daily_capture,
        "synthesis_pass",
        mode,
    )

    return {
        "skill": "synthesis_pass",
        "output": output,
        "mode": mode,
        "model": model,
    }


def agentic_second_brain_analysis(
    input_text: str,
    daily_capture: str | None = None,
    skip_skills: list[str] | None = None,
    mode: str = "balanced",
) -> dict[str, object]:
    started_at = time.perf_counter()
    if mode not in VALID_THINKING_MODES:
        raise ValueError(f"unsupported thinking mode '{mode}'")

    if daily_capture is None:
        daily_capture = get_latest_daily_capture()

    skip_set = set(skip_skills or [])
    skipped = [
        {"skill": name, "reason": "explicitly skipped by request"}
        for name in SKILL_ORDER
        if name in skip_set
    ]

    plan = planning_pass(input_text, daily_capture, mode, skip_skills)
    planned_skills = plan.get("recommended_skills")
    if not isinstance(planned_skills, list):
        planned_skills = CANONICAL_SKILL_ORDER.copy()

    selected_skills = [
        item
        for item in planned_skills
        if isinstance(item, str) and item in ALLOWED_SKILLS and item not in skip_set
    ]

    skill_results = [
        SKILL_FUNCTIONS[name](input_text, daily_capture, mode)
        for name in selected_skills
        if name in SKILL_FUNCTIONS
    ]
    gap_result = gap_detection_pass(input_text, skill_results, daily_capture, mode)
    followup_result = (
        followup_pass(input_text, skill_results, gap_result, daily_capture, mode)
        if gap_result.get("needs_followup") is True
        else None
    )
    synthesis_result = synthesis_pass(
        input_text,
        skill_results,
        gap_result,
        followup_result,
        daily_capture,
        mode,
    )

    return {
        "agentic": True,
        "mode": mode,
        "plan": plan,
        "results": skill_results,
        "gap_detection": gap_result,
        "followup": followup_result,
        "synthesis": synthesis_result,
        "skipped": skipped,
        "latency_ms": round((time.perf_counter() - started_at) * 1000, 1),
    }
