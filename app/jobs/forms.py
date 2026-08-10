from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, URLField
from wtforms.validators import DataRequired, Optional, Length, URL


class SearchForm(FlaskForm):
    keywords = StringField("Keywords", validators=[DataRequired(), Length(max=255)])
    location = StringField("Location (city, optional)", validators=[Optional(), Length(max=255)])


class ManualImportUrlForm(FlaskForm):
    url = URLField("Job posting URL", validators=[DataRequired(), URL(require_tld=True)])


class ManualImportReviewForm(FlaskForm):
    title = StringField("Job title", validators=[DataRequired(), Length(max=500)])
    company_name = StringField("Company", validators=[DataRequired(), Length(max=255)])
    location = StringField("Location", validators=[Optional(), Length(max=255)])
    start_date = StringField("Start date", validators=[Optional(), Length(max=50)])
    application_url = URLField("Application URL", validators=[Optional(), URL(require_tld=True)])
    description = TextAreaField("Description / pasted job text", validators=[Optional(), Length(max=20000)])
