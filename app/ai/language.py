"""Shared language-instruction helper for the "follows the UI language"
AI features (i18n pass 3): match explanation/improvement tips, company
insight, profile coaching, interview prep, CV profile statement. These
five prompt builders take an explicit `locale` argument and append the
instruction this module builds - the model is told exactly which language
to answer in, not left to infer it from whatever mix of English
instruction text and locale-aware (German-or-English, per i18n pass 2)
fact strings happens to be in the prompt, which was the actual bug this
pass exists to fix (see DECISIONS.md's i18n pass 3 entry).

The three employer-facing features (cover letter, application email,
reply suggestions) and the follow-up email never call this - their system
prompts hardcode German unconditionally, since a real German employer
needs a German document regardless of which language the candidate reads
the app in. Nothing in this module is wired into those four.
"""

_LANGUAGE_NAMES = {"en": "English", "de": "German"}


def language_instruction(locale):
    """One line to append to a "follows the UI language" system prompt.
    Falls back to English for an unrecognized locale code, matching
    app/i18n.py's own BABEL_DEFAULT_LOCALE fallback rather than raising -
    this runs inside a live generation call, not a place to fail loud over
    a locale string that's already been validated everywhere else."""
    language = _LANGUAGE_NAMES.get(locale, _LANGUAGE_NAMES["en"])
    return (
        f"\n\nRespond in {language}. This applies regardless of the "
        f"language any facts or labels below happen to be written in."
    )
