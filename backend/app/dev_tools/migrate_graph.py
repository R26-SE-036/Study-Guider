"""One-off graph migration: normalise the concept vocabulary, de-duplicate
students, add the constraints that would have prevented both, and seed the
prerequisite graph.

    python -m app.dev_tools.migrate_graph            # dry run, changes nothing
    python -m app.dev_tools.migrate_graph --apply    # writes

Dry run is the default on purpose: this rewrites relationships in a live Aura
database holding real research data, and the shape of that data is the thing
being migrated, so it should be read before it is changed.

Every step is idempotent - running it twice does nothing the second time.

============================ WHAT IS WRONG ============================

1. Concept nodes exist under two vocabularies. ARRAY_LENGTH_INDEX_MISUSE and
   MISSING_BREAK_IN_SWITCH and INCORRECT_CONDITIONAL_OPERATOR are Code Coach
   ERROR TYPES; loop_boundaries and conditional_logic are CONCEPT TAGS. The
   quiz UI posts an error type to /api/progress/update while everything else
   uses concept tags, so a student's history split across both.

   INCORRECT_CONDITIONAL_OPERATOR normalises to conditional_logic, which
   already exists - so this is a real merge with two histories to combine, not
   just a rename.

2. One student exists as two nodes. `user_0bcc693e70f0` has a Student node
   keyed on `student_id` carrying 12 ATTEMPTED relationships, and a second
   Student node keyed on a legacy `id` property carrying the two MASTERED /
   NEEDS_REVIEW relationships. Neither query sees the other's data.

3. MASTERED and NEEDS_REVIEW exist as relationship TYPES, while
   progress_service writes the same fact as a `status` PROPERTY on ATTEMPTED.
   Two conventions for one thing, in one graph.

4. No uniqueness constraints on Student.student_id or Concept.name, which is
   how all of the above became possible.
=======================================================================
"""

import sys

from app.core.concepts import CONCEPT_TAGS, PREREQUISITE_EDGES, find_cycles, normalise_concept
from app.db.neo4j_connection import neo4j_db


