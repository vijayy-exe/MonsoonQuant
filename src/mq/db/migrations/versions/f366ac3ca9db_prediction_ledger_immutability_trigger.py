"""prediction ledger immutability trigger

Revision ID: f366ac3ca9db
Revises: 75438be4a0ce
Create Date: 2026-10-04 12:54:14.653515

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f366ac3ca9db"
down_revision: str | Sequence[str] | None = "75438be4a0ce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    SPEC §2.1: prediction_ledger is append-only. Enforce it in the database,
    not application discipline, so no code path can ever rewrite history.
    """
    op.execute(
        """
        CREATE FUNCTION mq_prediction_ledger_block_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'prediction_ledger is append-only: % not permitted (row id=%)',
                TG_OP, OLD.id;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER mq_prediction_ledger_no_update
        BEFORE UPDATE ON prediction_ledger
        FOR EACH ROW EXECUTE FUNCTION mq_prediction_ledger_block_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER mq_prediction_ledger_no_delete
        BEFORE DELETE ON prediction_ledger
        FOR EACH ROW EXECUTE FUNCTION mq_prediction_ledger_block_mutation();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS mq_prediction_ledger_no_delete ON prediction_ledger;")
    op.execute("DROP TRIGGER IF EXISTS mq_prediction_ledger_no_update ON prediction_ledger;")
    op.execute("DROP FUNCTION IF EXISTS mq_prediction_ledger_block_mutation();")
