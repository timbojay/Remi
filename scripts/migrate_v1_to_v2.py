#!/usr/bin/env python3
"""
Migrate biography.json from v1 (flat) to v2 (graph) format.

Usage:
  python scripts/migrate_v1_to_v2.py
  python scripts/migrate_v1_to_v2.py --input data/biography_v1_backup.json --output data/biography.json
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DEFAULT_INPUT = BASE_DIR / "data" / "biography_v1_backup.json"
DEFAULT_OUTPUT = BASE_DIR / "data" / "biography.json"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def migrate(v1: dict) -> dict:
    """Convert a v1 biography dict to v2 format."""
    v2 = {
        "_meta": {
            "version": "2.0",
            "subject_id": None,
            "last_updated": str(date.today()),
            "description": "Migrated from v1 biography format.",
        },
        "people": {},
        "relationships": [],
    }

    used_ids = set()

    def make_id(name: str) -> str:
        slug = slugify(name)
        if slug in used_ids:
            i = 2
            while f"{slug}-{i}" in used_ids:
                i += 1
            slug = f"{slug}-{i}"
        used_ids.add(slug)
        return slug

    def make_person(name: str, **kw) -> dict:
        pid = make_id(name)
        person = {
            "id": pid,
            "name": name,
            "preferred_name": kw.get("preferred_name"),
            "date_of_birth": kw.get("date_of_birth"),
            "place_of_birth": kw.get("place_of_birth"),
            "date_of_death": None,
            "place_of_death": None,
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
            "memories": [],
        }
        v2["people"][pid] = person
        return person

    # --- Migrate subject ---
    subj = v1.get("subject", {})
    subj_name = subj.get("name")
    if subj_name:
        s = make_person(
            subj_name,
            preferred_name=subj.get("preferred_name"),
            date_of_birth=subj.get("date_of_birth"),
            place_of_birth=subj.get("place_of_birth"),
            nationality=subj.get("nationality"),
            current_location=subj.get("current_location"),
            education=v1.get("education", []),
            career=v1.get("career", []),
            milestones=v1.get("milestones", []),
            interests=v1.get("interests", []),
            places_lived=v1.get("places", []),
            notes=v1.get("additional_notes"),
        )
        v2["_meta"]["subject_id"] = s["id"]
        subject_id = s["id"]
    else:
        print("WARNING: No subject name found in v1 data. Creating empty v2.")
        return v2

    # --- Migrate family ---
    family = v1.get("family", {})

    for parent in family.get("parents", []):
        pname = parent.get("name")
        if not pname:
            continue
        p = make_person(
            pname,
            date_of_birth=parent.get("date_of_birth"),
            place_of_birth=parent.get("place_of_birth"),
            occupation=parent.get("occupation"),
            notes=parent.get("notes"),
        )
        rel_type = parent.get("relation", "parent")
        v2["relationships"].append({
            "person_id": subject_id,
            "relative_id": p["id"],
            "type": rel_type,
            "notes": None,
        })

    for sibling in family.get("siblings", []):
        sname = sibling.get("name") if isinstance(sibling, dict) else sibling
        if not sname:
            continue
        s = make_person(sname) if isinstance(sibling, dict) else make_person(sname)
        v2["relationships"].append({
            "person_id": subject_id,
            "relative_id": s["id"],
            "type": "sibling",
            "notes": None,
        })

    spouse = family.get("spouse_or_partner")
    if spouse:
        sp_name = spouse.get("name") if isinstance(spouse, dict) else spouse
        if sp_name:
            sp = make_person(sp_name) if isinstance(spouse, str) else make_person(
                sp_name, notes=spouse.get("notes") if isinstance(spouse, dict) else None
            )
            v2["relationships"].append({
                "person_id": subject_id,
                "relative_id": sp["id"],
                "type": "spouse",
                "notes": None,
            })

    for child in family.get("children", []):
        cname = child.get("name") if isinstance(child, dict) else child
        if not cname:
            continue
        c = make_person(cname)
        v2["relationships"].append({
            "person_id": subject_id,
            "relative_id": c["id"],
            "type": "child",
            "notes": None,
        })

    return v2


def main():
    parser = argparse.ArgumentParser(description="Migrate biography.json v1 → v2")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    inp = Path(args.input)
    out = Path(args.output)

    if not inp.exists():
        print(f"Input file not found: {inp}")
        sys.exit(1)

    with open(inp) as f:
        v1 = json.load(f)

    # Check if already v2
    if v1.get("_meta", {}).get("version", "").startswith("2"):
        print("Input is already v2 format. Nothing to do.")
        sys.exit(0)

    v2 = migrate(v1)

    with open(out, "w") as f:
        json.dump(v2, f, indent=2)

    people_count = len(v2["people"])
    rel_count = len(v2["relationships"])
    print(f"✓ Migrated to v2: {people_count} people, {rel_count} relationships")
    print(f"  Written to: {out}")


if __name__ == "__main__":
    main()
