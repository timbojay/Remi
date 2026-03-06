"""
rag.py — RAG retrieval: given a conversation turn, fetch relevant biography facts.
"""

from remi.biography import load, detect_topics, get_sections, format_for_prompt


def retrieve(query: str) -> str:
    """
    Given an interview question or conversational turn, retrieve and format
    the relevant biographical facts to inject into the prompt.

    Returns a formatted string ready for prompt injection (empty string if nothing relevant).
    """
    try:
        bio = load()
    except FileNotFoundError:
        return ""

    subject_name = bio.get("subject", {}).get("preferred_name") or \
                   bio.get("subject", {}).get("name") or "the subject"

    topics = detect_topics(query)
    sections = get_sections(topics, bio)

    # Always include subject basics
    if "subject" not in sections and bio.get("subject"):
        sections["subject"] = bio["subject"]

    return format_for_prompt(sections, subject_name)


def retrieve_all() -> str:
    """Retrieve and format the full biography (for session start injection)."""
    try:
        bio = load()
    except FileNotFoundError:
        return ""

    subject_name = bio.get("subject", {}).get("preferred_name") or \
                   bio.get("subject", {}).get("name") or "the subject"

    all_sections = {k: v for k, v in bio.items() if k not in ("_meta",) and v}
    return format_for_prompt(all_sections, subject_name)
