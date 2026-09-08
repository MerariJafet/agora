"""Reconcile early local Institutional Validator pilot schemas.

Revision ID: 0035_validator_reconcile
Revises: 0034_institutional_validators

An early local deployment applied a development draft of revision 0034 before
the profile and signed-review fields were finalized. This additive migration
repairs that legitimate historical state and is also safe after the final 0034.
"""

from __future__ import annotations

from alembic import op

revision = "0035_validator_reconcile"
down_revision = "0034_institutional_validators"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE institutional_validators
          ADD COLUMN IF NOT EXISTS legal_entity_id varchar(160),
          ADD COLUMN IF NOT EXISTS domain varchar(253),
          ADD COLUMN IF NOT EXISTS jurisdiction varchar(80),
          ADD COLUMN IF NOT EXISTS institution_mode varchar(32),
          ADD COLUMN IF NOT EXISTS accreditation_status varchar(32),
          ADD COLUMN IF NOT EXISTS public_label varchar(200),
          ADD COLUMN IF NOT EXISTS brain_provider varchar(16),
          ADD COLUMN IF NOT EXISTS review_role varchar(48),
          ADD COLUMN IF NOT EXISTS representative_owner_id varchar(30),
          ADD COLUMN IF NOT EXISTS verified_by_owner_id varchar(30),
          ADD COLUMN IF NOT EXISTS verification_evidence_hash varchar(64),
          ADD COLUMN IF NOT EXISTS activated_at timestamptz;

        UPDATE institutional_validators
        SET legal_entity_id = COALESCE(legal_entity_id, 'TEST-LEGAL-' || validator_id),
            domain = COALESCE(domain, lower(validator_id) || '.example.org'),
            jurisdiction = COALESCE(jurisdiction, 'TEST'),
            institution_mode = COALESCE(institution_mode, 'simulated_test'),
            accreditation_status = COALESCE(accreditation_status, 'NOT_REAL'),
            public_label = COALESCE(public_label, 'Synthetic institution for AGORA testing'),
            brain_provider = COALESCE(
              brain_provider,
              CASE WHEN lower(display_name || ' ' || institution_name) LIKE '%claude%'
                   THEN 'claude' ELSE 'codex' END
            ),
            review_role = COALESCE(
              review_role,
              CASE WHEN lower(display_name || ' ' || institution_name) LIKE '%claude%'
                   THEN 'FALSIFICATION_EVIDENCE' ELSE 'REPRODUCTION_METHODOLOGY' END
            );

        ALTER TABLE institutional_validators
          ALTER COLUMN legal_entity_id SET NOT NULL,
          ALTER COLUMN domain SET NOT NULL,
          ALTER COLUMN jurisdiction SET NOT NULL,
          ALTER COLUMN institution_mode SET NOT NULL,
          ALTER COLUMN accreditation_status SET NOT NULL,
          ALTER COLUMN public_label SET NOT NULL,
          ALTER COLUMN brain_provider SET NOT NULL,
          ALTER COLUMN review_role SET NOT NULL;

        ALTER TABLE validator_assignments
          ADD COLUMN IF NOT EXISTS commitment_signature varchar(128);
        ALTER TABLE validator_reviews
          ADD COLUMN IF NOT EXISTS reproduction_status varchar(64);
        UPDATE validator_reviews
          SET reproduction_status = 'NOT_REPRODUCIBLE_FROM_PROVIDED_ARTIFACTS'
          WHERE reproduction_status IS NULL;
        ALTER TABLE validator_reviews
          ALTER COLUMN reproduction_status SET NOT NULL;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'institutional_validators_legal_entity_id_key'
          ) THEN
            ALTER TABLE institutional_validators
              ADD CONSTRAINT institutional_validators_legal_entity_id_key
              UNIQUE (legal_entity_id);
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'institutional_validators_domain_key'
          ) THEN
            ALTER TABLE institutional_validators
              ADD CONSTRAINT institutional_validators_domain_key UNIQUE (domain);
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'institutional_validators_representative_owner_id_fkey'
          ) THEN
            ALTER TABLE institutional_validators
              ADD CONSTRAINT institutional_validators_representative_owner_id_fkey
              FOREIGN KEY (representative_owner_id) REFERENCES users(user_id);
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'institutional_validators_verified_by_owner_id_fkey'
          ) THEN
            ALTER TABLE institutional_validators
              ADD CONSTRAINT institutional_validators_verified_by_owner_id_fkey
              FOREIGN KEY (verified_by_owner_id) REFERENCES users(user_id);
          END IF;
        END $$;

        ALTER TABLE institutional_validators
          DROP CONSTRAINT IF EXISTS ck_pilot_validator_is_synthetic,
          DROP CONSTRAINT IF EXISTS ck_pilot_validator_brain_provider,
          DROP CONSTRAINT IF EXISTS ck_pilot_validator_review_role;
        ALTER TABLE institutional_validators
          ADD CONSTRAINT ck_pilot_validator_is_synthetic CHECK (
            validator_type = 'INSTITUTIONAL_VALIDATOR_TEST'
            AND synthetic_or_human = 'synthetic'
            AND institution_mode = 'simulated_test'
            AND jurisdiction = 'TEST'
            AND accreditation_status = 'NOT_REAL'
          ),
          ADD CONSTRAINT ck_pilot_validator_brain_provider CHECK (
            brain_provider IN ('codex', 'claude')
          ),
          ADD CONSTRAINT ck_pilot_validator_review_role CHECK (
            review_role IN ('REPRODUCTION_METHODOLOGY', 'FALSIFICATION_EVIDENCE')
          );
        """
    )


def downgrade() -> None:
    # Historical reconciliation is intentionally not destructive. Revision
    # 0034 owns the tables and remains responsible for their full downgrade.
    pass
