from flask_wtf import FlaskForm
from wtforms import HiddenField, StringField, TextAreaField, URLField
from wtforms.validators import DataRequired, Optional, Length, URL


class SearchForm(FlaskForm):
    keywords = StringField("Keywords", validators=[DataRequired(), Length(max=255)])
    location = StringField("Location (city, optional)", validators=[Optional(), Length(max=255)])


class ManualImportUrlForm(FlaskForm):
    # One or more URLs, one per line - per-URL format/reachability validation
    # happens in fetch_and_extract_text() (app/jobs/manual_import.py), same
    # as the single-URL path before this, so a malformed line is reported
    # per-URL rather than rejecting the whole batch.
    urls = TextAreaField("Job posting URL(s) - one per line", validators=[DataRequired(), Length(max=4000)])


class ManualImportReviewForm(FlaskForm):
    title = StringField("Job title", validators=[DataRequired(), Length(max=500)])
    company_name = StringField("Company", validators=[DataRequired(), Length(max=255)])
    location = StringField("Location", validators=[Optional(), Length(max=255)])
    start_date = StringField("Start date", validators=[Optional(), Length(max=50)])
    application_url = URLField("Application URL", validators=[Optional(), URL(require_tld=True)])
    description = TextAreaField("Description / pasted job text", validators=[Optional(), Length(max=20000)])
    # Which batch item (by index) this save belongs to, if any - empty for a
    # standalone save (no batch in progress, or the bookmarklet path, which
    # never uses a batch at all). Lets import_save() tell "this save
    # advances my in-progress batch" apart from "this is an unrelated save
    # that happens to arrive while some other batch is sitting in progress"
    # (e.g. using the bookmarklet mid-batch) - see app/jobs/routes.py.
    batch_index = HiddenField()
