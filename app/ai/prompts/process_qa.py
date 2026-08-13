"""Prompt for answering one of a fixed set of common Ausbildung process/
terminology questions (Phase 9, app/models/ai.py's PROCESS_QA_QUESTIONS) -
deliberately a typed question picker, not open free-text chat (this app has
no chat-style UI anywhere else - see app/ai/process_qa.py's module
docstring for the reasoning). Candidate facts here are the user's own
account data, not a third-party attack surface (see DECISIONS.md) - no
untrusted-external-text fencing needed for those; the question text itself
is one of a small fixed, trusted, developer-authored set, never user input.
"""

SYSTEM = """You answer a common process or terminology question from an \
international candidate applying for a German Ausbildung (apprenticeship), \
for a career-tracking platform.

Rules, no exceptions:
- Answer only the exact question given below - don't drift into other \
topics.
- Ground general/typical-practice questions (e.g. what a German term means, \
what's normal/typical) in real, accurate knowledge of the German Ausbildung \
system - don't invent statistics or make up a specific number where only a \
typical range is actually known; say "typically" or "usually" rather than \
presenting an estimate as a hard fact.
- If the question is about the candidate's own situation (e.g. whether to \
mention something from their own background), use ONLY the candidate facts \
given below - never invent experience, qualifications, or details about \
their profile that aren't there.
- Never claim something is true of a specific employer or specific job \
posting - this answer is general guidance, not advice about one particular \
application.
- Be concise: 3-5 sentences.
"""


def build_process_qa_prompt(question_text, candidate_facts_text):
    user = (
        f"Question: {question_text}\n\n"
        f"Candidate profile (for context, only relevant to some questions):\n{candidate_facts_text}\n\n"
        "Answer the question now."
    )
    return SYSTEM, user
