"""Optional report question interface. Paid requests require button clicks."""
import html
import os
import sqlite3
from pathlib import Path

import streamlit as st

from data_config import ENABLE_ADMIN_CONTROLS
from pdf_viewer import build_browser_pdf_url
from report_answers import (
    AnswerError, answer_question, daily_spend, fingerprint, passages_from_records,
    preparation_plan, prepare,
)


@st.cache_data(show_spinner=False, max_entries=4)
def cached_passages(records: list[dict]) -> list[dict]:
    return passages_from_records(records)


def render_answers(records: list[dict], pdf_dir_path: Path) -> None:
    st.subheader("Ask the reports")
    st.caption("Answers use retrieved report passages with links to supporting PDF pages. "
               "Check the cited evidence before relying on a finding.")
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        st.info("Report questions are not configured. The administrator must supply an OpenAI API key.")
        return
    if not records:
        st.info("No searchable text is available for report questions.")
        return
    try:
        passages = cached_passages(records)
        collection = fingerprint(passages, pdf_dir_path)
        missing, estimate = preparation_plan(passages)
        if missing:
            st.info("This collection needs preparation before questions can be answered.")
            if ENABLE_ADMIN_CONTROLS:
                st.write(f"{len(missing):,} new passages. Conservative cost estimate: USD {estimate:.4f}. Preparation limit: USD 1.")
                st.caption("Preparation sends indexed text to OpenAI. Existing embeddings are reused.")
                if st.button("Prepare report questions", disabled=estimate > 1):
                    with st.spinner("Preparing report passages..."):
                        prepare(missing)
                    st.rerun()
            else:
                st.caption("The administrator needs to prepare this collection.")
            return
        if ENABLE_ADMIN_CONTROLS:
            st.caption(f"Recorded answer spending today (UTC): USD {daily_spend():.4f} of USD 2.")
        with st.form("report_question_form"):
            question = st.text_area("Your question", max_chars=2000,
                                    placeholder="What has previous testing found related to SNAP benefits?")
            mode = st.radio("Answer mode", ["Quick answer", "Thorough review"], horizontal=True)
            st.caption("Quick answer retrieves a small set of passages (up to USD 0.10 per question).")
            st.caption("Thorough review searches related questions and gathers evidence across reports "
                       "(up to USD 0.50 per question).")
            st.caption("Neither guarantees exhaustive coverage. Questions and selected passages are sent to OpenAI.")
            submitted = st.form_submit_button("Ask the reports")
        if submitted:
            st.session_state.pop("report_answer", None)
            with st.spinner("Reviewing report evidence..."):
                result = answer_question(question, passages, mode == "Thorough review")
            st.session_state["report_answer"] = (collection, result)
        stored = st.session_state.get("report_answer")
        if stored and stored[0] == collection:
            show_answer(stored[1], pdf_dir_path, len({p["document"] for p in passages}))
    except AnswerError as exc:
        st.error(str(exc))
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        st.error("Report questions could not be completed. Contact the administrator. Ordinary search remains available.")


def show_answer(result: dict, folder: Path, total_reports: int) -> None:
    sources = {s["id"]: s for s in result["sources"]}
    st.write(result["question"])
    st.caption(f"{result['mode']} | Recorded API cost: USD {result['cost']:.4f}")
    if not result["answer"]["paragraphs"]:
        st.info("The retrieved passages did not provide enough evidence to answer this question.")
    for paragraph in result["answer"]["paragraphs"]:
        st.html("<p>" + html.escape(paragraph["text"]) + "</p>")
        for source_id in dict.fromkeys(paragraph["source_ids"]):
            source = sources[source_id]
            st.link_button(f"[{source_id}] {source['title']} — page {source['page']}",
                           build_browser_pdf_url(folder / source["document"], source["page"], []))
    st.write("Limitations")
    st.html("<p>" + html.escape(result["answer"]["limitations"]) + "</p>")
    covered = len({s["document"] for s in result["sources"]})
    st.caption(f"Retrieved {len(sources)} passages from {covered} of {total_reports} reports with indexed text. "
               "This is retrieval coverage, not confirmation that every report or page was reviewed.")
    with st.expander("Source passages considered"):
        for source in sources.values():
            st.write(f"[{source['id']}] {source['title']} — page {source['page']}")
            st.html("<p>" + html.escape(source["text"]) + "</p>")
            st.link_button(f"Open source {source['id']}",
                           build_browser_pdf_url(folder / source["document"], source["page"], []))
