"""Create the demo graph in Neo4j. Run this once: python seed.py"""

from db import get_driver

EMPLOYEES = [
    ("Priya Sharma", "ML Engineer", "AI"),
    ("Sneha Iyer", "Data Scientist", "AI"),
    ("Rahul Verma", "Data Engineer", "Data Engineering"),
    ("Kavya Nair", "Analytics Engineer", "Data Engineering"),
    ("Arjun Mehta", "DevOps Engineer", "Platform"),
]

DEPARTMENTS = ["AI", "Data Engineering", "Platform"]

PROJECTS = [
    ("Project Alpha", "Customer churn prediction"),
    ("Project Beta", "Real-time data pipeline"),
    ("Project Gamma", "Internal developer portal"),
]

SKILLS = ["Python", "AWS", "Neo4j", "SQL", "Docker"]

HAS_SKILL = [
    ("Priya Sharma", "Python"),
    ("Priya Sharma", "Neo4j"),
    ("Sneha Iyer", "Python"),
    ("Sneha Iyer", "SQL"),
    ("Rahul Verma", "Python"),
    ("Rahul Verma", "SQL"),
    ("Kavya Nair", "AWS"),
    ("Kavya Nair", "SQL"),
    ("Arjun Mehta", "AWS"),
    ("Arjun Mehta", "Docker"),
]

WORKS_ON = [
    ("Priya Sharma", "Project Alpha"),
    ("Sneha Iyer", "Project Alpha"),
    ("Rahul Verma", "Project Beta"),
    ("Kavya Nair", "Project Beta"),
    ("Arjun Mehta", "Project Gamma"),
    ("Arjun Mehta", "Project Alpha"),
]

CLEAR = "MATCH (n) DETACH DELETE n"

CONSTRAINTS = [
    "CREATE CONSTRAINT emp_name IF NOT EXISTS FOR (e:Employee) REQUIRE e.name IS UNIQUE",
    "CREATE CONSTRAINT dep_name IF NOT EXISTS FOR (d:Department) REQUIRE d.name IS UNIQUE",
    "CREATE CONSTRAINT prj_name IF NOT EXISTS FOR (p:Project) REQUIRE p.name IS UNIQUE",
    "CREATE CONSTRAINT skl_name IF NOT EXISTS FOR (s:Skill) REQUIRE s.name IS UNIQUE",
]


def build(tx):
    for name in DEPARTMENTS:
        tx.run("MERGE (:Department {name: $name})", name=name)

    for name in SKILLS:
        tx.run("MERGE (:Skill {name: $name})", name=name)

    for name, description in PROJECTS:
        tx.run(
            "MERGE (p:Project {name: $name}) SET p.description = $description",
            name=name,
            description=description,
        )

    for name, role, department in EMPLOYEES:
        tx.run(
            """
            MERGE (e:Employee {name: $name})
            SET e.role = $role
            WITH e
            MATCH (d:Department {name: $department})
            MERGE (e)-[:WORKS_IN]->(d)
            """,
            name=name,
            role=role,
            department=department,
        )

    for employee, skill in HAS_SKILL:
        tx.run(
            """
            MATCH (e:Employee {name: $employee}), (s:Skill {name: $skill})
            MERGE (e)-[:HAS_SKILL]->(s)
            """,
            employee=employee,
            skill=skill,
        )

    for employee, project in WORKS_ON:
        tx.run(
            """
            MATCH (e:Employee {name: $employee}), (p:Project {name: $project})
            MERGE (e)-[:WORKS_ON]->(p)
            """,
            employee=employee,
            project=project,
        )


def main():
    driver = get_driver()
    with driver.session() as session:
        session.run(CLEAR)
        for statement in CONSTRAINTS:
            session.run(statement)
        session.execute_write(build)
        counts = session.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS total ORDER BY label"
        ).data()
        edges = session.run("MATCH ()-[r]->() RETURN count(r) AS total").single()["total"]
    driver.close()

    print("Graph created.")
    for row in counts:
        print(f"  {row['label']:<12} {row['total']}")
    print(f"  relationships {edges}")


if __name__ == "__main__":
    main()
