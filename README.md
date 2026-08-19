# graphrag-mini

A small GraphRAG system over an org graph — Employees, Departments, Projects, Skills.
Ask a question in plain English, an LLM turns it into Cypher, Neo4j answers it, the LLM
phrases the result. Five files, no framework.

```
question -> LLM writes Cypher -> read-only guard -> Neo4j -> rows -> LLM writes the answer
```

## Files

| File | What it does |
|---|---|
| `db.py` | Neo4j connection + the read-only guard |
| `seed.py` | Builds the demo graph (run once) |
| `graphrag.py` | The pipeline: question → Cypher → rows → answer |
| `app.py` | CLI demo, prints every stage |
| `example.py` | Standalone Student/Course Cypher tutorial (see "Learning Cypher" below) |
| `tests/test_graphrag.py` | Tests for the four required questions (see "Tests" below) |
| `.env.example` | Copy to `.env` and fill in |

## Setup

**1. Start Neo4j** (Docker is the fastest route):

```bash
docker run -d --name neo4j-demo -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password123 neo4j:5.26
```

Browser opens at http://localhost:7474 — log in with `neo4j` / `password123`.
Neo4j Desktop or a free Aura instance work equally well; just update `.env`.

**2. Install and configure:**

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
pip install -r requirements.txt
copy .env.example .env          # then edit it
```

A Groq key is optional. Without one, `graphrag.py` uses a keyword matcher to build the
Cypher so the demo still runs — the graph half of the pipeline is unchanged either way.
Get a free key at console.groq.com and paste it into `.env` for the real thing.

**3. Build the graph:**

```bash
python seed.py
```

**4. Run the demo:**

```bash
python app.py            # the four required questions
python app.py --chat     # ask your own
```

Each question prints `QUESTION → CYPHER → ROWS → ANSWER`, which is exactly the sequence
to narrate on camera.

### Expected output for the four required questions

Against the graph `seed.py` builds (5 employees, 3 departments, 3 projects, 5 skills),
`python app.py` should produce:

| # | Question | Rows | Answer (offline fallback wording) |
|---|---|---|---|
| 1 | Which employees know Python? | Priya Sharma (ML Engineer), Sneha Iyer (Data Scientist), Rahul Verma (Data Engineer) | From the graph: Priya Sharma, ML Engineer; Sneha Iyer, Data Scientist; Rahul Verma, Data Engineer |
| 2 | Who is working on Project Alpha? | Priya Sharma (ML Engineer), Sneha Iyer (Data Scientist), Arjun Mehta (DevOps Engineer) | From the graph: Priya Sharma, ML Engineer; Sneha Iyer, Data Scientist; Arjun Mehta, DevOps Engineer |
| 3 | Which employees belong to the AI department? | Priya Sharma (ML Engineer), Sneha Iyer (Data Scientist) | From the graph: Priya Sharma, ML Engineer; Sneha Iyer, Data Scientist |
| 4 | Which projects have employees with AWS skills? | Project Beta (Kavya Nair), Project Gamma (Arjun Mehta), Project Alpha (Arjun Mehta) | From the graph: Project Beta, Kavya Nair; Project Gamma, Arjun Mehta; Project Alpha, Arjun Mehta |

With a `GROQ_API_KEY` set, the rows are identical (same graph, same Cypher shape) but the
`ANSWER` line is phrased by the LLM instead of the raw "From the graph: ..." fallback text.
Row order isn't guaranteed by Cypher — Neo4j may return the "Rows" column in a different
order across runs — so `tests/test_graphrag.py` compares row sets, not row order.

## The graph

```
(:Employee)-[:WORKS_IN]->(:Department)
(:Employee)-[:WORKS_ON]->(:Project)
(:Employee)-[:HAS_SKILL]->(:Skill)
```

5 employees, 3 departments, 3 projects, 5 skills. Paste this into Neo4j Browser to see it:

```cypher
MATCH (n)-[r]->(m) RETURN n, r, m
```

## Recording checklist

1. Neo4j Browser — run the query above, show the nodes and arrows.
2. `python app.py` — show all four questions answering.
3. Open `graphrag.py`, point at `generate_cypher`, `run_query`, `write_answer` — the three
   stages, in order.
4. Show `is_read_only` in `db.py` blocking a `DELETE`, then `matches_intent` in `graphrag.py`
   catching a safe-but-wrong query — explain why generated Cypher must never be trusted
   directly, on either axis.
5. Close on the AWS question: vector search would have to find one document mentioning both
   AWS and a project name. The graph just walks `Skill ← HAS_SKILL ← Employee → WORKS_ON → Project`.

## Concepts covered

- **RAG** — retrieve real data first, then let the model phrase the answer, so it can't invent facts.
- **GraphRAG** — the retrieval step is a graph traversal instead of a similarity search over text chunks.
- **Why a graph** — questions that need to join two facts ("projects staffed by AWS people") are one
  traversal in a graph and a guess in a vector store, because no single chunk contains both facts.
- **Nodes** — the entities: Employee, Department, Project, Skill.
- **Relationships** — the typed, directed edges between them.
- **Properties** — key/value pairs stored on nodes, e.g. `name`, `role`, `description`.
- **Retrieval** — the LLM sees the schema, writes Cypher, the guard validates it, Neo4j executes it.
- **Reaching the LLM** — returned rows are pasted into a second prompt as the only allowed source
  for the final answer.

## Guards: safety and intent

`db.is_read_only` checks that a generated query is *safe* — read-only, starts with `MATCH`. That's
necessary but not sufficient: a query can be perfectly safe and still answer the wrong question
(e.g. a `WORKS_IN` query returned for a question about skills). `graphrag.matches_intent` is a
second, semantic guard on top: it classifies the question into one of the four supported types
(skill / project / department, via `graphrag.INTENTS`) and checks that the generated Cypher
actually uses the relationship that type implies. If it doesn't, `ask()` in `graphrag.py` falls
back to the deterministic, intent-matched query from `_fallback_cypher` instead of running (and
answering from) the mismatched one. `ask()`'s result dict exposes this as `intent_validated`.

This is a constrained mapping, not a general fix — questions outside the four supported types
skip the check (`detect_intent` returns `None`) and run whatever Cypher was generated. Worth
stating out loud in the video.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/
```

