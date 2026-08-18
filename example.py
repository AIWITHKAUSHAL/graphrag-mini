"""Standalone Cypher tutorial: a Student/Course graph, separate from the main demo.

Builds the example graph from the "Students enrolled in Courses" walkthrough and
then runs the 10 practice queries against it, printing each query and its rows.

    python example.py            builds the graph, then runs all 10 queries
    python example.py --build    builds the graph only
    python example.py --query 5  builds the graph, then runs just query 5
    python example.py --advanced builds the graph, then runs the SET / MERGE / DELETE /
                                  aggregation / OPTIONAL MATCH / WITH / UNWIND / CASE /
                                  variable-length-path examples

Uses the same Neo4j connection as the rest of the project (db.py / .env), but the
Student/Course nodes it creates are independent of the Employee/Department/Project/
Skill graph that seed.py builds — CLEAR below only removes Student and Course nodes,
so running this won't touch data created by seed.py.
"""

import sys

from db import get_driver, run_query

CLEAR = "MATCH (n) WHERE n:Student OR n:Course DETACH DELETE n"

CREATE_STUDENTS = """
CREATE
    (:Student {name: 'Alice', age: 22}),
    (:Student {name: 'Bob', age: 23}),
    (:Student {name: 'Charlie', age: 21})
"""

CREATE_COURSES = """
CREATE
    (:Course {name: 'Python'}),
    (:Course {name: 'Neo4j'}),
    (:Course {name: 'Docker'})
"""

CREATE_RELATIONSHIPS = """
MATCH (alice:Student {name: 'Alice'}),
      (bob:Student {name: 'Bob'}),
      (charlie:Student {name: 'Charlie'}),
      (python:Course {name: 'Python'}),
      (neo4j:Course {name: 'Neo4j'}),
      (docker:Course {name: 'Docker'})
CREATE
    (alice)-[:ENROLLED_IN]->(python),
    (alice)-[:ENROLLED_IN]->(neo4j),
    (bob)-[:ENROLLED_IN]->(python),
    (bob)-[:ENROLLED_IN]->(docker),
    (charlie)-[:ENROLLED_IN]->(neo4j)
"""

QUERIES = [
    ("All students", "MATCH (s:Student) RETURN s"),
    ("All courses", "MATCH (c:Course) RETURN c"),
    ("Student names", "MATCH (s:Student) RETURN s.name"),
    (
        "Students older than 21",
        "MATCH (s:Student) WHERE s.age > 21 RETURN s.name, s.age",
    ),
    (
        "Alice's courses",
        "MATCH (s:Student {name: 'Alice'})-[:ENROLLED_IN]->(c:Course) RETURN c.name",
    ),
    (
        "Who is studying Python?",
        "MATCH (s:Student)-[:ENROLLED_IN]->(c:Course {name: 'Python'}) RETURN s.name",
    ),
    (
        "Who is studying Neo4j?",
        "MATCH (s:Student)-[:ENROLLED_IN]->(c:Course {name: 'Neo4j'}) RETURN s.name",
    ),
    ("Count students", "MATCH (s:Student) RETURN count(s)"),
    (
        "Count students per course",
        "MATCH (s:Student)-[:ENROLLED_IN]->(c:Course) RETURN c.name, count(s)",
    ),
    ("Display complete graph", "MATCH (n)-[r]->(m) RETURN n, r, m"),
]

