"""Optional LLM-as-judge for free-text answers.

Deterministic checks come first and are authoritative where they can be. The judge covers
what regexes can't, such as "does this summary invent features". A judge failure (bad JSON,
API error) is reported as ``judge_error`` and is never counted as a model failure.
"""

from __future__ import annotations

import json
import re
from typing import Any

from relay.chat.usage import read_usage

JUDGE_PROMPT = """You are grading an AI assistant's answer. Judge ONLY against the source material.

Task given to the assistant:
{prompt}

Source material the assistant had access to:
{material}

Assistant's answer:
{answer}

Criteria:
{criteria}

Score from 1 to 5:
5 = fully accurate and complete, nothing unsupported
4 = accurate with a minor omission
3 = partly accurate or notably incomplete
2 = contains a claim the source does not support
1 = wrong or unrelated

Reply with ONLY a JSON object: {{"score": <1-5>, "reasoning": "<one sentence>"}}"""


def parse_judge_reply(text: str) -> dict[str, Any]:
    """Pull {"score", "reasoning"} out of a model reply that may wrap the JSON in prose."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return {"score": None, "error": "no JSON object in judge reply"}
    try:
        data = json.loads(match.group(0))
        score = int(data["score"])
    except (ValueError, KeyError, TypeError) as exc:
        return {"score": None, "error": f"unparseable judge reply: {exc}"}
    if not 1 <= score <= 5:
        return {"score": None, "error": f"score out of range: {score}"}
    return {"score": score, "reasoning": str(data.get("reasoning", ""))[:300]}


class LLMJudge:
    def __init__(self, client: Any, model_id: str, *, omit_temperature: bool = False):
        self.client = client
        self.model_id = model_id
        self.omit_temperature = omit_temperature

    def grade(self, task: dict[str, Any], answer: str, material: str) -> dict[str, Any]:
        rubric = task["expect"]["rubric"]
        prompt = JUDGE_PROMPT.format(
            prompt=task["prompt"], material=material or "(none)", answer=answer, criteria=rubric["criteria"]
        )
        messages = [{"role": "user", "content": prompt}]
        last_error = "unknown"
        # Claude 4.7+ rejects temperature below 1; other hosts sometimes reject it entirely.
        variants: tuple[dict[str, Any], ...] = (
            ({},) if self.omit_temperature else ({"temperature": 0}, {})
        )
        for kwargs in variants:
            try:
                reply = self.client.chat.completions.create(model=self.model_id, messages=messages, **kwargs)
                graded = parse_judge_reply(reply.choices[0].message.content or "")
                # What the judge itself cost, kept apart from the model under test.
                graded["model"] = self.model_id
                if getattr(reply, "usage", None) is not None:
                    graded["usage"] = read_usage(reply.usage)
                return graded
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
        return {"score": None, "error": last_error}
