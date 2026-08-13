import pytest
from markupsafe import escape

from app.ai import process_qa
from app.ai.provider import AIProvider, AIResponse
from app.models.ai import ProcessQAAnswer, PROCESS_QA_QUESTIONS
from tests.conftest import login


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text):
        self._text = text

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=8, output_tokens=8)


def test_process_qa_page_lists_all_fixed_questions(client, db, make_user):
    make_user(email="qa1@example.com", password="Password123!")
    login(client, "qa1@example.com", "Password123!")

    resp = client.get("/profile/")
    for question in PROCESS_QA_QUESTIONS.values():
        assert str(escape(question)).encode() in resp.data


def test_generate_qa_answer_mock_mode_is_honest(client, db, make_user):
    make_user(email="qa2@example.com", password="Password123!")
    login(client, "qa2@example.com", "Password123!")

    resp = client.post("/profile/qa/ausbildungsverguetung", follow_redirects=True)
    assert resp.status_code == 200
    assert b"aren&#39;t available" in resp.data or b"aren't available" in resp.data

    answer = ProcessQAAnswer.query.filter_by(question_key="ausbildungsverguetung").first()
    assert answer is not None
    assert answer.provider == "mock"


def test_unknown_question_key_is_404(client, db, make_user):
    make_user(email="qa3@example.com", password="Password123!")
    login(client, "qa3@example.com", "Password123!")

    resp = client.post("/profile/qa/not-a-real-question")
    assert resp.status_code == 404


def test_generate_qa_answer_uses_real_provider_and_caches(app, db, make_user, monkeypatch):
    user = make_user(email="qa4@example.com")
    monkeypatch.setattr(process_qa, "get_provider", lambda: FakeProvider("Ausbildungsvergütung means training pay."))

    result1 = process_qa.generate_process_qa_answer(user, "ausbildungsverguetung")
    assert "training pay" in result1.answer_text

    monkeypatch.setattr(process_qa, "get_provider", lambda: FakeProvider("A different answer."))
    result2 = process_qa.generate_process_qa_answer(user, "ausbildungsverguetung")
    assert "training pay" in result2.answer_text  # cached

    assert ProcessQAAnswer.query.filter_by(user_id=user.id, question_key="ausbildungsverguetung").count() == 1


def test_qa_answers_are_independent_per_question(app, db, make_user, monkeypatch):
    user = make_user(email="qa5@example.com")
    monkeypatch.setattr(process_qa, "get_provider", lambda: FakeProvider("Answer about pay."))
    process_qa.generate_process_qa_answer(user, "ausbildungsverguetung")

    monkeypatch.setattr(process_qa, "get_provider", lambda: FakeProvider("Answer about response time."))
    process_qa.generate_process_qa_answer(user, "response_time")

    assert ProcessQAAnswer.query.filter_by(user_id=user.id).count() == 2
    assert process_qa.get_process_qa_answer(user, "ausbildungsverguetung").answer_text == "Answer about pay."
    assert process_qa.get_process_qa_answer(user, "response_time").answer_text == "Answer about response time."


def test_generate_process_qa_answer_rejects_unknown_key(app, db, make_user):
    user = make_user(email="qa6@example.com")
    with pytest.raises(ValueError):
        process_qa.generate_process_qa_answer(user, "not-a-real-question")


def test_qa_answers_are_per_user_not_shared(app, db, make_user, monkeypatch):
    user1 = make_user(email="qa7a@example.com")
    user2 = make_user(email="qa7b@example.com")
    monkeypatch.setattr(process_qa, "get_provider", lambda: FakeProvider("Answer for user 1."))
    process_qa.generate_process_qa_answer(user1, "response_time")

    assert process_qa.get_process_qa_answer(user2, "response_time") is None
