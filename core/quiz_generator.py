"""Exam questions for a section of notes."""
from core import llm
from core.notes_generator import SYSTEM

QUIZ_SCHEMA = {
    "type": "object",
    "properties": {
        "mcq": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "answer_index": {"type": "integer"},
                    "explanation": {"type": "string"},
                },
                "required": ["question", "options", "answer_index", "explanation"],
            },
        },
        "short_answer": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"question": {"type": "string"}, "answer": {"type": "string"}},
                "required": ["question", "answer"],
            },
        },
        "long_answer": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"question": {"type": "string"}, "answer": {"type": "string"}},
                "required": ["question", "answer"],
            },
        },
    },
    "required": ["mcq", "short_answer", "long_answer"],
}


def generate_quiz(section: dict, lecture_title: str, n_mcq: int = 4, n_short: int = 3, n_long: int = 1) -> dict:
    notes = section["notes"]
    prompt = (
        f"Lecture: {lecture_title}\nSection: {section['title']}\n\nNOTES\n{notes['long']}\n\n"
        "Key points:\n" + "\n".join(f"- {p}" for p in notes.get("key_points", [])) + "\n\n"
        f"Write exam questions that test understanding of this section (not trivia):\n"
        f"- mcq: {n_mcq} multiple-choice questions, each with exactly 4 options, answer_index (0–3) of the "
        "correct option, and an explanation of why it is right and the others are wrong.\n"
        f"- short_answer: {n_short} questions answerable in 2–4 sentences, with model answers.\n"
        f"- long_answer: {n_long} exam-style essay or problem question with a full model answer in Markdown.\n"
        "Mix recall, application and analysis questions."
    )
    data = llm.chat_json(prompt, QUIZ_SCHEMA, system=SYSTEM, temperature=0.4)
    mcq = []
    for q in data.get("mcq", []):
        opts = [str(o) for o in q.get("options", [])][:6]
        if len(opts) >= 2 and 0 <= int(q.get("answer_index", -1)) < len(opts):
            mcq.append({**q, "options": opts, "answer_index": int(q["answer_index"])})
    data["mcq"] = mcq
    return data
