"""Interactive resolution of ambiguous link decisions.

Presents each unresolved ambiguity from a :class:`~lore_extractor.inference.DecisionLog`
to the user and stores their choice back in the log, so the next inference pass
resolves the conflict automatically.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Union

from lore_extractor.inference import DecisionLog


class InteractiveResolver:
    """Walk unresolved ambiguities and let the user pick a candidate."""

    def __init__(
        self,
        decision_log: DecisionLog,
        stdin=None,
        stdout=None,
    ) -> None:
        self.decision_log = decision_log
        self._stdin = stdin if stdin is not None else sys.stdin
        self._stdout = stdout if stdout is not None else sys.stdout
        self.resolved = 0

    def run(self) -> int:
        """Prompt for every unresolved entry; returns the number resolved."""
        entries = self.decision_log.unresolved_entries()
        if not entries:
            self._print("No unresolved decisions to review.")
            return 0
        for entry in entries:
            choice = self._prompt(entry)
            if choice is None:
                break  # quit
            if choice == "skip":
                continue
            if choice == "auto":
                chosen = max(
                    entry["candidates"],
                    key=lambda c: c.get("confidence", 0.0),
                )
            else:
                chosen = entry["candidates"][choice]
            self.decision_log.update_resolution(entry, chosen["name"])
            self.resolved += 1
            self._print(f"  -> {chosen['name']} ({chosen['type']})\n")
        return self.resolved

    def _print(self, text: str) -> None:
        self._stdout.write(text + "\n")
        self._stdout.flush()

    def _prompt(self, entry: Dict[str, Any]) -> Optional[Union[str, int]]:
        candidates = entry["candidates"]
        self._print(f"Ambiguity: \"{entry['link_text']}\"")
        self._print(
            f"Sources: {', '.join(entry['sources'])} "
            f"({entry['occurrence_count']} occurrences)"
        )
        self._print("Candidates:")
        for i, candidate in enumerate(candidates, 1):
            conf = candidate.get("confidence", 0.0)
            self._print(f"  {i}. {candidate['name']} ({candidate['type']}, confidence: {conf})")
        while True:
            self._stdout.write(
                f"[1-{len(candidates)}] pick / [a] auto / [s] skip / [q] quit: "
            )
            self._stdout.flush()
            try:
                raw = self._stdin.readline()
            except (EOFError, KeyboardInterrupt):
                return None
            if raw == "":
                return None
            raw = raw.strip().lower()
            if raw in ("q", "quit"):
                return None
            if raw in ("s", "skip"):
                return "skip"
            if raw in ("a", "auto"):
                return "auto"
            try:
                index = int(raw)
            except ValueError:
                self._print("Invalid choice.")
                continue
            if 1 <= index <= len(candidates):
                return index - 1
            self._print("Invalid choice.")
