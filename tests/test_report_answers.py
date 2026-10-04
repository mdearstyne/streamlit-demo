import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
import requests

import report_answers as ai


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "EMBEDDINGS_PATH", tmp_path / "embeddings.sqlite3")
    monkeypatch.setattr(ai, "SPENDING_PATH", tmp_path / "usage.sqlite3")
    monkeypatch.setattr(ai, "LEGACY_PATH", tmp_path / "legacy.sqlite3")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-real-secret")
    monkeypatch.setattr(requests, "post", Mock(side_effect=AssertionError("Unexpected network request")))


def passage(text="SNAP benefits", document="report.pdf", page=3):
    return ai.passages_from_records([{"text": text, "file_path": document, "title": "Report", "page": page}])[0]


def save_vectors(passages):
    with ai.connect_embeddings(write=True) as db:
        db.executemany("INSERT INTO vectors VALUES (?, ?)", [(p["key"], json.dumps([1.0] + [0.0] * (ai.DIMENSIONS - 1))) for p in passages])


def test_passage_overlap_and_original_page():
    records = [{"text": "a" * 2800, "file_path": "report.pdf", "title": "Report", "page": 12}]
    passages = ai.passages_from_records(records)
    assert [len(p["text"]) for p in passages] == [1500, 1450, 100]
    assert all(p["page"] == 12 and p["document"] == "report.pdf" for p in passages)
    assert passages[0]["text"][-150:] == passages[1]["text"][:150]


def test_preparation_reuses_text_and_deduplicates_missing():
    existing = passage()
    save_vectors([existing])
    same_text = passage(document="another.pdf")
    new = passage("new evidence")
    missing, cost = ai.preparation_plan([existing, same_text, new, new])
    assert missing == [new]
    assert cost == pytest.approx(len(new["text"].encode()) * ai.EMBEDDING_PRICE / 1_000_000)


def test_embedding_reads_leave_database_unchanged():
    save_vectors([passage()])
    before = ai.EMBEDDINGS_PATH.read_bytes()
    assert ai.cached_vectors()
    assert ai.EMBEDDINGS_PATH.read_bytes() == before
    assert not ai.SPENDING_PATH.exists()


def test_legacy_database_blocks_new_ledger():
    ai.LEGACY_PATH.touch()
    with pytest.raises(ai.AnswerError, match="Migrate"):
        ai.reserve(0.01, "answers")
    assert not ai.SPENDING_PATH.exists()


def test_daily_budget_settlement_and_preparation_are_separate():
    reservation = ai.reserve(1.9, "answers")
    with pytest.raises(ai.AnswerError, match="daily"):
        ai.reserve(0.11, "answers")
    ai.settle(reservation, 0.1)
    ai.reserve(0.9, "embeddings")
    assert ai.daily_spend() == pytest.approx(0.1)
    with pytest.raises(ai.AnswerError, match="preparation"):
        ai.reserve(0.11, "embeddings")


def test_old_day_does_not_count_toward_answers_but_preparation_is_cumulative():
    with ai.connect_spending() as db:
        db.executemany("INSERT INTO spend(day, category, amount) VALUES (?, ?, ?)",
                       [("2000-01-01", "answers", 2), ("2000-01-01", "embeddings", 1)])
    ai.reserve(0.1, "answers")
    with pytest.raises(ai.AnswerError, match="preparation"):
        ai.reserve(0.01, "embeddings")


def test_concurrent_reservations_cannot_exceed_limit():
    with ai.connect_spending():
        pass
    def attempt(_):
        try:
            ai.reserve(0.6, "answers")
            return True
        except ai.AnswerError:
            return False
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(pool.map(attempt, range(6))) == 3
    assert ai.daily_spend() == pytest.approx(1.8)


def test_question_budget_rejects_before_api_call():
    budget = ai.RequestBudget(0.1, "answers")
    with pytest.raises(ai.AnswerError, match="selected spending"):
        budget.post("embeddings", {}, 0.11, ai.EMBEDDING_PRICE)
    requests.post.assert_not_called()
    assert not ai.SPENDING_PATH.exists()


def test_successful_request_accounts_for_returned_usage(monkeypatch):
    response = Mock(ok=True)
    response.json.return_value = {"usage": {"prompt_tokens": 1000, "completion_tokens": 100}}
    monkeypatch.setattr(requests, "post", Mock(return_value=response))
    budget = ai.RequestBudget(0.1, "answers")
    budget.post("chat/completions", {}, 0.02, ai.INPUT_PRICE, ai.OUTPUT_PRICE)
    expected = (1000 * ai.INPUT_PRICE + 100 * ai.OUTPUT_PRICE) / 1_000_000
    assert budget.cost == pytest.approx(expected)
    assert ai.daily_spend() == pytest.approx(expected)


