"""
family_tree.py — Graph-based family tree data model with JSON persistence.

This is the core data layer used by both Remi's RAG and the MCP server.
People are nodes, relationships are directed edges. Supports traversal,
search, gap detection, timeline generation, and write-back from interviews.
"""

import json
import re
from collections import deque
from datetime import date
from pathlib import Path
from typing import Any, Optional

BIOGRAPHY_FILE = Path(__file__).parent.parent / "data" / "biography.json"


class FamilyTree:
    """In-memory family tree with JSON file persistence."""

    # Maps a relationship type to its inverse
    INVERSE = {
        "father": "child", "mother": "child",
        "son": "parent", "daughter": "parent",
        "child": "parent", "parent": "child",
        "brother": "sibling", "sister": "sibling", "sibling": "sibling",
        "spouse": "spouse", "partner": "partner",
        "grandfather": "grandchild", "grandmother": "grandchild",
        "grandchild": "grandparent", "grandparent": "grandchild",
        "uncle": "nephew/niece", "aunt": "nephew/niece",
        "nephew": "uncle/aunt", "niece": "uncle/aunt",
        "cousin": "cousin", "friend": "friend",
        "stepfather": "stepchild", "stepmother": "stepchild",
        "stepchild": "stepparent",
        "half-brother": "half-sibling", "half-sister": "half-sibling",
        "other": "other",
    }

    def __init__(self, data_file: Path = None):
        self.data_file = data_file or BIOGRAPHY_FILE
        self.data = self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        if self.data_file.exists():
            with open(self.data_file) as f:
                data = json.load(f)
            version = data.get("_meta", {}).get("version", "1.0")
            if version.startswith("1"):
                raise ValueError(
                    "biography.json is v1 format. Run: python scripts/migrate_v1_to_v2.py"
                )
            return data
        return self._empty()

    def _empty(self) -> dict:
        return {
            "_meta": {
                "version": "2.0",
                "subject_id": None,
                "last_updated": str(date.today()),
            },
            "people": {},
            "relationships": [],
        }

    def save(self) -> None:
        self.data["_meta"]["last_updated"] = str(date.today())
        with open(self.data_file, "w") as f:
            json.dump(self.data, f, indent=2)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if slug not in self.data["people"]:
            return slug
        i = 2
        while f"{slug}-{i}" in self.data["people"]:
            i += 1
        return f"{slug}-{i}"

    # ------------------------------------------------------------------
    # Read — People
    # ------------------------------------------------------------------

    def get_subject(self) -> Optional[dict]:
        sid = self.data["_meta"].get("subject_id")
        return self.data["people"].get(sid) if sid else None

    def get_person(self, person_id: str) -> Optional[dict]:
        return self.data["people"].get(person_id)

    def search_people(self, query: str) -> list[dict]:
        q = query.lower()
        return [
            p for p in self.data["people"].values()
            if q in (p.get("name") or "").lower()
            or q in (p.get("preferred_name") or "").lower()
        ]

    def list_people(self) -> list[dict]:
        return [
            {"id": p["id"], "name": p.get("name"), "preferred_name": p.get("preferred_name")}
            for p in self.data["people"].values()
        ]

    # ------------------------------------------------------------------
    # Read — Relationships
    # ------------------------------------------------------------------

    def get_relatives(self, person_id: str, rel_type: str = None) -> list[dict]:
        """
        Get relatives of a person. Checks both directions — direct edges
        and inverse edges — so you only need to store a relationship once.
        """
        results = []
        for rel in self.data["relationships"]:
            if rel["person_id"] == person_id:
                if rel_type and rel["type"] != rel_type:
                    continue
                person = self.data["people"].get(rel["relative_id"])
                if person:
                    results.append({
                        "relationship": rel["type"],
                        "person": person,
                        "notes": rel.get("notes"),
                    })
            elif rel["relative_id"] == person_id:
                inverse = self.INVERSE.get(rel["type"], "related")
                if rel_type and inverse != rel_type:
                    continue
                person = self.data["people"].get(rel["person_id"])
                if person:
                    results.append({
                        "relationship": inverse,
                        "person": person,
                        "notes": rel.get("notes"),
                    })
        return results

    def find_relationship(self, person_a: str, person_b: str, max_depth: int = 8) -> Optional[list]:
        """BFS to find the shortest relationship path between two people."""
        if person_a not in self.data["people"] or person_b not in self.data["people"]:
            return None

        # Build adjacency list
        adj: dict[str, list[tuple[str, str]]] = {}
        for rel in self.data["relationships"]:
            pid, rid, rtype = rel["person_id"], rel["relative_id"], rel["type"]
            adj.setdefault(pid, []).append((rid, rtype))
            adj.setdefault(rid, []).append((pid, self.INVERSE.get(rtype, "related")))

        queue = deque([(person_a, [(person_a, "start")])])
        visited = {person_a}

        while queue:
            current, path = queue.popleft()
            if current == person_b:
                return path
            if len(path) > max_depth:
                continue
            for neighbor, rel_type in adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [(neighbor, rel_type)]))
        return None

    def get_family_summary(self, person_id: str) -> str:
        """Human-readable summary of someone's family connections."""
        person = self.data["people"].get(person_id)
        if not person:
            return f"Person '{person_id}' not found."

        name = person.get("preferred_name") or person.get("name") or person_id
        relatives = self.get_relatives(person_id)

        if not relatives:
            return f"{name} has no recorded family relationships yet."

        by_type: dict[str, list[str]] = {}
        for rel in relatives:
            rtype = rel["relationship"]
            rname = rel["person"].get("preferred_name") or rel["person"].get("name") or "?"
            by_type.setdefault(rtype, []).append(rname)

        lines = [f"Family connections for {name}:"]
        for rtype, names in sorted(by_type.items()):
            lines.append(f"  {rtype}: {', '.join(names)}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Read — Timeline
    # ------------------------------------------------------------------

    def get_timeline(self, person_id: str) -> list[dict]:
        person = self.data["people"].get(person_id)
        if not person:
            return []

        events = []
        if person.get("date_of_birth"):
            events.append({"year": person["date_of_birth"], "event": "Born",
                           "place": person.get("place_of_birth")})

        for edu in person.get("education", []):
            if edu.get("years") and edu.get("institution"):
                events.append({"year": edu["years"],
                               "event": f"Education: {edu['institution']}",
                               "detail": edu.get("qualification")})

        for job in person.get("career", []):
            if job.get("years") and (job.get("employer") or job.get("role")):
                label = " at ".join(filter(None, [job.get("role"), job.get("employer")]))
                events.append({"year": job["years"], "event": f"Career: {label}"})

        for ms in person.get("milestones", []):
            if ms.get("year") and ms.get("event"):
                events.append({"year": ms["year"], "event": ms["event"],
                               "notes": ms.get("notes")})

        for place in person.get("places_lived", []):
            if place.get("years") and place.get("location"):
                events.append({"year": place["years"],
                               "event": f"Lived in {place['location']}",
                               "type": place.get("type")})

        if person.get("date_of_death"):
            events.append({"year": person["date_of_death"], "event": "Died",
                           "place": person.get("place_of_death")})

        events.sort(key=lambda e: str(e.get("year", "9999")))
        return events

    # ------------------------------------------------------------------
    # Read — Gap detection
    # ------------------------------------------------------------------

    def get_unexplored(self, person_id: str = None) -> dict:
        """Find null/empty fields — gaps worth exploring in interviews."""
        people = (
            {person_id: self.data["people"][person_id]}
            if person_id and person_id in self.data["people"]
            else self.data["people"]
        )

        gaps: dict[str, dict] = {}
        core_fields = [
            "name", "date_of_birth", "place_of_birth",
            "gender", "nationality", "occupation",
        ]

        for pid, person in people.items():
            missing = [f for f in core_fields if not person.get(f)]

            has_rels = any(
                r for r in self.data["relationships"]
                if r["person_id"] == pid or r["relative_id"] == pid
            )
            if not has_rels:
                missing.append("no_relationships_recorded")

            for list_field in ("education", "career", "milestones", "memories"):
                if not person.get(list_field):
                    missing.append(list_field)

            if missing:
                gaps[pid] = {"name": person.get("name", "Unknown"), "missing": missing}

        return gaps

    # ------------------------------------------------------------------
    # Write — People
    # ------------------------------------------------------------------

    def _new_person_dict(self, pid: str, name: str, **kw: Any) -> dict:
        return {
            "id": pid,
            "name": name,
            "preferred_name": kw.get("preferred_name"),
            "date_of_birth": kw.get("date_of_birth"),
            "place_of_birth": kw.get("place_of_birth"),
            "date_of_death": kw.get("date_of_death"),
            "place_of_death": kw.get("place_of_death"),
            "is_living": kw.get("is_living", True),
            "gender": kw.get("gender"),
            "nationality": kw.get("nationality"),
            "current_location": kw.get("current_location"),
            "occupation": kw.get("occupation"),
            "education": kw.get("education", []),
            "career": kw.get("career", []),
            "places_lived": kw.get("places_lived", []),
            "milestones": kw.get("milestones", []),
            "interests": kw.get("interests", []),
            "notes": kw.get("notes"),
            "memories": kw.get("memories", []),
        }

    def add_person(self, name: str, **kwargs: Any) -> dict:
        pid = self._make_id(name)
        person = self._new_person_dict(pid, name, **kwargs)
        self.data["people"][pid] = person
        self.save()
        return person

    def update_person(self, person_id: str, field: str, value: Any) -> Optional[dict]:
        person = self.data["people"].get(person_id)
        if not person or field not in person:
            return None
        person[field] = value
        self.save()
        return person

    # ------------------------------------------------------------------
    # Write — Relationships
    # ------------------------------------------------------------------

    def add_relationship(self, person_id: str, relative_id: str,
                         rel_type: str, notes: str = None) -> dict:
        if person_id not in self.data["people"]:
            raise ValueError(f"Person '{person_id}' not found")
        if relative_id not in self.data["people"]:
            raise ValueError(f"Person '{relative_id}' not found")

        # Duplicate check
        for rel in self.data["relationships"]:
            if (rel["person_id"] == person_id
                    and rel["relative_id"] == relative_id
                    and rel["type"] == rel_type):
                return rel

        rel = {
            "person_id": person_id,
            "relative_id": relative_id,
            "type": rel_type,
            "notes": notes,
        }
        self.data["relationships"].append(rel)
        self.save()
        return rel

    # ------------------------------------------------------------------
    # Write — Memories
    # ------------------------------------------------------------------

    def add_memory(self, person_id: str, text: str,
                   year: str = None, topic: str = None) -> Optional[dict]:
        person = self.data["people"].get(person_id)
        if not person:
            return None
        entry: dict[str, Any] = {"text": text}
        if year:
            entry["year"] = year
        if topic:
            entry["topic"] = topic
        person.setdefault("memories", []).append(entry)
        self.save()
        return entry

    # ------------------------------------------------------------------
    # Format for prompt injection (enhanced RAG)
    # ------------------------------------------------------------------

    def format_context(self, person_id: str = None, topics: list[str] = None) -> str:
        """
        Build a focused context string for prompt injection.
        If person_id is given, focuses on that person.
        If topics are given, filters to relevant sections.
        """
        target_id = person_id or self.data["_meta"].get("subject_id")
        if not target_id:
            return ""

        person = self.data["people"].get(target_id)
        if not person:
            return ""

        name = person.get("preferred_name") or person.get("name") or target_id
        lines = [f"KNOWN FACTS ABOUT {name.upper()}:"]
        lines.append("(Verified ground truth. Use them — do not contradict them.)\n")

        # Core info
        core = []
        for field in ("name", "preferred_name", "date_of_birth", "place_of_birth",
                       "nationality", "current_location", "occupation", "gender"):
            val = person.get(field)
            if val:
                core.append(f"  {field.replace('_', ' ').title()}: {val}")
        if core:
            lines.append("[PERSONAL]")
            lines.extend(core)
            lines.append("")

        # Family
        if not topics or "family" in topics:
            relatives = self.get_relatives(target_id)
            if relatives:
                lines.append("[FAMILY]")
                for rel in relatives:
                    rname = rel["person"].get("preferred_name") or rel["person"].get("name")
                    detail = f"  {rel['relationship']}: {rname}"
                    if rel.get("notes"):
                        detail += f" — {rel['notes']}"
                    lines.append(detail)
                lines.append("")

        # Education
        if not topics or "education" in topics:
            edu_items = [e for e in person.get("education", []) if any(e.values())]
            if edu_items:
                lines.append("[EDUCATION]")
                for e in edu_items:
                    parts = filter(None, [e.get("institution"), e.get("qualification"),
                                          e.get("field"), e.get("years")])
                    lines.append("  " + " | ".join(parts))
                lines.append("")

        # Career
        if not topics or "career" in topics:
            career_items = [c for c in person.get("career", []) if any(c.values())]
            if career_items:
                lines.append("[CAREER]")
                for c in career_items:
                    parts = filter(None, [c.get("role"), c.get("employer"), c.get("years")])
                    lines.append("  " + " | ".join(parts))
                lines.append("")

        # Milestones
        if not topics or "milestones" in topics:
            ms = [m for m in person.get("milestones", []) if m.get("event")]
            if ms:
                lines.append("[MILESTONES]")
                for m in ms:
                    line = f"  {m.get('year', '?')}: {m['event']}"
                    if m.get("notes"):
                        line += f" — {m['notes']}"
                    lines.append(line)
                lines.append("")

        # Places
        if not topics or "places" in topics:
            places = [p for p in person.get("places_lived", []) if p.get("location")]
            if places:
                lines.append("[PLACES]")
                for p in places:
                    parts = filter(None, [p.get("location"), p.get("type"), p.get("years")])
                    lines.append("  " + " | ".join(parts))
                lines.append("")

        # Interests
        if not topics or "interests" in topics:
            if person.get("interests"):
                lines.append("[INTERESTS]")
                lines.append("  " + ", ".join(person["interests"]))
                lines.append("")

        # Memories
        if not topics or "memories" in topics:
            memories = person.get("memories", [])
            if memories:
                lines.append("[MEMORIES & ANECDOTES]")
                for m in memories:
                    prefix = f"  ({m['year']}) " if m.get("year") else "  "
                    lines.append(f"{prefix}{m['text']}")
                lines.append("")

        # Gaps — what's still unknown
        gaps = self.get_unexplored(target_id)
        if gaps.get(target_id):
            missing = gaps[target_id]["missing"]
            lines.append("[GAPS — STILL UNKNOWN]")
            lines.append(f"  {', '.join(missing)}")
            lines.append("  (Consider exploring these during the interview.)")
            lines.append("")

        # Notes
        if person.get("notes"):
            lines.append("[NOTES]")
            lines.append(f"  {person['notes']}")
            lines.append("")

        return "\n".join(lines)
