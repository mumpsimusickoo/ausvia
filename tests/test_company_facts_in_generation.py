"""Regression tests for the small fix wiring real Company data (Phase 6)
into cover-letter/application-email generation. Before this fix,
format_job_facts() only ever read Job fields - a job's linked Company row's
industry/website/description (real, populated data) never reached the AI
prompt at all.

AI_PROVIDER is "mock" in this environment (see AI.md/QA_REPORT.md), so
there's no live model to demonstrate actually *uses* the facts well - these
tests verify the part that's ours to guarantee: the facts reach the prompt
text, gracefully degrade to nothing when there's no company data, and the
system prompt explicitly permits (without requiring) referencing them.
"""
from app.ai.facts import format_company_facts, format_job_facts
from app.ai.prompts.cover_letter import build_generation_prompt, GENERATION_SYSTEM
from app.models import Company, Job


def make_job(db, **overrides):
    kwargs = dict(dedup_key="company-facts-test", employment_type="Ausbildung", title="Fachinformatiker")
    kwargs.update(overrides)
    job = Job(**kwargs)
    db.session.add(job)
    db.session.commit()
    return job


def test_format_company_facts_returns_none_for_no_company():
    assert format_company_facts(None) is None


def test_format_company_facts_returns_none_for_company_with_no_populated_fields(db):
    company = Company(name="Nameless GmbH", normalized_name="nameless")
    db.session.add(company)
    db.session.commit()

    assert format_company_facts(company) is None


def test_format_company_facts_includes_populated_fields(db):
    company = Company(
        name="Siemens AG",
        normalized_name="siemens",
        industry="Industrial automation",
        location="München",
        website="https://siemens.com",
        description="A global technology company focused on industry, infrastructure, and mobility.",
    )
    db.session.add(company)
    db.session.commit()

    facts = format_company_facts(company)
    assert "Industry: Industrial automation" in facts
    assert "Location: München" in facts
    assert "Website: https://siemens.com" in facts
    assert "Description (from job postings): A global technology company" in facts
    # name isn't repeated here - format_job_facts already states "Company: <name>"
    assert "Siemens AG" not in facts


def test_format_job_facts_includes_company_details_when_present(db):
    company = Company(name="Siemens AG", normalized_name="siemens", industry="Industrial automation")
    db.session.add(company)
    db.session.commit()
    job = make_job(db, title="Elektroniker", company_id=company.id)

    facts = format_job_facts(job)
    assert "Company details:" in facts
    assert "Industry: Industrial automation" in facts


def test_format_job_facts_has_no_company_details_section_when_company_is_none(db):
    job = make_job(db, title="Elektroniker")  # no company_id
    facts = format_job_facts(job)
    assert "Company details:" not in facts


def test_format_job_facts_has_no_company_details_section_when_company_has_no_fields(db):
    company = Company(name="Nameless GmbH", normalized_name="nameless")
    db.session.add(company)
    db.session.commit()
    job = make_job(db, title="Elektroniker", company_id=company.id)

    facts = format_job_facts(job)
    assert "Company details:" not in facts


def test_generation_prompt_carries_company_facts_and_system_permits_using_them(db):
    company = Company(
        name="Siemens AG",
        normalized_name="siemens",
        industry="Industrial automation",
        description="A global technology company focused on industry, infrastructure, and mobility.",
    )
    db.session.add(company)
    db.session.commit()
    job = make_job(db, title="Elektroniker", company_id=company.id)

    _, user_prompt = build_generation_prompt("Candidate: Test Candidate", format_job_facts(job), "Sehr geehrte Damen und Herren")

    assert "Industry: Industrial automation" in user_prompt
    assert "A global technology company" in user_prompt
    assert "Company details" in GENERATION_SYSTEM
    assert "never invent" in GENERATION_SYSTEM.lower() or "never add anything beyond it" in GENERATION_SYSTEM