`tests/test_graphrag.py` covers the four required questions from `app.py`:

- Cypher generated for each question uses the relationship the question implies
  (`matches_intent` / `graphrag.INTENTS`).
- The full `ask()` pipeline, with `db.run_query` mocked to return the rows you'd get from the
  seeded graph, produces the right rows and a correctly phrased answer.
- The semantic guard actually intervenes: given a deliberately off-topic (but read-only-safe)
  query, `ask()` discards it and runs the intent-matched fallback instead.

These run offline (`GROQ_API_KEY` is forced empty so Cypher comes from the deterministic keyword
fallback) — no Neo4j or network access required.

A further test class, `TestAgainstSeededDatabase`, runs the same four questions end to end
against a real Neo4j instance and checks the actual returned rows. It's opt-in and skipped by
default, since it rebuilds the graph via `seed.py` (wiping whatever `NEO4J_URI` points at):

```bash
RUN_INTEGRATION_TESTS=1 python -m pytest tests/ -k TestAgainstSeededDatabase
```

## Learning Cypher: Student/Course walkthrough

A second, self-contained example lives in [`example.py`](example.py) — a Student/Course
graph with the 10 practice queries below. It's independent of the Employee graph `seed.py`
builds, so running it won't disturb the main demo.

```bash
python example.py            # builds the graph, then runs all 10 queries
python example.py --build    # builds the graph only
python example.py --query 5  # builds the graph, then runs just query 5
python example.py --advanced # builds the graph, then runs the SET/MERGE/DELETE/...
                              # examples below (steps 10-14 of the learning order)
```

### The recommended learning order

If you're teaching or learning Cypher from scratch, go in this order — each step only
needs the ones before it:

