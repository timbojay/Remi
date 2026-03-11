#!/usr/bin/env python3
"""
Remi Family Tree — MCP Server

Exposes biographical and family tree data via the Model Context Protocol.
Works with any MCP client: Claude Desktop, Cursor, VS Code Copilot, etc.

Usage:
  # stdio transport (default — for MCP clients)
  python mcp_server/server.py

  # SSE transport (for HTTP access)
  python mcp_server/server.py --transport sse --port 8000

  # Custom data file
  python mcp_server/server.py --data /path/to/biography.json
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path so we can import remi.*
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP
from remi.family_tree import FamilyTree

# Default data file
DEFAULT_DATA = Path(__file__).parent.parent / "data" / "biography.json"

mcp = FastMCP(
    "remi-family-tree",
    instructions="Family tree and biographical data server for Remi — "
                 "a personal biography assistant.",
)

# Global tree instance — initialized in main()
tree: FamilyTree = None


# ======================================================================
# Tools — Read
# ======================================================================

@mcp.tool()
def get_subject() -> str:
    """Get the main interview subject's full biographical data."""
    subject = tree.get_subject()
    if not subject:
        return json.dumps({"error": "No subject configured. Set subject_id in biography.json _meta."})
    return json.dumps(subject, indent=2, default=str)


@mcp.tool()
def get_person(person_id: str) -> str:
    """Get full biographical data for a person by their ID.

    Args:
        person_id: The person's unique ID (slug format, e.g. 'tim-jordan')
    """
    person = tree.get_person(person_id)
    if not person:
        return json.dumps({"error": f"Person '{person_id}' not found."})
    return json.dumps(person, indent=2, default=str)


@mcp.tool()
def search_people(query: str) -> str:
    """Search for people by name (partial match, case-insensitive).

    Args:
        query: Name or partial name to search for
    """
    results = tree.search_people(query)
    if not results:
        return json.dumps({"results": [], "message": f"No one found matching '{query}'."})
    return json.dumps({
        "results": [
            {"id": p["id"], "name": p["name"], "preferred_name": p.get("preferred_name")}
            for p in results
        ]
    }, indent=2)


@mcp.tool()
def list_people() -> str:
    """List all people in the family tree with their IDs."""
    people = tree.list_people()
    return json.dumps({"count": len(people), "people": people}, indent=2)


@mcp.tool()
def get_relatives(person_id: str, relationship_type: str = None) -> str:
    """Get relatives of a person, optionally filtered by type.

    Automatically resolves inverse relationships (if A is B's father, B is A's child).

    Args:
        person_id: ID of the person
        relationship_type: Optional filter — father, mother, child, sibling, spouse, etc.
    """
    relatives = tree.get_relatives(person_id, relationship_type)
    if not relatives:
        msg = f"No {'matching ' if relationship_type else ''}relatives found for '{person_id}'."
        return json.dumps({"relatives": [], "message": msg})

    result = []
    for rel in relatives:
        result.append({
            "relationship": rel["relationship"],
            "id": rel["person"]["id"],
            "name": rel["person"]["name"],
            "preferred_name": rel["person"].get("preferred_name"),
            "notes": rel.get("notes"),
        })
    return json.dumps({"relatives": result}, indent=2)


@mcp.tool()
def find_relationship(person_a_id: str, person_b_id: str) -> str:
    """Find the relationship path between two people in the family tree.

    Uses breadth-first search to find the shortest connection.

    Args:
        person_a_id: ID of the first person
        person_b_id: ID of the second person
    """
    path = tree.find_relationship(person_a_id, person_b_id)
    if not path:
        return json.dumps({
            "error": f"No relationship path found between '{person_a_id}' and '{person_b_id}'."
        })

    formatted = []
    for pid, rel in path:
        person = tree.get_person(pid)
        name = (person.get("preferred_name") or person.get("name")) if person else pid
        formatted.append({"person_id": pid, "name": name, "via": rel})
    return json.dumps({"path": formatted}, indent=2)


@mcp.tool()
def get_timeline(person_id: str) -> str:
    """Get a chronological timeline of life events for a person.

    Includes: birth, education, career, milestones, places lived, death.

    Args:
        person_id: ID of the person
    """
    events = tree.get_timeline(person_id)
    if not events:
        return json.dumps({"events": [], "message": f"No timeline events found for '{person_id}'."})
    return json.dumps({"events": events}, indent=2, default=str)


@mcp.tool()
def get_unexplored(person_id: str = None) -> str:
    """Find gaps in biographical data — null or empty fields worth exploring.

    Great for planning interview questions.

    Args:
        person_id: Optional — check one person. Omit to check everyone.
    """
    gaps = tree.get_unexplored(person_id)
    if not gaps:
        return json.dumps({"message": "No gaps found — all core fields are populated!"})
    return json.dumps({"gaps": gaps}, indent=2)