class Migration:
    def __init__(self, apply: bool):
        self.apply = apply
        self.planned = []

    def run_query(self, cypher, params=None):
        """Execute, or record what would have been executed."""
        if not self.apply:
            return None
        return neo4j_db.execute_query(cypher, params)

    def read(self, cypher, params=None):
        """Reads always run - a dry run has to look at the data to plan."""
        return neo4j_db.execute_query(cypher, params) or []

    def note(self, message):
        self.planned.append(message)
        print(f"  {'APPLY ' if self.apply else 'would '}{message}")

    # ── 1. one student, one node ───────────────────────────────────────────
    def merge_duplicate_students(self):
        print("\n[1] Students keyed on the legacy `id` property")

        legacy = self.read(
            "MATCH (s:Student) WHERE s.id IS NOT NULL AND s.student_id IS NULL "
            "RETURN s.id AS legacy_id, count{(s)--()} AS degree"
        )
        if not legacy:
            print("  nothing to do")
            return

        for row in legacy:
            legacy_id, degree = row["legacy_id"], row["degree"]
            self.note(
                f"fold Student(id={legacy_id!r}, {degree} relationships) "
                f"into Student(student_id={legacy_id!r})"
            )

            # Move every relationship off the legacy node, then delete it.
            # Done per relationship type because Cypher cannot parameterise a
            # type, and APOC is not assumed to be installed on Aura Free.
            for rel_type in ("ATTEMPTED", "MASTERED", "NEEDS_REVIEW"):
                self.run_query(
                    f"""
                    MATCH (legacy:Student {{id: $id}})
                    WHERE legacy.student_id IS NULL
                    MERGE (canonical:Student {{student_id: $id}})
                    WITH legacy, canonical
                    MATCH (legacy)-[old:{rel_type}]->(target)
                    CREATE (canonical)-[fresh:{rel_type}]->(target)
                    SET fresh = properties(old)
                    DELETE old
                    """,
                    {"id": legacy_id},
                )

            self.run_query(
                "MATCH (legacy:Student {id: $id}) WHERE legacy.student_id IS NULL "
                "AND count{(legacy)--()} = 0 DELETE legacy",
                {"id": legacy_id},
            )

    # ── 2. one vocabulary ──────────────────────────────────────────────────
    def normalise_concepts(self):
        print("\n[2] Concept nodes under the error-type vocabulary")

        concepts = self.read("MATCH (c:Concept) RETURN c.name AS name")
        renames = [
            (row["name"], normalise_concept(row["name"]))
            for row in concepts
            if row["name"] and normalise_concept(row["name"]) != row["name"]
        ]

        if not renames:
            print("  nothing to do")
            return

        for old_name, new_name in renames:
            collides = self.read(
                "MATCH (c:Concept {name: $name}) RETURN count(c) AS n", {"name": new_name}
            )[0]["n"]
            attempts = self.read(
                "MATCH (:Student)-[a:ATTEMPTED]->(:Concept {name: $name}) RETURN count(a) AS n",
                {"name": old_name},
            )[0]["n"]

            self.note(
                f"{old_name} -> {new_name} "
                f"({attempts} attempts{', merging into an existing node' if collides else ''})"
            )

            for rel_type in ("ATTEMPTED", "MASTERED", "NEEDS_REVIEW"):
                self.run_query(
                    f"""
                    MATCH (old:Concept {{name: $old}})
                    MERGE (new:Concept {{name: $new}})
                    WITH old, new
                    MATCH (s)-[stale:{rel_type}]->(old)
                    CREATE (s)-[fresh:{rel_type}]->(new)
                    SET fresh = properties(stale)
                    DELETE stale
                    """,
                    {"old": old_name, "new": new_name},
                )

            # Only if nothing else points at it. An ErrorType->HAS_LESSON edge
            # or anything else unaccounted for must block the delete rather
            # than be silently orphaned.
            self.run_query(
                "MATCH (old:Concept {name: $old}) WHERE count{(old)--()} = 0 DELETE old",
                {"old": old_name},
            )

    # ── 3. one convention for mastery ──────────────────────────────────────
    def fold_legacy_status_relationships(self):
        print("\n[3] MASTERED / NEEDS_REVIEW as relationship types")

        legacy = self.read(
            "MATCH (s:Student)-[r:MASTERED|NEEDS_REVIEW]->(c:Concept) "
            "RETURN type(r) AS rel, c.name AS concept, properties(r) AS props, "
            "s.student_id AS student"
        )
        if not legacy:
            print("  nothing to do")
            return

        for row in legacy:
            props = row["props"]
            self.note(
                f"convert ({row['student']})-[:{row['rel']}]->({row['concept']}) "
                f"to ATTEMPTED score={props.get('latest_score')}/"
                f"{props.get('total_questions')} at {props.get('last_updated')}"
            )

        # CONVERTED, not deleted.
        #
        # These carry real data - latest_score, total_questions, last_updated -
        # so each one is a quiz a student actually sat. Dropping them would
        # destroy two attempts, one of them a 4/4.
        #
        # The relationship TYPE is the status: that is what MASTERED and
        # NEEDS_REVIEW meant before the status moved onto a property. So the
        # conversion is lossless in both directions - type becomes status,
        # latest_score becomes score, total_questions becomes total, and
        # percentage is recomputed the way progress_service computes it.
        self.run_query(
            """
            MATCH (s:Student)-[r:MASTERED|NEEDS_REVIEW]->(c:Concept)
            CREATE (s)-[a:ATTEMPTED {
                score: r.latest_score,
                total: r.total_questions,
                percentage: CASE WHEN coalesce(r.total_questions, 0) > 0
                                 THEN (toFloat(r.latest_score) / r.total_questions) * 100
                                 ELSE 0.0 END,
                status: type(r),
                timestamp: r.last_updated,
                migrated_from_relationship_type: true
            }]->(c)
            DELETE r
            """
        )

    # ── 4. make the above impossible again ─────────────────────────────────
    def add_constraints(self):
        print("\n[4] Uniqueness constraints")
        for name, label, prop in (
            ("student_id_unique", "Student", "student_id"),
            ("concept_name_unique", "Concept", "name"),
            ("error_type_name_unique", "ErrorType", "name"),
        ):
            self.note(f"CONSTRAINT {name} on :{label}({prop})")
            self.run_query(
                f"CREATE CONSTRAINT {name} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
            )

    # ── 5. the prerequisite graph ──────────────────────────────────────────
    def seed_prerequisites(self):
        print("\n[5] Concept prerequisite graph")

        cycles = find_cycles()
        if cycles:
            raise SystemExit(f"  ABORT: prerequisite graph has a cycle: {' -> '.join(cycles)}")

        self.note(f"MERGE {len(CONCEPT_TAGS)} Concept nodes (the canonical vocabulary)")
        for tag in CONCEPT_TAGS:
            self.run_query("MERGE (:Concept {name: $name})", {"name": tag})

        self.note(f"MERGE {len(PREREQUISITE_EDGES)} PREREQUISITE_OF relationships")
        for prereq, dependent in PREREQUISITE_EDGES:
            self.run_query(
                "MERGE (p:Concept {name: $prereq}) "
                "MERGE (d:Concept {name: $dependent}) "
                "MERGE (p)-[:PREREQUISITE_OF]->(d)",
                {"prereq": prereq, "dependent": dependent},
            )


def main():
    apply = "--apply" in sys.argv

    if not neo4j_db.driver:
        raise SystemExit("Neo4j is not connected - check NEO4J_URI in backend/.env")

    print("=" * 68)
    print("  APPLYING CHANGES" if apply else "  DRY RUN - nothing will be written")
    print("=" * 68)

    migration = Migration(apply)
    migration.merge_duplicate_students()
    migration.normalise_concepts()
    migration.fold_legacy_status_relationships()
    migration.add_constraints()
    migration.seed_prerequisites()

    print("\n" + "=" * 68)
    print(f"  {len(migration.planned)} change(s) "
          f"{'applied' if apply else 'planned - re-run with --apply to write'}")
    print("=" * 68)


if __name__ == "__main__":
    main()
