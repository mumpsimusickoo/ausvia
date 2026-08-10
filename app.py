import os
import json

from flask import Flask, render_template, request, redirect, url_for, flash

import jobsearch
import coverletter
import pdfmerge
import gmail_client

app = Flask(__name__)
app.secret_key = "local-dev-only-change-me"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "generated")
PROFILE_FILE = os.path.join(BASE_DIR, "profile.json")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# very small in-memory cache of last search results, keyed by refnr
LAST_RESULTS = {}


def load_profile():
    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE) as f:
            return json.load(f)
    return {}


def save_profile(data):
    with open(PROFILE_FILE, "w") as f:
        json.dump(data, f, indent=2)


@app.route("/", methods=["GET", "POST"])
def home():
    profile = load_profile()

    if request.method == "POST":
        profile.update({
            "your_name": request.form.get("your_name", ""),
            "your_address": request.form.get("your_address", ""),
            "your_email": request.form.get("your_email", ""),
            "your_phone": request.form.get("your_phone", ""),
            "city": request.form.get("city", ""),
            "study_field": request.form.get("study_field", ""),
            "field_keywords": request.form.get("field_keywords", ""),
            "search_keywords": request.form.get("search_keywords", ""),
            "search_location": request.form.get("search_location", ""),
        })

        # handle file uploads (only overwrite if a new file was chosen)
        for field, fname in [("cv", "cv.pdf"), ("diploma", "diploma.pdf")]:
            f = request.files.get(field)
            if f and f.filename:
                f.save(os.path.join(UPLOAD_DIR, fname))
                profile[f"{field}_path"] = os.path.join(UPLOAD_DIR, fname)

        translations = request.files.getlist("translations")
        if translations and translations[0].filename:
            paths = []
            for i, f in enumerate(translations):
                path = os.path.join(UPLOAD_DIR, f"translation_{i}.pdf")
                f.save(path)
                paths.append(path)
            profile["translations_paths"] = paths

        save_profile(profile)
        flash("Profile saved.")
        return redirect(url_for("home"))

    return render_template("index.html", profile=profile)


@app.route("/search")
def search():
    profile = load_profile()
    if not profile.get("search_keywords"):
        flash("Set your search keywords on the home page first.")
        return redirect(url_for("home"))

    location = profile.get("search_location") or None
    raw_results = jobsearch.search_ausbildung(
        keywords=profile["search_keywords"], location=location
    )
    results = [jobsearch.simplify_posting(r) for r in raw_results]

    for r in results:
        if r["refnr"]:
            LAST_RESULTS[r["refnr"]] = r

    return render_template("results.html", results=results)


@app.route("/draft/<refnr>", methods=["GET", "POST"])
def draft(refnr):
    profile = load_profile()
    posting = LAST_RESULTS.get(refnr)
    if not posting:
        flash("This posting is no longer in memory - please search again.")
        return redirect(url_for("search"))

    letter_text = coverletter.build_cover_letter(profile, posting)

    if request.method == "POST":
        # allow manual edits to the letter before building the PDF/draft
        letter_text = request.form.get("letter_text", letter_text)

        output_pdf = os.path.join(OUTPUT_DIR, f"Bewerbung_{posting['company']}_{refnr}.pdf")
        pdfmerge.merge_application_pdf(
            cover_letter_text=letter_text,
            cv_path=profile.get("cv_path"),
            diploma_path=profile.get("diploma_path"),
            translations_paths=profile.get("translations_paths", []),
            output_path=output_pdf,
        )

        to_email = request.form.get("to_email", "")
        subject = f"Bewerbung um einen Ausbildungsplatz als {posting['title']}"
        body_short = (
            f"Sehr geehrte Damen und Herren,\n\nanbei meine Bewerbungsunterlagen "
            f"fuer die Ausbildung als {posting['title']}.\n\n"
            f"Mit freundlichen Gruessen\n{profile.get('your_name','')}"
        )

        try:
            gmail_client.create_draft(to_email, subject, body_short, output_pdf)
            flash(f"Draft created in Gmail for {posting['company']} - check your Drafts folder.")
        except FileNotFoundError as e:
            flash(str(e))
        return redirect(url_for("search"))

    return render_template("draft.html", posting=posting, letter_text=letter_text)


if __name__ == "__main__":
    app.run(debug=True, port=5050)
