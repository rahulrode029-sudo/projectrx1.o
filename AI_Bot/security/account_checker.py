"""Telling a genuine contact from a bulk sender.

Uses the messages a contact has sent, looking for the patterns that
give away an automated account: many links, near-identical messages
and no replies of its own.
"""

from dataclasses import dataclass, field


@dataclass
class AccountRisk:
    """How much a contact looks like a bulk sender."""

    score: int = 0
    reasons: list[str] = field(default_factory=list)

    @property
    def is_suspicious(self) -> bool:
        return self.score >= 3

    @property
    def level(self) -> str:
        if self.score >= 6:
            return "high"

        if self.score >= 3:
            return "medium"

        return "low"


def _normalise(text: str) -> str:
    return " ".join((text or "").lower().split())


def assess(messages: list[str]) -> AccountRisk:
    """Judge a list of message bodies from one contact."""

    risk = AccountRisk()

    bodies = [body for body in messages if (body or "").strip()]

    if len(bodies) < 3:
        return risk

    # Lots of links.
    with_links = sum(1 for body in bodies if "http" in body.lower())

    if with_links >= max(3, len(bodies) // 2):
        risk.score += 2
        risk.reasons.append("sends a lot of links")

    # The same message over and over.
    normalised = [_normalise(body) for body in bodies]

    unique = len(set(normalised))

    if unique <= len(normalised) // 2:
        risk.score += 3
        risk.reasons.append("repeats the same message")

    # Only ever very short messages, which reads as automated.
    if len(bodies) >= 5 and all(len(body) < 15 for body in bodies):
        risk.score += 1
        risk.reasons.append("only sends very short messages")

    return risk
