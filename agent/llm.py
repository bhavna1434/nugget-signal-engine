"""
Claude API wrapper.

Thin on purpose. Everything interesting lives in the prompts and the critic
loop; this file only handles calling, retrying, and counting.

The API key is read from the ANTHROPIC_API_KEY environment variable and is
never written to disk, never logged, and never included in any run artefact.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

import anthropic

# Sonnet for drafting and critique: fast enough for a multi-round loop, and
# the task is judgement over a short brief rather than deep reasoning.
# Override per call where a step genuinely needs more.
DEFAULT_MODEL = "claude-sonnet-5-5"

MAX_RETRIES = 3


@dataclass
class Usage:
    """Running token/cost accounting so a run's cost is visible, not a surprise."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    by_step: dict = field(default_factory=dict)

    def add(self, step: str, inp: int, out: int) -> None:
        self.calls += 1
        self.input_tokens += inp
        self.output_tokens += out
        s = self.by_step.setdefault(step, {"calls": 0, "in": 0, "out": 0})
        s["calls"] += 1
        s["in"] += inp
        s["out"] += out

    def summary(self) -> str:
        return (
            f"{self.calls} API calls, {self.input_tokens:,} in / "
            f"{self.output_tokens:,} out tokens"
        )


class LLM:
    def __init__(self, model: str = DEFAULT_MODEL, usage: Usage | None = None):
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise SystemExit(
                "ANTHROPIC_API_KEY is not set.\n\n"
                "  export ANTHROPIC_API_KEY=sk-ant-...\n\n"
                "Get one at console.anthropic.com -> API keys. A full run of this\n"
                "agent costs a few cents."
            )
        self.client = anthropic.Anthropic(api_key=key)
        self.model = model
        self.usage = usage or Usage()

    def complete(
        self,
        step: str,
        system: str,
        user: str,
        max_tokens: int = 4000,
        effort: str | None = None,
        prefill: str | None = None,
    ) -> str:
        """
        One call. Retries on transient errors, fails loudly on everything else.

        NOTE ON SAMPLING: this SDK version (1.15.x) removed `temperature` from
        messages.create entirely and replaced it with output_config.effort
        ("low" | "medium" | "high" | "xhigh" | "max"). That is a different knob:
        it controls how much work the model puts into the response, not how
        randomly it samples. So we cannot pin the critic to temperature 0 and
        call it deterministic - repeated reviews of the same draft may differ
        slightly. Effort "high" on the critic buys thoroughness, not
        reproducibility. Worth knowing before quoting a score as exact.
        """
        messages = [{"role": "user", "content": user}]
        if prefill:
            # Prefilling the assistant turn is how we force a response to start
            # as JSON instead of with a preamble we would then have to strip.
            messages.append({"role": "assistant", "content": prefill})

        kwargs = {}
        if effort:
            kwargs["output_config"] = {"effort": effort}

        last_err = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=messages,
                    **kwargs,
                )
                self.usage.add(
                    step, resp.usage.input_tokens, resp.usage.output_tokens
                )
                # The response may contain several content blocks, and with
                # extended thinking the FIRST one is a ThinkingBlock with no
                # .text attribute. Taking content[0] blindly crashes. Collect
                # every text block instead, in order.
                parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
                if not parts:
                    raise SystemExit(
                        f"Step '{step}' returned no text block. Block types: "
                        f"{[getattr(b, 'type', '?') for b in resp.content]}"
                    )
                text = "".join(parts)
                return (prefill + text) if prefill else text
            except (anthropic.RateLimitError, anthropic.APIConnectionError) as e:
                last_err = e
                time.sleep(2 ** attempt)
            except anthropic.APIStatusError as e:
                raise SystemExit(f"API error on step '{step}': {e}") from e
        raise SystemExit(f"Step '{step}' failed after {MAX_RETRIES} retries: {last_err}")

    def json_complete(
        self, step: str, system: str, user: str, max_tokens: int = 1500
    ) -> dict:
        """
        Call expecting JSON back.

        Extracts the outermost JSON object from the response.

        An earlier version prefilled the assistant turn with '{' to force the
        reply to start as JSON. That is incompatible with extended thinking,
        which this model returns by default, so we parse instead: try the whole
        string, then fall back to the outermost braces, which handles a reply
        wrapped in a code fence or a sentence of preamble.

        BUDGET NOTE: thinking tokens count against max_tokens. At effort "high"
        with a 1200 budget the model spent the whole allowance thinking and
        returned a response containing ONLY a thinking block, no JSON at all.
        Effort "medium" plus a generous budget leaves room for both the
        reasoning and the verdict.
        """
        raw = self.complete(
            step, system, user, max_tokens=max(max_tokens, 4000), effort="medium"
        )
        for candidate in (raw, raw[raw.find("{") : raw.rfind("}") + 1] if "{" in raw else ""):
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        raise SystemExit(
            f"Step '{step}' did not return valid JSON. First 500 chars:\n{raw[:500]}"
        )
