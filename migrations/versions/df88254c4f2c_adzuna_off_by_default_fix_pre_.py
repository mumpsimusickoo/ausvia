"""adzuna off-by-default fix: pre-existing job_source_settings row

Revision ID: df88254c4f2c
Revises: faa3774fd6ec
Create Date: 2026-08-30 06:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'df88254c4f2c'
down_revision = 'faa3774fd6ec'
branch_labels = None
depends_on = None


def upgrade():
    # Data-only correction, not a schema change - see
    # app/jobs/adapters/manager.py's SEED_DISABLED_SOURCES docstring for
    # the full story. Every job_source_settings row, including "adzuna",
    # was seeded is_enabled=True by ensure_source_settings_seeded()'s old
    # blanket default. For Adzuna specifically that meant the moment real
    # ADZUNA_APP_ID/ADZUNA_APP_KEY credentials existed in config, it went
    # live for real user search traffic with no deliberate admin action -
    # unlike Jooble, which was already carefully admin-gated. This flips
    # any existing "adzuna" row back to disabled, once. An admin can
    # still turn it on deliberately via /admin/job-sources exactly as
    # before - this migration only corrects the default it was silently
    # defaulted to, it doesn't remove the ability to enable it. Safe to
    # run even if the row doesn't exist yet (a fresh seed after this pass
    # already defaults it to False, so there's nothing to correct).
    job_source_settings = sa.table(
        "job_source_settings",
        sa.column("source_name", sa.String),
        sa.column("is_enabled", sa.Boolean),
    )
    op.execute(
        job_source_settings.update()
        .where(job_source_settings.c.source_name == "adzuna")
        .values(is_enabled=False)
    )


def downgrade():
    # Deliberately a no-op: there's no way to know whether an admin had
    # manually re-enabled Adzuna between upgrade and downgrade, and
    # restoring is_enabled=True unconditionally would silently recreate
    # the exact bug this migration exists to fix. Re-enable via
    # /admin/job-sources after a downgrade if genuinely needed.
    pass
