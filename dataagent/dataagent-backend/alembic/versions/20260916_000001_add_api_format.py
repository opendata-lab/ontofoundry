"""Add api_format to da_model_provider and reset legacy provider rows.

Routing used to key off ``provider_id`` and guess it from substrings of the base
URL, so only Anthropic-shaped endpoints were reachable. ``api_format`` records
the wire protocol explicitly.

Existing rows cannot be migrated: ``provider_type`` names a vendor family and
does not imply a request shape — a self-hosted gateway under any vendor label
can serve either protocol — so copying or guessing a value would silently pin
providers to the wrong one. The registry is small and admin-owned, so the rows
are dropped and an explicit reconfiguration is required.

The legacy settings row holds a second copy of the provider fields. Left in
place, settings bootstrap recreates every deleted provider on the next start, so
the provider-related keys are cleared there too. Database, skill and widget
settings in the same row are preserved.
"""
from alembic import op

revision = "20260916_000001"
down_revision = "20260913_000001"
branch_labels = None
depends_on = None


# Provider-owned keys inside da_agent_settings.raw_json. Everything else in that
# blob belongs to other subsystems and must survive.
_LEGACY_PROVIDER_KEYS = (
    "provider_id",
    "model",
    "anthropic_api_key",
    "anthropic_auth_token",
    "anthropic_base_url",
    "provider_settings",
    "providers",
    "validated_provider_id",
    "validated_model",
    "provider_validation_status",
    "provider_validation_message",
    "provider_validated_at",
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE da_model_provider
        ADD COLUMN api_format VARCHAR(64) NOT NULL DEFAULT '/v1/messages'
        """
    )
    op.execute(
        "COMMENT ON COLUMN da_model_provider.api_format IS "
        "'API 格式: /v1/messages 或 /v1/chat/completions'"
    )
    op.execute("DELETE FROM da_model_provider")

    # raw_json is TEXT, not jsonb, so the keys are stripped by casting through
    # jsonb and back. PostgreSQL has no built-in safe JSON parse before 16
    # (pg_input_is_valid), so a scratch function carries the exception handler
    # and is dropped again below. A row holding invalid JSON is left untouched
    # rather than blanked: losing unrelated settings is worse than leaving a
    # stale provider copy the admin is about to overwrite anyway.
    op.execute(
        """
        CREATE FUNCTION pg_temp.odw_strip_keys(raw text, keys text[])
        RETURNS text AS $$
        BEGIN
            RETURN (raw::jsonb - keys)::text;
        EXCEPTION WHEN others THEN
            RETURN raw;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    keys = ", ".join(f"'{key}'" for key in _LEGACY_PROVIDER_KEYS)
    op.execute(
        f"""
        UPDATE da_agent_settings
        SET provider_id = '',
            model_name = '',
            anthropic_api_key = '',
            anthropic_auth_token = '',
            anthropic_base_url = '',
            raw_json = CASE
                WHEN raw_json IS NULL OR btrim(raw_json) = '' THEN raw_json
                ELSE pg_temp.odw_strip_keys(raw_json, ARRAY[{keys}])
            END
        """
    )
    op.execute("DROP FUNCTION pg_temp.odw_strip_keys(text, text[])")


def downgrade() -> None:
    op.execute("ALTER TABLE da_model_provider DROP COLUMN api_format")
