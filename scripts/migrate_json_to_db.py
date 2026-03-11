#!/usr/bin/env python3
"""
Migrate biography.json → Remi SQLite database.

Reads the v2 biography.json and seeds the knowledge graph with:
- People as entities (entity_type='person')
- Core facts from their biographical fields
- Relationships between people

Usage:
    python scripts/migrate_json_to_db.py
    python scripts/migrate_json_to_db.py --json data/biography.json --db backend/data/remi.db
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add project root and backend to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))


async def migrate(json_path: Path, db_path: Path):
    import os
    os.environ["DB_PATH"] = str(db_path)

    from app.config import settings
    settings.DB_PATH = str(db_path)

    from app.db.database import init_db
    from app.db import knowledge_graph as kg

    print(f"Initialising database at {db_path}...")
    await init_db()

    print(f"Loading {json_path}...")
    with open(json_path) as f:
        data = json.load(f)

    people_data = data.get("people", {})
    relationships_data = data.get("relationships", [])

    # Track old JSON id → new SQLite entity UUID
    id_map: dict[str, str] = {}

    # ── Create entities ──────────────────────────────────────────────
    print(f"Migrating {len(people_data)} people...")
    for slug, person in people_data.items():
        name = person.get("name") or slug
        is_living = person.get("is_living", True)
        family_role = None

        # Build description from available fields
        desc_parts = []
        if person.get("date_of_birth"):
            desc_parts.append(f"Born {person['date_of_birth']}")
        if person.get("place_of_birth"):
            desc_parts.append(f"in {person['place_of_birth']}")
        if person.get("date_of_death"):
            desc_parts.append(f"Died {person['date_of_death']}")
        if person.get("occupation"):
            desc_parts.append(person["occupation"])
        description = ". ".join(desc_parts)

        result = await kg.add_entity(
            name=name,
            entity_type="person",
            relationship=None,
            family_role=family_role,
            description=description,
            confidence=0.9,
        )
        entity_id = result["id"]
        id_map[slug] = entity_id
        print(f"  ✓ {name} → {entity_id[:8]}")

        # ── Add facts for this person ─────────────────────────────
        subject_id = entity_id

        if person.get("nationality"):
            await kg.add_fact(
                value=f"Nationality: {person['nationality']}",
                category="identity",
                subject_entity_id=subject_id,
                confidence=0.95,
                significance=4,
                is_anchor=(slug == data.get("_meta", {}).get("subject_id", "")),
            )

        if person.get("current_location"):
            await kg.add_fact(
                value=f"Currently lives in {person['current_location']}",
                category="residence",
                subject_entity_id=subject_id,
                confidence=0.9,
                significance=3,
            )

        if person.get("date_of_birth") and person.get("place_of_birth"):
            await kg.add_fact(
                value=f"Born {person['date_of_birth']} in {person['place_of_birth']}",
                category="identity",
                subject_entity_id=subject_id,
                confidence=0.95,
                significance=5,
                is_anchor=True,
            )
        elif person.get("date_of_birth"):
            await kg.add_fact(
                value=f"Born {person['date_of_birth']}",
                category="identity",
                subject_entity_id=subject_id,
                confidence=0.95,
                significance=5,
                is_anchor=True,
            )

        if person.get("date_of_death"):
            await kg.add_fact(
                value=f"Died {person['date_of_death']}",
                category="milestone",
                subject_entity_id=subject_id,
                confidence=0.95,
                significance=5,
            )

        if person.get("occupation"):
            await kg.add_fact(
                value=f"Occupation: {person['occupation']}",
                category="career",
                subject_entity_id=subject_id,
                confidence=0.8,
                significance=3,
            )

        for edu in person.get("education", []) or []:
            parts = []
            if edu.get("qualification"):
                parts.append(edu["qualification"])
            if edu.get("institution"):
                parts.append(f"at {edu['institution']}")
            if edu.get("years"):
                parts.append(f"({edu['years']})")
            if parts:
                await kg.add_fact(
                    value=" ".join(parts),
                    category="education",
                    subject_entity_id=subject_id,
                    confidence=0.9,
                    significance=4,
                )

        for career in person.get("career", []) or []:
            parts = []
            if career.get("role"):
                parts.append(career["role"])
            if career.get("employer"):
                parts.append(f"at {career['employer']}")
            if career.get("years"):
                parts.append(f"({career['years']})")
            if parts:
                await kg.add_fact(
                    value=" ".join(parts),
                    category="career",
                    subject_entity_id=subject_id,
                    confidence=0.8,
                    significance=3,
                )

        for memory in person.get("memories", []) or []:
            if memory:
                await kg.add_fact(
                    value=str(memory),
                    category="milestone",
                    subject_entity_id=subject_id,
                    confidence=0.7,
                    significance=3,
                )

    # ── Create relationships ─────────────────────────────────────────
    print(f"\nMigrating {len(relationships_data)} relationships...")
    for rel in relationships_data:
        from_slug = rel.get("person_id")
        to_slug = rel.get("relative_id")
        rel_type = rel.get("type", "related")

        from_id = id_map.get(from_slug)
        to_id = id_map.get(to_slug)

        if not from_id or not to_id:
            print(f"  ⚠ Skipping {from_slug} → {to_slug} (entity not found)")
            continue

        result = await kg.add_relationship(
            from_entity_id=from_id,
            to_entity_id=to_id,
            relationship_type=rel_type,
            is_bidirectional=False,
            confidence=0.9,
        )
        from_name = people_data.get(from_slug, {}).get("name", from_slug)
        to_name = people_data.get(to_slug, {}).get("name", to_slug)
        print(f"  ✓ {from_name} → {rel_type} → {to_name}")

    print(f"\n✅ Migration complete!")
    print(f"   People:        {len(id_map)}")
    print(f"   Relationships: {len(relationships_data)}")
    print(f"   Database:      {db_path}")


def main():
    parser = argparse.ArgumentParser(description="Migrate biography.json → Remi SQLite DB")
    parser.add_argument(
        "--json",
        default=str(PROJECT_ROOT / "data" / "biography.json"),
        help="Path to biography.json",
    )
    parser.add_argument(
        "--db",
        default=str(PROJECT_ROOT / "backend" / "data" / "remi.db"),
        help="Path to SQLite database",
    )
    args = parser.parse_args()

    asyncio.run(migrate(Path(args.json), Path(args.db)))


if __name__ == "__main__":
    main()
