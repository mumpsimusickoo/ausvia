"""
Renders CandidateProfile and Job into plain-text fact blocks for AI prompts.
Only fields that are actually present are included - this is the single
place that decides what the AI is allowed to know, so it's also the anchor
for the anti-hallucination rule: if it's not in this text, the AI has no way
to know about it and must not claim it.
"""


def format_candidate_facts(profile):
    if profile is None:
        return "No candidate profile on file."

    lines = []
    if profile.full_name:
        lines.append(f"Name: {profile.full_name}")
    if profile.address or profile.city or profile.country:
        addr = ", ".join(p for p in [profile.address, profile.postal_code, profile.city, profile.country] if p)
        lines.append(f"Address: {addr}")
    if profile.phone:
        lines.append(f"Phone: {profile.phone}")
    if profile.contact_email:
        lines.append(f"Email: {profile.contact_email}")
    if profile.nationality:
        lines.append(f"Nationality: {profile.nationality}")

    if profile.education_entries:
        lines.append("Education:")
        for e in profile.education_entries:
            parts = [p for p in [e.degree, e.field, e.institution, e.country] if p]
            lines.append(f"  - {' / '.join(parts)}")

    if profile.experience_entries:
        lines.append("Experience:")
        for x in profile.experience_entries:
            parts = [p for p in [x.role, x.company] if p]
            lines.append(f"  - {' / '.join(parts)}")
            if x.responsibilities:
                lines.append(f"    Responsibilities: {x.responsibilities}")

    if profile.skills:
        skill_strs = [s.name + (f" ({s.proficiency})" if s.proficiency else "") for s in profile.skills]
        lines.append(f"Skills: {', '.join(skill_strs)}")

    if profile.languages:
        lang_strs = [f"{l.name} {l.level}" if l.level else l.name for l in profile.languages]
        lines.append(f"Languages: {', '.join(lang_strs)}")

    return "\n".join(lines) if lines else "No candidate profile details on file."


def format_job_facts(job):
    lines = [
        f"Job title: {job.title}",
        f"Company: {job.company_name or 'not specified'}",
        f"Location: {job.location or 'not specified'}",
    ]
    if job.start_date:
        lines.append(f"Start date: {job.start_date}")
    if job.requirements:
        lines.append(f"Requirements: {job.requirements}")
    if job.education_requirements:
        lines.append(f"Education requirements: {job.education_requirements}")
    if job.skills:
        lines.append(f"Skills mentioned: {', '.join(job.skills)}")
    if job.contact_person:
        lines.append(f"Named contact: {job.contact_person}")
    return "\n".join(lines)