1. **CREATE** — make nodes and relationships
2. **MATCH** — find nodes and relationships that already exist
3. **RETURN** — choose what a query outputs
4. **WHERE** — filter matched data by a condition
5. **relationships** — traverse `-[:TYPE]->` between nodes
6. **SET** — update properties on existing nodes/relationships
7. **MERGE** — create-if-missing, the idempotent version of CREATE
8. **DELETE** — remove nodes/relationships (`DETACH DELETE` for nodes with edges)
9. **aggregation** — `count()`, `collect()`, `avg()`, `sum()`, `GROUP BY`-style grouping
10. **OPTIONAL MATCH** — like a SQL `LEFT JOIN`, keeps rows even when the match fails
11. **WITH** — pipe results from one query part into the next
12. **UNWIND** — expand a list into rows
13. **CASE** — conditional expressions inside a query
14. **variable-length paths** — `-[:TYPE*1..3]->` to traverse a chain of unknown depth

The core shape to internalize:

```
MATCH   -> find nodes
WHERE   -> filter them
RETURN  -> show the result
```

versus SQL's `TABLE -> JOIN -> TABLE -> WHERE -> RESULT`: Cypher matches a **shape**
(nodes and relationships) instead of joining tables.

### Doing it manually in Neo4j Browser

`example.py` runs everything for you, but to build the same intuition by hand:

1. **Start Neo4j** and open Neo4j Browser at http://localhost:7474 (see Setup above).
2. **Clear old data** (optional, only if you want a blank graph):
   ```cypher
   MATCH (n) DETACH DELETE n
   ```
3. **Create the students** — paste and run:
   ```cypher
   CREATE
       (alice:Student {name: 'Alice', age: 22}),
       (bob:Student {name: 'Bob', age: 23}),
       (charlie:Student {name: 'Charlie', age: 21})
   RETURN alice, bob, charlie;
   ```
4. **Create the courses** — paste and run:
   ```cypher
   CREATE
       (python:Course {name: 'Python'}),
       (neo4j:Course {name: 'Neo4j'}),
       (docker:Course {name: 'Docker'})
   RETURN python, neo4j, docker;
   ```
5. **Create the relationships** — match the six nodes you just made, then connect them:
   ```cypher
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
   RETURN *;
   ```
6. **See the whole graph** to sanity-check it visually:
   ```cypher
   MATCH (n)-[r]->(m) RETURN n, r, m;
   ```
7. **Run the 10 practice queries one at a time**, reading each result before moving to
   the next — this is where the MATCH → WHERE → RETURN pattern actually sinks in:

   | # | Question | Query |
   |---|---|---|
   | 1 | All students | `MATCH (s:Student) RETURN s;` |
   | 2 | All courses | `MATCH (c:Course) RETURN c;` |
   | 3 | Student names | `MATCH (s:Student) RETURN s.name;` |
   | 4 | Students older than 21 | `MATCH (s:Student) WHERE s.age > 21 RETURN s.name, s.age;` |
   | 5 | Alice's courses | `MATCH (s:Student {name: 'Alice'})-[:ENROLLED_IN]->(c:Course) RETURN c.name;` |
   | 6 | Who is studying Python? | `MATCH (s:Student)-[:ENROLLED_IN]->(c:Course {name: 'Python'}) RETURN s.name;` |
   | 7 | Who is studying Neo4j? | `MATCH (s:Student)-[:ENROLLED_IN]->(c:Course {name: 'Neo4j'}) RETURN s.name;` |
   | 8 | Count students | `MATCH (s:Student) RETURN count(s);` |
   | 9 | Count students per course | `MATCH (s:Student)-[:ENROLLED_IN]->(c:Course) RETURN c.name, count(s);` |
   | 10 | Display complete graph | `MATCH (n)-[r]->(m) RETURN n, r, m;` |
8. **Read relationship queries like English.** For example:
   ```cypher
   MATCH (a:Student)-[:ENROLLED_IN]->(b:Course)
   RETURN a.name, b.name;
   ```
   reads as: *find a Student `a` who has an `ENROLLED_IN` relationship to a Course `b`,
   and return the student's name and course name.*
