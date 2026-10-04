"""Evidence-only replies to conversational Workspace update requests."""

import re

from .schemas import SatchyContext

_UPDATE_REQUEST = re.compile(
    r"(?:(?:no worries|thanks|thank you|okay|ok|all right)[.! ,]+)?"
    r"(?:any (?:other|more|new) updates|anything (?:else|new)|"
    r"what(?:'s| is) new|any updates)[?!. ]*",
    re.I,
)


def verified_update_answer(context: SatchyContext, message: str) -> tuple[str, str] | None:
    """Describe available evidence without claiming freshness or consulting a model.

    Context has no per-user seen-evidence cursor. Existing records therefore cannot
    be called new, and conversational history is never evidence for this reply.
    """
    if not _UPDATE_REQUEST.fullmatch(" ".join(message.split()).strip()):
        return None

    summaries = [
        " ".join(item["summary"].split())[:600]
        for item in context.evidence
        if isinstance(item.get("summary"), str) and item["summary"].strip()
    ]
    if not summaries:
        answer = (
            "No verified updates are available in the current Workspace context. "
            "You can review Activity or Map for source-linked information."
        )
    else:
        answer = (
            "The current Workspace context includes these source summaries; "
            "I cannot determine which are new since your last review:\n"
            + "\n".join(f"- {summary}" for summary in summaries[-3:])
            + "\nReview Activity or Map for the source records and timestamps."
        )
    return answer, "satchy-verified-updates"
