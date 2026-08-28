from flask import Blueprint, render_template, redirect, url_for, flash, current_app, send_file, abort, request
from flask_babel import gettext as _
from flask_login import login_required, current_user

from app.extensions import db
from app.models.document import Document, DOCUMENT_TYPES, DOCUMENT_TYPE_LABELS
from app.documents.storage import UnsupportedFileError, get_storage_provider
from app.documents.extraction import suggest_doc_type
from app.utils.logging import log_event

bp = Blueprint("documents", __name__, url_prefix="/documents")


def _storage():
    return get_storage_provider(current_app.config)


def _owned_document_or_404(doc_id):
    doc = db.get_or_404(Document, doc_id)
    if doc.user_id != current_user.id:
        # Never let a user reach another user's document by guessing/incrementing an ID.
        abort(404)
    return doc


@bp.route("/", methods=["GET"])
@login_required
def list_documents():
    docs = (
        Document.query.filter_by(user_id=current_user.id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    return render_template("documents/list.html", documents=docs, doc_types=DOCUMENT_TYPES)


@bp.route("/upload", methods=["POST"])
@login_required
def upload():
    file = request.files.get("file")
    doc_type = request.form.get("doc_type", "other")
    description = (request.form.get("description") or "").strip()[:500]

    if doc_type not in DOCUMENT_TYPES:
        doc_type = "other"

    if not file or not file.filename:
        flash(_("Please choose a file to upload."), "error")
        return redirect(url_for("documents.list_documents"))

    try:
        stored_filename, storage_path, file_size, mime_type = _storage().upload(
            file, subdir=str(current_user.id)
        )
    except UnsupportedFileError as e:
        flash(str(e), "error")
        log_event("upload", "Rejected upload: invalid file.", level="warning", user_id=current_user.id)
        return redirect(url_for("documents.list_documents"))

    doc = Document(
        user_id=current_user.id,
        doc_type=doc_type,
        original_filename=file.filename[:255],
        stored_filename=stored_filename,
        storage_path=storage_path,
        mime_type=mime_type,
        file_size=file_size,
        description=description or None,
    )

    # Document AI extraction (Phase 6): a heuristic best-guess at the real
    # doc_type from the file's own text, PDF only. Stored as a suggestion
    # only - never applied to doc.doc_type here. See app/documents/extraction.py.
    if mime_type == "application/pdf":
        doc.ai_suggested_doc_type = suggest_doc_type(_storage().full_path(storage_path), doc_type)

    db.session.add(doc)
    db.session.commit()
    log_event("upload", f"Document uploaded (type={doc_type}).", user_id=current_user.id)
    if doc.ai_suggested_doc_type:
        # i18n pass 2: DOCUMENT_TYPE_LABELS (app/models/document.py), not
        # doc_type.replace('_', ' '), which has no German equivalent -
        # same fix as the doc-type displays in applications/detail.html
        # and documents/list.html.
        flash(
            _(
                'Document uploaded. This looks like it might be a "%(suggested)s" rather than '
                '"%(chosen)s" - you can confirm the suggestion below if that\'s right.',
                suggested=DOCUMENT_TYPE_LABELS[doc.ai_suggested_doc_type], chosen=DOCUMENT_TYPE_LABELS[doc_type],
            ),
            "info",
        )
    else:
        flash(_("Document uploaded."), "success")
    return redirect(url_for("documents.list_documents"))


@bp.route("/<int:doc_id>/apply-suggested-type", methods=["POST"])
@login_required
def apply_suggested_type(doc_id):
    doc = _owned_document_or_404(doc_id)
    if doc.ai_suggested_doc_type:
        doc.doc_type = doc.ai_suggested_doc_type
        doc.ai_suggested_doc_type = None
        db.session.commit()
        flash(_("Document type updated."), "success")
    return redirect(url_for("documents.list_documents"))


@bp.route("/<int:doc_id>/dismiss-suggested-type", methods=["POST"])
@login_required
def dismiss_suggested_type(doc_id):
    doc = _owned_document_or_404(doc_id)
    doc.ai_suggested_doc_type = None
    db.session.commit()
    return redirect(url_for("documents.list_documents"))


@bp.route("/<int:doc_id>/download")
@login_required
def download(doc_id):
    doc = _owned_document_or_404(doc_id)
    try:
        abs_path = _storage().full_path(doc.storage_path)
    except FileNotFoundError:
        # Local storage's full_path() never raises here (it only validates
        # the path shape, not that the file exists) - send_file below turns
        # a missing local file into the same 404 on its own. A remote
        # provider has to actually fetch the object to know it's missing,
        # so it raises explicitly instead; this keeps the response identical
        # either way.
        abort(404)
    return send_file(abs_path, download_name=doc.original_filename, as_attachment=True)


@bp.route("/<int:doc_id>/delete", methods=["POST"])
@login_required
def delete(doc_id):
    doc = _owned_document_or_404(doc_id)
    _storage().delete(doc.storage_path)
    db.session.delete(doc)
    db.session.commit()
    log_event("upload", "Document deleted.", user_id=current_user.id)
    flash(_("Document deleted."), "info")
    return redirect(url_for("documents.list_documents"))


@bp.route("/<int:doc_id>/set-primary/<kind>", methods=["POST"])
@login_required
def set_primary(doc_id, kind):
    field_by_kind = {
        "cv": "is_primary_cv",
        "diploma": "is_primary_diploma",
        "german_cert": "is_primary_german_cert",
    }
    field = field_by_kind.get(kind)
    if not field:
        abort(404)

    doc = _owned_document_or_404(doc_id)

    # unset the flag on any other document of this user, then set it here
    Document.query.filter_by(user_id=current_user.id).update({field: False})
    setattr(doc, field, True)
    db.session.commit()
    flash(_("Primary document updated."), "success")
    return redirect(url_for("documents.list_documents"))
