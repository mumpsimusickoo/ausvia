"""Production WSGI entrypoint (Procfile: gunicorn wsgi:app).

Deliberately a separate file from app.py, not just an alias for it: this
project has both an app.py *file* and an app/ *package* in the same
directory, so a plain `import app` (what any WSGI server's "module:object"
target string does - gunicorn, uwsgi, waitress, etc.) resolves to the app/
package (app/__init__.py, which only exposes create_app) rather than
app.py. flask run/flask CLI auto-discovery never hit this because it loads
app.py by file path, not through normal package import - but `gunicorn
app:app` fails outright with "module 'app' has no attribute 'app'". A
distinctly-named entrypoint sidesteps the collision rather than relying on
every future WSGI server invocation getting the ambiguity right.
"""
from app import create_app

app = create_app()