9. **Move on to the rest of the learning order** (SET, MERGE, DELETE, aggregation,
   OPTIONAL MATCH, WITH, UNWIND, CASE, variable-length paths) once steps 1-8 feel natural —
   each one builds directly on MATCH/WHERE/RETURN from this walkthrough. Examples for all
   of them, on the same Student/Course graph, are below — and runnable via
   `python example.py --advanced`.

### SET, MERGE, DELETE, aggregation, OPTIONAL MATCH, WITH, UNWIND, CASE, variable-length paths

Run these in order — later ones build on earlier ones (DELETE removes the student MERGE
just created; the variable-length path query needs the FRIEND_OF edges created right
before it).

**SET** — update a property on a node that already exists:
```cypher
MATCH (s:Student {name: 'Alice'}) SET s.age = 23 RETURN s.name, s.age;
```

**MERGE** — create-if-missing, for both a node and a relationship. Unlike `CREATE`,
running this twice does not create a duplicate Dave:
```cypher
MERGE (s:Student {name: 'Dave'}) ON CREATE SET s.age = 24
WITH s MATCH (c:Course {name: 'Docker'})
MERGE (s)-[:ENROLLED_IN]->(c)
RETURN s.name, s.age;
```

**DELETE** — remove Dave; `DETACH DELETE` also removes his `ENROLLED_IN` edge, which
plain `DELETE` would refuse to do while the edge still exists:
```cypher
MATCH (s:Student {name: 'Dave'}) DETACH DELETE s;
```

**aggregation** — `avg()`, `collect()`, and friends group rows the way SQL's
`GROUP BY` does, keyed by whatever isn't itself being aggregated:
```cypher
MATCH (s:Student) RETURN avg(s.age) AS averageAge;

MATCH (c:Course)<-[:ENROLLED_IN]-(s:Student)
RETURN c.name AS course, collect(s.name) AS students;
```

**OPTIONAL MATCH** — like SQL's `LEFT JOIN`: keeps every student even when the second
match finds nothing, filling the missing side with `null` instead of dropping the row:
```cypher
MATCH (s:Student)
OPTIONAL MATCH (s)-[:ENROLLED_IN]->(c:Course {name: 'Docker'})
RETURN s.name AS student, c.name AS docker;
```

**WITH** — pipes the result of one part of a query into the next, so you can filter on
an aggregate (`WHERE` can't reference `count()` directly without it):
```cypher
MATCH (s:Student)-[:ENROLLED_IN]->(c:Course)
WITH c, count(s) AS numStudents
WHERE numStudents > 1
RETURN c.name AS course, numStudents;
```

**UNWIND** — the reverse of `collect()`: expands a list into one row per item, useful
for turning a plain list of values into something you can `MATCH` against:
```cypher
UNWIND ['Python', 'Neo4j', 'Docker'] AS courseName
MATCH (c:Course {name: courseName})<-[:ENROLLED_IN]-(s:Student)
RETURN courseName, count(s) AS numStudents;
```

**CASE** — an inline conditional expression, Cypher's equivalent of SQL's `CASE WHEN`:
```cypher
MATCH (s:Student)
RETURN s.name AS student,
       CASE WHEN s.age >= 23 THEN 'Senior' ELSE 'Junior' END AS level;
```

**variable-length paths** — `-[:TYPE*min..max]->` traverses a chain of relationships of
unknown depth. First give the students something to chain through:
```cypher
MATCH (alice:Student {name: 'Alice'}),
      (bob:Student {name: 'Bob'}),
      (charlie:Student {name: 'Charlie'})
MERGE (alice)-[:FRIEND_OF]->(bob)
MERGE (bob)-[:FRIEND_OF]->(charlie);
```
Then walk 1 to 2 hops out from Alice — this returns both Bob (1 hop) and Charlie
(2 hops, via Bob), which a fixed-length `-[:FRIEND_OF]->` could never reach in one query:
```cypher
MATCH (a:Student {name: 'Alice'})-[:FRIEND_OF*1..2]->(friend:Student)
RETURN DISTINCT friend.name AS friend;
```
