"""
biography.py — Backward-compatible biography module.

In v2, the FamilyTree class handles all data access.
This module provides convenience wrappers and the topic detection
that the RAG system uses.
"""

from pathlib import Path
from remi.family_tree import FamilyTree, BIOGRAPHY_FILE


def load_tree(data_file: Path = None) -> FamilyTree:
    """Load the family tree. This is the primary entry point for v2."""
    return FamilyTree(data_file or BIOGRAPHY_FILE)


def get_subject_name(tree: FamilyTree = None) -> str:
    """Get the subject's display name."""
    if tree is None:
        tree = load_tree()
    subject = tree.get_subject()
    if not subject:
        return "the subject"
    return subject.get("preferred_name") or subject.get("name") or "the subject"
