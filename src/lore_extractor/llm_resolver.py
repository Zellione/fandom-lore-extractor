"""LLM-based resolution of ambiguous link decisions.

Instead of prompting the user interactively (see :mod:`lore_extractor.resolvers`),
an OpenAI-compatible endpoint (OpenAI, Ollama, vLLM, LM Studio, ...) chooses the
best candidate for each ambiguity. The model is asked to justify its choice; the
reasoning is written to a JSON file in the output directory so decisions stay
auditable.

Two prompt strategies are supported:

* **Batched** (default): all unresolved ambiguities are sent in a single prompt.
* **Single** (``single_prompt=True``): one API call per ambiguity.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from lore_extractor.inference import DecisionLog

SYSTEM_PROMPT = (
    "You are an expert editor of a wiki. You resolve ambiguous internal links "
    "by picking the single most appropriate candidate entity for each ambiguity. "
    "Reply with valid JSON only, no markdown fences and no extra prose."
)


class LLMResolver:
    """Resolve ambiguities from a :class:`~lore_extractor.inference.DecisionLog`
    using an OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        decision_log: DecisionLog,
        client: Any,
        model: str,
        single_prompt: bool = False,
        temperature: float = 0.0,
        max_attempts: int = 3,
        stdout=None,
    ) -> None:
        self.decision_log = decision_log
        self._client = client
        self.model = model
        self.single_prompt = single_prompt
        self.temperature = temperature
        self.max_attempts = max_attempts
        self._stdout = stdout if stdout is not None else sys.stdout
        self.resolved = 0
        self._records: List[Dict[str, Any]] = []

    def run(self) -> int:
        """Resolve every unresolved entry; returns the number resolved."""
        pending = self.decision_log.unresolved_entries()
        if not pending:
            self._print("No unresolved decisions to review.")
            return 0
        self._print(f"Resolving {len(pending)} ambiguities with model '{self.model}' ...")
        for _ in range(self.max_attempts):
            if not pending:
                break
            pending = self._attempt(pending)
        for entry in pending:
            self._record_failure(entry)
            self._print(f"  !! Skipped \"{entry['link_text']}\": failed after "
                        f"{self.max_attempts} attempts")
        return self.resolved

    # -- prompt / parse helpers -------------------------------------------

    def _attempt(self, pending: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """One resolution pass over ``pending``; returns entries still unresolved."""
        remaining: List[Dict[str, Any]] = []
        if self.single_prompt:
            for entry in pending:
                try:
                    content = self._call(entry)
                    payload = _extract_json(content)
                except Exception as exc:  # network / auth / bad payload
                    self._print(f"  !  \"{entry['link_text']}\": {exc}")
                    remaining.append(entry)
                    continue
                if self._apply_result(entry, payload):
                    self._record_success(entry, payload)
                else:
                    remaining.append(entry)
        else:
            try:
                content = self._call(pending)
                payload = _extract_json(content)
            except Exception as exc:
                self._print(f"  !  batch failed: {exc}")
                return pending
            if not isinstance(payload, dict):
                self._print("  !  batch returned an unexpected shape; retrying")
                return pending
            for i, entry in enumerate(pending):
                raw = payload.get(str(i))
                if not isinstance(raw, dict) or not self._apply_result(entry, raw):
                    remaining.append(entry)
                    continue
                self._record_success(entry, raw)
        return remaining

    def _apply_result(self, entry: Dict[str, Any], payload: Dict[str, Any]) -> bool:
        """Apply a ``{chosen, reasoning}`` payload to ``entry``. Returns False if
        the choice is not one of the entry's candidates (triggers a retry)."""
        chosen = payload.get("chosen")
        names = {c["name"] for c in entry["candidates"]}
        if not isinstance(chosen, str) or chosen not in names:
            return False
        self.decision_log.update_resolution(entry, chosen)
        self.resolved += 1
        return True

    def _call(self, data: Any) -> str:
        """Chat completion for either a single entry or a batch list of entries."""
        user_prompt = (
            _build_single_prompt(data)
            if self.single_prompt
            else _build_batch_prompt(data)
        )
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content

    # -- reasoning records ------------------------------------------------

    def _record_success(self, entry: Dict[str, Any], payload: Dict[str, Any]) -> None:
        chosen = payload.get("chosen", "")
        reasoning = payload.get("reasoning", "")
        self._records.append(
            {
                "key": entry["key"],
                "link_text": entry["link_text"],
                "chosen": chosen,
                "reasoning": reasoning,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        snippet = reasoning if reasoning else chosen
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        self._print(f"  -> {chosen} ({snippet})")

    def _record_failure(self, entry: Dict[str, Any]) -> None:
        self._records.append(
            {
                "key": entry["key"],
                "link_text": entry["link_text"],
                "error": f"Could not resolve after {self.max_attempts} attempts",
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    @property
    def reasoning_records(self) -> List[Dict[str, Any]]:
        return list(self._records)

    def write_reasoning(self, path: Path) -> None:
        """Write the reasoning/error log to ``path``."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.reasoning_records, indent=2),
            encoding="utf-8",
        )

    def _print(self, text: str) -> None:
        self._stdout.write(text + "\n")
        self._stdout.flush()


def build_client(base_url: Optional[str] = None, api_key: Optional[str] = None) -> Any:
    """Create an OpenAI client.

    ``None`` values fall back to the ``OPENAI_BASE_URL`` / ``OPENAI_API_KEY``
    environment variables handled by the SDK, so explicit CLI flags always win.
    """
    from openai import OpenAI

    return OpenAI(base_url=base_url, api_key=api_key)


def resolve_model(client: Any, model_name: Optional[str]) -> str:
    """Return the model to use.

    An explicit ``model_name`` (``--llm-model``) is used as-is. Otherwise the
    endpoint's model list is consulted: a single model is auto-selected, while
    multiple models require the user to pick one via ``--llm-model``.
    """
    if model_name:
        return model_name
    try:
        models = client.models.list()
        ids = sorted(m.id for m in models)
    except Exception as exc:
        raise click.UsageError(
            "Could not list models from the endpoint and no --llm-model was "
            f"provided. Pass --llm-model to select a model. (error: {exc})"
        )
    if not ids:
        raise click.UsageError(
            "The endpoint returned no models; pass --llm-model to select one."
        )
    if len(ids) == 1:
        click.echo(f"Auto-selected model: {ids[0]}")
        return ids[0]
    raise click.UsageError(
        "Multiple models available; pick one with --llm-model:\n  "
        + "\n  ".join(ids)
    )


def _extract_json(content: str) -> Dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    return parsed


def _build_batch_prompt(entries: List[Dict[str, Any]]) -> str:
    lines = [
        "Resolve the following ambiguous wiki links. For each ambiguity, choose "
        "the single most appropriate candidate and explain your choice briefly.",
        "",
    ]
    for i, entry in enumerate(entries):
        lines.extend(_format_entry(i, entry))
    lines.extend(
        [
            "",
            "Reply with a JSON object mapping each index to an object with "
            '"chosen" (exactly one candidate name) and "reasoning" (1-2 sentences).',
            'Example: {"0": {"chosen": "Wave", "reasoning": "..."}}',
        ]
    )
    return "\n".join(lines)


def _build_single_prompt(entry: Dict[str, Any]) -> str:
    lines = [
        "Resolve the following ambiguous wiki link. Choose the single most "
        "appropriate candidate and explain your choice briefly.",
        "",
    ]
    lines.extend(_format_entry(0, entry))
    lines.extend(
        [
            "",
            'Reply with a JSON object with "chosen" (exactly one candidate name) '
            'and "reasoning" (1-2 sentences).',
            'Example: {"chosen": "Wave", "reasoning": "..."}',
        ]
    )
    return "\n".join(lines)


def _format_entry(i: int, entry: Dict[str, Any]) -> List[str]:
    candidates = entry["candidates"]
    lines = [
        f"Ambiguity {i}:",
        f'  Link text: "{entry["link_text"]}"',
        f"  Sources: {', '.join(entry['sources'])} "
        f"({entry['occurrence_count']} occurrences)",
        "  Candidates:",
    ]
    for j, candidate in enumerate(candidates, 1):
        conf = candidate.get("confidence", 0.0)
        lines.append(f"    {j}. {candidate['name']} ({candidate['type']}, confidence: {conf})")
    return lines