@pytest.mark.parametrize("failure", ["timeout", "http"])
def test_failed_requests_keep_reservation_and_do_not_retry(monkeypatch, failure):
    if failure == "timeout":
        mock = Mock(side_effect=requests.Timeout("sensitive internal details"))
    else:
        mock = Mock(return_value=Mock(ok=False, status_code=401))
    monkeypatch.setattr(requests, "post", mock)
    with pytest.raises(ai.AnswerError) as exc:
        ai.RequestBudget(0.1, "answers").post("embeddings", {}, 0.02, ai.EMBEDDING_PRICE)
    assert "sensitive" not in str(exc.value)
    assert mock.call_count == 1
    assert ai.daily_spend() == pytest.approx(0.02)


@pytest.mark.parametrize("ids", [[], ["invented"]])
def test_missing_or_invented_citations_are_rejected(ids):
    with pytest.raises(ai.AnswerError, match="citations"):
        ai.validate_answer({"paragraphs": [{"text": "Finding", "source_ids": ids}]}, [{"id": "S1"}])


def test_insufficient_evidence_can_return_no_paragraphs():
    answer = {"paragraphs": [], "limitations": "No relevant evidence"}
    assert ai.validate_answer(answer, []) == answer


@pytest.mark.parametrize("question", [" ", "x" * 2001])
def test_invalid_question_does_not_contact_api(question):
    with pytest.raises(ai.AnswerError, match="2,000"):
        ai.answer_question(question, [], False)
    requests.post.assert_not_called()


def test_unprepared_collection_does_not_contact_api():
    with pytest.raises(ai.AnswerError, match="Prepare"):
        ai.answer_question("SNAP findings?", [passage()], False)
    requests.post.assert_not_called()


@pytest.mark.parametrize("thorough", [False, True])
def test_retrieval_respects_selected_collection_and_coverage_caps(thorough):
    passages = [passage(f"SNAP evidence {i}", document=f"report-{i // 3}.pdf") for i in range(120)]
    vectors = {p["key"]: [1.0, 0.0] for p in passages}
    vectors["unselected"] = [1.0, 0.0]
    budget = Mock()
    budget.embed.return_value = [[1.0, 0.0]]
    sources = ai.retrieve(passages, vectors, ["SNAP"], budget, thorough)
    assert len(sources) == (64 if thorough else 10)
    assert all(s["key"] != "unselected" for s in sources)
    assert len({s["id"] for s in sources}) == len(sources)
    if thorough:
        assert all(sum(s["document"] == doc for s in sources) <= 2 for doc in {s["document"] for s in sources})


@pytest.mark.parametrize("thorough", [False, True])
def test_answer_pipeline_has_citations_and_review_steps(monkeypatch, thorough):
    p = passage()
    save_vectors([p])
    budget = Mock(cost=0.01)
    budget.embed.return_value = [[1.0] + [0.0] * (ai.DIMENSIONS - 1)] * (4 if thorough else 1)
    answer = {"paragraphs": [{"text": "Finding", "source_ids": ["S1"]}], "limitations": "Selected evidence"}
    budget.generate.side_effect = [{"queries": ["benefits testing"]}, answer, answer] if thorough else [answer]
    monkeypatch.setattr(ai, "RequestBudget", Mock(return_value=budget))
    result = ai.answer_question("SNAP findings?", [p], thorough)
    assert result["answer"] == answer
    assert budget.generate.call_count == (3 if thorough else 1)
    requests.post.assert_not_called()


def test_empty_collection_does_not_contact_api():
    with pytest.raises(ai.AnswerError, match="No searchable"):
        ai.answer_question("SNAP findings?", [], False)
    requests.post.assert_not_called()


@pytest.mark.parametrize("vector", [[1.0], [float("nan")] * ai.DIMENSIONS])
def test_invalid_api_embeddings_are_rejected(monkeypatch, vector):
    budget = ai.RequestBudget(0.1, "answers")
    monkeypatch.setattr(budget, "post", lambda *args: {"data": [{"index": 0, "embedding": vector}]})
    with pytest.raises(ai.AnswerError, match="invalid embeddings"):
        budget.embed(["SNAP"])


def test_api_embeddings_are_sorted_into_input_order(monkeypatch):
    budget = ai.RequestBudget(0.1, "answers")
    first, second = [1.0] * ai.DIMENSIONS, [2.0] * ai.DIMENSIONS
    monkeypatch.setattr(budget, "post", lambda *args: {"data": [
        {"index": 1, "embedding": second}, {"index": 0, "embedding": first}]})
    assert budget.embed(["first", "second"]) == [first, second]


@pytest.mark.parametrize("reason,refusal", [("length", None), ("stop", "Refused")])
def test_truncated_or_refused_answers_are_not_displayed(monkeypatch, reason, refusal):
    budget = ai.RequestBudget(0.1, "answers")
    monkeypatch.setattr(budget, "post", lambda *args: {"choices": [
        {"finish_reason": reason, "message": {"refusal": refusal, "content": "partial"}}]})
    with pytest.raises(ai.AnswerError, match="could not complete"):
        budget.generate("instructions", {}, ai.ANSWER_SCHEMA, 100)
