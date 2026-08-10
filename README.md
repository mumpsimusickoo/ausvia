# Ausbildung Finder

A local web app that:
1. Searches Ausbildung (apprenticeship) postings from the Bundesagentur für Arbeit's public API
2. Generates a customized cover letter per posting
3. Merges it with your CV + diploma + translated papers into one PDF
4. Creates a **Gmail draft** with that PDF attached — it never sends automatically

## 1. Install

```bash
cd ausbildung-finder
python3 -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Set up Gmail access (one-time, ~5 minutes)

Google requires this to come from your own account — I can't do it for you.

1. Go to https://console.cloud.google.com/ and create a new project (any name).
2. Go to **APIs & Services → Library**, search "Gmail API", click **Enable**.
3. Go to **APIs & Services → OAuth consent screen**. Choose **External**, fill in
   the required fields (app name, your email). Add yourself as a **test user**.
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
   Choose application type **Desktop app**. Create it, then click **Download JSON**.
5. Rename the downloaded file to `credentials.json` and put it in this project
   folder (same folder as `app.py`).

The first time you create a draft, a browser tab will open asking you to log in
and approve access — this creates `token.json` so you won't need to repeat it.
The app only requests the `gmail.compose` permission, which lets it create
drafts but **cannot send email or read your inbox**.

## 3. Run it

```bash
python app.py
```

Open http://127.0.0.1:5050 in your browser.

## 4. Use it

1. **Profile & Setup** tab: fill in your details, upload your CV, diploma, and
   translated papers (all PDF), set your search keywords and location.
2. **Search & Draft** tab: see matched postings, click into one, review/edit
   the generated cover letter, enter the company's application email, and
   click "Build PDF & create Gmail draft".
3. Open Gmail → Drafts, review the attached PDF and text, and hit Send yourself.

## Notes / things worth knowing

- The job search API field names (`titel`, `arbeitgeber`, etc.) are based on
  the current public Jobsuche API. If results ever come back empty/broken,
  it likely means the API changed slightly — open `jobsearch.py`, add a
  `print(data)` in `search_ausbildung()` to see the raw response, and adjust
  the field names.
- Company application emails aren't always in the API response — you'll often
  need to check the posting on arbeitsagentur.de or the company site and paste
  the email in manually. A future improvement could scrape it automatically.
- The cover letter template in `coverletter.py` is a solid generic starting
  point — edit `DEFAULT_TEMPLATE` to sound more like you.
- Everything (profile, uploaded files, generated PDFs) stays local on your
  machine in the `uploads/` and `generated/` folders.