@mcp.tool()
def get_family_summary(person_id: str) -> str:
    """Get a human-readable summary of someone's family connections.

    Args:
        person_id: ID of the person
    """
    return tree.get_family_summary(person_id)


# ======================================================================
# Tools — Write
# ======================================================================

@mcp.tool()
def add_person(
    name: str,
    preferred_name: str = None,
    date_of_birth: str = None,
    place_of_birth: str = None,
    gender: str = None,
    is_living: bool = True,
    occupation: str = None,
    notes: str = None,
) -> str:
    """Add a new person to the family tree.

    Args:
        name: Full name
        preferred_name: What they go by (nickname, shortened name)
        date_of_birth: Date of birth (any format)
        place_of_birth: Where they were born
        gender: male, female, or other
        is_living: Whether they're still alive (default: true)
        occupation: What they do/did for work
        notes: Any additional notes
    """
    person = tree.add_person(
        name=name,
        preferred_name=preferred_name,
        date_of_birth=date_of_birth,
        place_of_birth=place_of_birth,
        gender=gender,
        is_living=is_living,
        occupation=occupation,
        notes=notes,
    )
    return json.dumps({"created": person}, indent=2, default=str)


@mcp.tool()
def update_person(person_id: str, field: str, value: str) -> str:
    """Update a single field on a person's record.

    Args:
        person_id: ID of the person to update
        field: Field name (e.g. date_of_birth, occupation, notes, nationality)
        value: New value (for lists/objects, pass JSON string)
    """
    # Try to parse JSON for complex values
    parsed = value
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        pass

    result = tree.update_person(person_id, field, parsed)
    if not result:
        return json.dumps({
            "error": f"Could not update '{field}' on '{person_id}'. "
                     f"Person not found or field doesn't exist."
        })
    return json.dumps({"updated": {"person_id": person_id, "field": field, "value": parsed}},
                       default=str)


@mcp.tool()
def add_relationship(
    person_id: str,
    relative_id: str,
    relationship_type: str,
    notes: str = None,
) -> str:
    """Add a relationship between two people.

    Reads as: "[relative_id] is [person_id]'s [relationship_type]"
    Example: add_relationship("tim", "john", "father") → John is Tim's father.

    Args:
        person_id: ID of the person
        relative_id: ID of their relative
        relationship_type: father, mother, son, daughter, brother, sister, spouse,
                          partner, grandfather, grandmother, uncle, aunt, cousin,
                          stepfather, stepmother, half-brother, half-sister, friend, other
        notes: Optional notes about the relationship
    """
    try:
        rel = tree.add_relationship(person_id, relative_id, relationship_type, notes)
        return json.dumps({"created": rel})
    except ValueError as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def add_memory(
    person_id: str,
    memory: str,
    year: str = None,
    topic: str = None,
) -> str:
    """Record a memory or anecdote about a person (discovered during interviews).

    Args:
        person_id: ID of the person this memory is about
        memory: The memory or anecdote text
        year: Approximate year (if known)
        topic: Topic category (family, childhood, career, etc.)
    """
    entry = tree.add_memory(person_id, memory, year, topic)
    if not entry:
        return json.dumps({"error": f"Person '{person_id}' not found."})
    return json.dumps({"added": entry, "person_id": person_id})


# ======================================================================
# Resources
# ======================================================================

@mcp.resource("family://tree/summary")
def tree_summary() -> str:
    """Overview of the entire family tree — people count, relationships, subject."""
    people = tree.list_people()
    subject = tree.get_subject()
    rels = len(tree.data.get("relationships", []))
    return json.dumps({
        "total_people": len(people),
        "total_relationships": rels,
        "subject": subject.get("name") if subject else None,
        "people": people,
    }, indent=2)


# ======================================================================
# Entry point
# ======================================================================

def main():
    parser = argparse.ArgumentParser(description="Remi Family Tree MCP Server")
    parser.add_argument("--data", default=str(DEFAULT_DATA),
                        help="Path to biography.json (v2 format)")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio",
                        help="Transport method (default: stdio)")
    parser.add_argument("--host", default="localhost",
                        help="Host for SSE transport (default: localhost)")
    parser.add_argument("--port", type=int, default=8000,
                        help="Port for SSE transport (default: 8000)")
    args = parser.parse_args()

    global tree
    tree = FamilyTree(Path(args.data))

    print(f"Remi Family Tree MCP Server", file=sys.stderr)
    print(f"  Data: {args.data}", file=sys.stderr)
    print(f"  Transport: {args.transport}", file=sys.stderr)

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
