from datetime import date

from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import HiddenField, SelectField, SelectMultipleField, StringField, TextAreaField, URLField
from wtforms.validators import DataRequired, Optional, Length, URL
from wtforms.widgets import CheckboxInput, ListWidget

REQUIRED = _l("This field is required.")


def _max_length_message(max_len):
    return _l("Must be at most %(max)d characters long.", max=max_len)


def _year_range_choices():
    # 2026-08-28: Ausbildung places are almost always advertised for a start
    # this year or the next few - Job.start_date is real-but-free-form
    # ("01.09.2027", "sofort", "2027", ...), so this is a *year* filter
    # (matching the same \d{4} extraction app/ai/matching.py's
    # _score_start_date already uses), not a calendar-date picker.
    current_year = date.today().year
    return [("", _l("Any"))] + [(str(y), str(y)) for y in range(current_year, current_year + 6)]


# Reuses app/ai/matching.py's own recommendation thresholds rather than
# inventing separate score breakpoints - "Good match" already means >=60
# everywhere else in this app.
def _min_score_choices():
    return [
        ("", _l("Any")),
        ("40", _l("40+ (some gaps)")),
        ("60", _l("60+ (good match)")),
        ("80", _l("80+ (strong match)")),
    ]


def _sort_choices():
    return [("match", _l("Best match")), ("newest", _l("Newest"))]


class SearchForm(FlaskForm):
    keywords = StringField(_l("Keywords"), validators=[DataRequired(message=REQUIRED), Length(max=255, message=_max_length_message(255))])
    location = StringField(_l("Location (city, optional)"), validators=[Optional(), Length(max=255, message=_max_length_message(255))])
    # Year range and minimum score: real fields with real data behind them
    # (see DECISIONS.md for the fill-rate numbers checked before adding
    # these). Radius, German level, and category were all considered and
    # dropped - no real data backs them yet, see the same entry.
    start_year_min = SelectField(_l("Start year, from"), choices=_year_range_choices, validators=[Optional()])
    start_year_max = SelectField(_l("Start year, to"), choices=_year_range_choices, validators=[Optional()])
    min_score = SelectField(_l("Minimum match score"), choices=_min_score_choices, validators=[Optional()])
    sort = SelectField(_l("Sort by"), choices=_sort_choices, validators=[Optional()], default="match")
    # Choices are set per-request from the enabled adapters (app/jobs/
    # routes.py) - a source can be added/disabled by an admin without a
    # code change, so this can't be a fixed class-level list.
    sources = SelectMultipleField(
        _l("Sources"), validators=[Optional()],
        widget=ListWidget(prefix_label=False), option_widget=CheckboxInput(),
    )


class ManualImportUrlForm(FlaskForm):
    # One or more URLs, one per line - per-URL format/reachability validation
    # happens in fetch_and_extract_text() (app/jobs/manual_import.py), same
    # as the single-URL path before this, so a malformed line is reported
    # per-URL rather than rejecting the whole batch.
    urls = TextAreaField(
        _l("Job posting URL(s) - one per line"),
        validators=[DataRequired(message=REQUIRED), Length(max=4000, message=_max_length_message(4000))],
    )


class ManualImportReviewForm(FlaskForm):
    title = StringField(_l("Job title"), validators=[DataRequired(message=REQUIRED), Length(max=500, message=_max_length_message(500))])
    company_name = StringField(_l("Company"), validators=[DataRequired(message=REQUIRED), Length(max=255, message=_max_length_message(255))])
    location = StringField(_l("Location"), validators=[Optional(), Length(max=255, message=_max_length_message(255))])
    start_date = StringField(_l("Start date"), validators=[Optional(), Length(max=50, message=_max_length_message(50))])
    # Salary follow-up pass (2026-08-30): matches Job.salary's own
    # db.String(255) column length (app/models/job.py) - free text, not a
    # structured number, since real postings state pay in wildly
    # different shapes (a single figure, a per-year range, a per-training-
    # year table, gross vs. net, etc.) that a numeric field couldn't hold
    # without lossy normalization.
    salary = StringField(_l("Salary"), validators=[Optional(), Length(max=255, message=_max_length_message(255))])
    application_url = URLField(_l("Application URL"), validators=[Optional(), URL(require_tld=True, message=_l("Please enter a valid URL."))])
    description = TextAreaField(_l("Description / pasted job text"), validators=[Optional(), Length(max=20000, message=_max_length_message(20000))])
    # Which batch item (by index) this save belongs to, if any - empty for a
    # standalone save (no batch in progress, or the bookmarklet path, which
    # never uses a batch at all). Lets import_save() tell "this save
    # advances my in-progress batch" apart from "this is an unrelated save
    # that happens to arrive while some other batch is sitting in progress"
    # (e.g. using the bookmarklet mid-batch) - see app/jobs/routes.py.
    batch_index = HiddenField()