# Each entry runs after the 10 queries above, in order — later steps build on earlier
# ones (e.g. DELETE removes the student MERGE just added). "write" steps run through the
# driver directly since db.run_query()'s guard deliberately blocks non-MATCH statements;
# "read" steps go through run_query() like the 10 queries above.
ADVANCED_STEPS = [
    (
        "SET — Alice has a birthday",
        "MATCH (s:Student {name: 'Alice'}) SET s.age = 23 RETURN s.name, s.age",
        "write",
    ),
    (
        "MERGE — add Dave if he doesn't exist yet, then enroll him in Docker",
        "MERGE (s:Student {name: 'Dave'}) ON CREATE SET s.age = 24 "
        "WITH s MATCH (c:Course {name: 'Docker'}) "
        "MERGE (s)-[:ENROLLED_IN]->(c) RETURN s.name, s.age",
        "write",
    ),
    (
        "DELETE — Dave drops out (DETACH removes his ENROLLED_IN edge too)",
        "MATCH (s:Student {name: 'Dave'}) DETACH DELETE s",
        "write",
    ),
    (
        "aggregation — average student age",
        "MATCH (s:Student) RETURN avg(s.age) AS averageAge",
        "read",
    ),
    (
        "aggregation — roster collected per course",
        "MATCH (c:Course)<-[:ENROLLED_IN]-(s:Student) "
        "RETURN c.name AS course, collect(s.name) AS students",
        "read",
    ),
    (
        "OPTIONAL MATCH — every student, with their Docker enrollment if any",
        "MATCH (s:Student) "
        "OPTIONAL MATCH (s)-[:ENROLLED_IN]->(c:Course {name: 'Docker'}) "
        "RETURN s.name AS student, c.name AS docker",
        "read",
    ),
    (
        "WITH — courses with more than one student enrolled",
        "MATCH (s:Student)-[:ENROLLED_IN]->(c:Course) "
        "WITH c, count(s) AS numStudents "
        "WHERE numStudents > 1 "
        "RETURN c.name AS course, numStudents",
        "read",
    ),
    (
        "UNWIND — expand a plain list into rows, one MATCH per item",
        "UNWIND ['Python', 'Neo4j', 'Docker'] AS courseName "
        "MATCH (c:Course {name: courseName})<-[:ENROLLED_IN]-(s:Student) "
        "RETURN courseName, count(s) AS numStudents",
        "read",
    ),
    (
        "CASE — label each student Senior/Junior by age",
        "MATCH (s:Student) "
        "RETURN s.name AS student, "
        "CASE WHEN s.age >= 23 THEN 'Senior' ELSE 'Junior' END AS level",
        "read",
    ),
    (
        "variable-length paths — first, connect the students as friends",
        "MATCH (alice:Student {name: 'Alice'}), "
        "(bob:Student {name: 'Bob'}), "
        "(charlie:Student {name: 'Charlie'}) "
        "MERGE (alice)-[:FRIEND_OF]->(bob) "
        "MERGE (bob)-[:FRIEND_OF]->(charlie)",
        "write",
    ),
    (
        "variable-length paths — everyone reachable from Alice within 2 hops",
        "MATCH (a:Student {name: 'Alice'})-[:FRIEND_OF*1..2]->(friend:Student) "
        "RETURN DISTINCT friend.name AS friend",
        "read",
    ),
]

LINE = "=" * 72


def build_graph() -> None:
    """Steps 1-3: wipe any prior Student/Course nodes, then recreate the demo graph."""
    driver = get_driver()
    with driver.session() as session:
        session.run(CLEAR)
        session.run(CREATE_STUDENTS)
        session.run(CREATE_COURSES)
        session.run(CREATE_RELATIONSHIPS)
        students = session.run("MATCH (s:Student) RETURN count(s) AS total").single()["total"]
        courses = session.run("MATCH (c:Course) RETURN count(c) AS total").single()["total"]
        edges = session.run(
            "MATCH (:Student)-[r:ENROLLED_IN]->(:Course) RETURN count(r) AS total"
        ).single()["total"]

    print(f"Graph created: {students} students, {courses} courses, {edges} ENROLLED_IN edges.")


def _run_write(cypher: str) -> list:
    """Execute a write statement directly against the driver, bypassing the
    read-only guard in db.run_query() — used only by ADVANCED_STEPS, which
    intentionally demonstrates SET / MERGE / DELETE."""
    driver = get_driver()
    with driver.session() as session:
        return [record.data() for record in session.run(cypher)]


def run_one(index: int) -> None:
    title, cypher = QUERIES[index]
    print(LINE)
    print(f"QUERY {index + 1} — {title}")
    print(cypher.strip())
    print("-" * 72)
    rows = run_query(cypher)
    if not rows:
        print("(no rows)")
    for row in rows:
        print(row)
    print()


def run_advanced() -> None:
    print(LINE)
    print("ADVANCED: SET, MERGE, DELETE, aggregation, OPTIONAL MATCH, WITH, UNWIND, "
          "CASE, variable-length paths")
    for title, cypher, kind in ADVANCED_STEPS:
        print(LINE)
        print(title)
        print(cypher)
        print("-" * 72)
        rows = _run_write(cypher) if kind == "write" else run_query(cypher)
        if not rows:
            print("(no rows returned)")
        for row in rows:
            print(row)
        print()


def main() -> None:
    build_graph()
    print()

    if "--build" in sys.argv:
        return

    if "--advanced" in sys.argv:
        run_advanced()
        return

    if "--query" in sys.argv:
        index = int(sys.argv[sys.argv.index("--query") + 1]) - 1
        run_one(index)
        return

    for index in range(len(QUERIES)):
        run_one(index)


if __name__ == "__main__":
    main()
