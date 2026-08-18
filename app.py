"""Demo runner.

python app.py          -> runs the four required questions, printing every stage
python app.py --chat   -> ask your own questions
"""

import sys

from graphrag import GROQ_API_KEY, ask

# Windows consoles default to a legacy codepage that can't print LLM output
# containing curly quotes, em dashes, or other non-ASCII characters.
sys.stdout.reconfigure(encoding="utf-8")

QUESTIONS = [
    "Which employees know Python?",
    "Who is working on Project Alpha?",
    "Which employees belong to the AI department?",
    "Which projects have employees with AWS skills?",
]

LINE = "=" * 72


def show(question: str) -> None:
    print(LINE)
    print(f"QUESTION  {question}")
    try:
        result = ask(question)
    except Exception as error:
        print(f"ERROR     {error}")
        return
    print(f"CYPHER    {result['cypher']}")
    print("ROWS")
    for row in result["rows"]:
        print(f"          {row}")
    if not result["rows"]:
        print("          (none)")
    print(f"ANSWER    {result['answer']}")
    print()


def main() -> None:
    mode = "Groq LLM" if GROQ_API_KEY else "offline keyword fallback (no GROQ_API_KEY set)"
    print(f"Cypher generation: {mode}\n")

    if "--chat" in sys.argv:
        print("Type a question, or 'exit' to quit.\n")
        while True:
            question = input("> ").strip()
            if question.lower() in {"exit", "quit", ""}:
                break
            show(question)
        return

    for question in QUESTIONS:
        show(question)


if __name__ == "__main__":
    main()
