"""Unified PostgreSQL baseline for OntoFoundry and DataAgent.

Revision ID: 20260913_000001
Revises:
Create Date: 2026-09-13 10:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260913_000001"
down_revision = None
branch_labels = None
depends_on = None


DATAAGENT_TABLES = (
    "da_agent_settings",
    "da_skill_document",
    "da_skill_document_version",
    "da_agent_profile",
    "da_agent_topic",
    "da_agent_task",
    "da_agent_message",
    "da_agent_chunk",
    "da_agent_event_record",
    "da_agent_message_queue",
    "da_agent_message_schedule",
    "da_agent_message_schedule_log",
    "da_agent_widget_event",
    "da_model_provider",
    "da_mcp_server",
)


def _drop_retired_tables(schema: str) -> None:
    op.execute(
        f"""
        ALTER TABLE IF EXISTS "{schema}".modeling_sessions
            DROP COLUMN IF EXISTS active_run_id CASCADE;
        ALTER TABLE IF EXISTS "{schema}".workspaces
            DROP COLUMN IF EXISTS agent_engine;

        DROP TABLE IF EXISTS "{schema}".runtime_claims CASCADE;
        DROP TABLE IF EXISTS "{schema}".run_results CASCADE;
        DROP TABLE IF EXISTS "{schema}".run_calls CASCADE;
        DROP TABLE IF EXISTS "{schema}".run_events CASCADE;
        DROP TABLE IF EXISTS "{schema}".agent_runs CASCADE;
        DROP TABLE IF EXISTS "{schema}".runtime_workers CASCADE;

        DROP TABLE IF EXISTS "{schema}".eval_run_case CASCADE;
        DROP TABLE IF EXISTS "{schema}".eval_run CASCADE;
        DROP TABLE IF EXISTS "{schema}".eval_case CASCADE;
        DROP TABLE IF EXISTS "{schema}".eval_dataset CASCADE;
        """
    )


def _merge_legacy_dataagent_schema() -> None:
    connection = op.get_bind()
    op.execute(
        """
        DROP TABLE IF EXISTS dataagent.eval_run_case CASCADE;
        DROP TABLE IF EXISTS dataagent.eval_run CASCADE;
        DROP TABLE IF EXISTS dataagent.eval_case CASCADE;
        DROP TABLE IF EXISTS dataagent.eval_dataset CASCADE;
        """
    )
    for table in DATAAGENT_TABLES:
        old_table = connection.scalar(
            sa.text("SELECT to_regclass(:name)"), {"name": f"dataagent.{table}"}
        )
        if old_table is None:
            continue
        public_table = connection.scalar(
            sa.text("SELECT to_regclass(:name)"), {"name": f"public.{table}"}
        )
        if public_table is not None:
            raise RuntimeError(
                f"cannot merge dataagent.{table}: public.{table} already exists"
            )
        op.execute(f'ALTER TABLE dataagent."{table}" SET SCHEMA public')

    op.execute("DROP TABLE IF EXISTS dataagent.alembic_version")
    # Deliberately omit CASCADE: an unknown table in the old schema must stop the
    # migration instead of being deleted silently.
    op.execute("DROP SCHEMA IF EXISTS dataagent")


def _create_platform_tables() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(36) PRIMARY KEY,
            subject VARCHAR(255) NOT NULL UNIQUE,
            display_name VARCHAR(120) NOT NULL,
            email VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_users_subject ON users(subject);

        CREATE TABLE IF NOT EXISTS workspaces (
            id VARCHAR(36) PRIMARY KEY,
            slug VARCHAR(80) NOT NULL UNIQUE,
            name VARCHAR(120) NOT NULL UNIQUE,
            description TEXT NOT NULL,
            created_by VARCHAR(36) NOT NULL REFERENCES users(id),
            current_version_id VARCHAR(36),
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_workspaces_slug ON workspaces(slug);
        CREATE INDEX IF NOT EXISTS ix_workspaces_created_by ON workspaces(created_by);

        CREATE TABLE IF NOT EXISTS workspace_members (
            id SERIAL PRIMARY KEY,
            workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id),
            user_id VARCHAR(36) NOT NULL REFERENCES users(id),
            role VARCHAR(20) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (workspace_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS ix_workspace_members_workspace_id
            ON workspace_members(workspace_id);
        CREATE INDEX IF NOT EXISTS ix_workspace_members_user_id
            ON workspace_members(user_id);

        CREATE TABLE IF NOT EXISTS ontology_versions (
            id VARCHAR(36) PRIMARY KEY,
            workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id),
            version_number INTEGER NOT NULL,
            status VARCHAR(20) NOT NULL,
            message VARCHAR(240) NOT NULL,
            snapshot_json JSONB NOT NULL,
            ossie_json JSONB NOT NULL,
            validation_json JSONB NOT NULL,
            sha256 VARCHAR(64) NOT NULL,
            published_by VARCHAR(36) NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (workspace_id, version_number)
        );
        CREATE INDEX IF NOT EXISTS ix_ontology_versions_workspace_id
            ON ontology_versions(workspace_id);
        CREATE INDEX IF NOT EXISTS ix_ontology_versions_sha256 ON ontology_versions(sha256);

        CREATE TABLE IF NOT EXISTS modeling_sessions (
            id VARCHAR(36) PRIMARY KEY,
            workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id),
            created_by VARCHAR(36) NOT NULL REFERENCES users(id),
            title VARCHAR(240) NOT NULL,
            base_version_id VARCHAR(36),
            revision INTEGER NOT NULL,
            draft_json JSONB NOT NULL,
            candidates_json JSONB NOT NULL,
            messages_json JSONB NOT NULL,
            material_ids JSONB NOT NULL,
            task_status VARCHAR(24) NOT NULL,
            task_detail TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_modeling_sessions_workspace_id
            ON modeling_sessions(workspace_id);

        CREATE TABLE IF NOT EXISTS materials (
            id VARCHAR(36) PRIMARY KEY,
            workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id),
            name VARCHAR(240) NOT NULL,
            sha256 VARCHAR(64) NOT NULL,
            byte_size INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (workspace_id, sha256)
        );
        CREATE INDEX IF NOT EXISTS ix_materials_workspace_id ON materials(workspace_id);

        CREATE TABLE IF NOT EXISTS material_chunks (
            id SERIAL PRIMARY KEY,
            material_id VARCHAR(36) NOT NULL REFERENCES materials(id),
            ordinal INTEGER NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            text TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_material_chunks_material_id
            ON material_chunks(material_id);

        CREATE TABLE IF NOT EXISTS data_connections (
            id VARCHAR(36) PRIMARY KEY,
            workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id),
            name VARCHAR(120) NOT NULL,
            kind VARCHAR(16) NOT NULL,
            config_json JSONB NOT NULL,
            secret_encrypted TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_data_connections_workspace_id
            ON data_connections(workspace_id);

        CREATE TABLE IF NOT EXISTS service_tokens (
            id VARCHAR(36) PRIMARY KEY,
            workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id),
            created_by VARCHAR(36) NOT NULL REFERENCES users(id),
            name VARCHAR(120) NOT NULL,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL
        );

        CREATE TABLE IF NOT EXISTS service_token_scopes (
            token_id VARCHAR(36) NOT NULL REFERENCES service_tokens(id),
            scope VARCHAR(40) NOT NULL,
            PRIMARY KEY (token_id, scope)
        );

        CREATE TABLE IF NOT EXISTS metadata_snapshots (
            connection_id VARCHAR(36) NOT NULL REFERENCES data_connections(id),
            schema_name VARCHAR(240) NOT NULL,
            snapshot_json JSONB NOT NULL,
            changes_json JSONB NOT NULL,
            observed_at TIMESTAMPTZ,
            error TEXT,
            PRIMARY KEY (connection_id, schema_name)
        );
        """
    )


def upgrade() -> None:
    connection = op.get_bind()
    schema = connection.scalar(sa.text("SELECT current_schema()"))
    _drop_retired_tables(schema)
    if schema == "public":
        _merge_legacy_dataagent_schema()
    _create_platform_tables()

    present = {
        table
        for table in DATAAGENT_TABLES
        if connection.scalar(
            sa.text("SELECT to_regclass(:name)"), {"name": f"{schema}.{table}"}
        )
        is not None
    }
    if present and present != set(DATAAGENT_TABLES):
        missing = ", ".join(sorted(set(DATAAGENT_TABLES) - present))
        raise RuntimeError(f"incomplete DataAgent schema; missing tables: {missing}")
    if present:
        return

    op.execute(
        """
        CREATE TABLE da_agent_settings (
            settings_key VARCHAR(32) PRIMARY KEY,
            provider_id VARCHAR(64) NOT NULL DEFAULT '',
            model_name VARCHAR(255) NOT NULL DEFAULT '',
            anthropic_api_key VARCHAR(512),
            anthropic_auth_token VARCHAR(512),
            anthropic_base_url VARCHAR(512),
            skills_output_dir VARCHAR(512),
            raw_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE da_skill_document (
            id BIGSERIAL PRIMARY KEY,
            relative_path VARCHAR(255) NOT NULL UNIQUE,
            file_name VARCHAR(128) NOT NULL,
            category VARCHAR(64) NOT NULL,
            content_type VARCHAR(32) NOT NULL,
            current_content TEXT NOT NULL,
            current_hash CHAR(64) NOT NULL,
            current_version_id BIGINT,
            version_count INTEGER NOT NULL DEFAULT 0,
            last_change_source VARCHAR(32) NOT NULL DEFAULT 'import',
            last_change_summary VARCHAR(255),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_skill_document_category ON da_skill_document(category);
        CREATE INDEX idx_skill_document_updated ON da_skill_document(updated_at);

        CREATE TABLE da_skill_document_version (
            id BIGSERIAL PRIMARY KEY,
            document_id BIGINT NOT NULL REFERENCES da_skill_document(id) ON DELETE CASCADE,
            version_no INTEGER NOT NULL,
            change_source VARCHAR(32) NOT NULL,
            change_summary VARCHAR(255),
            actor VARCHAR(64),
            content TEXT NOT NULL,
            content_hash CHAR(64) NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT,
            parent_version_id BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uk_skill_doc_version UNIQUE (document_id, version_no)
        );
        CREATE INDEX idx_skill_doc_version_created
            ON da_skill_document_version(document_id, created_at);

        CREATE TABLE da_agent_profile (
            agent_id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            description TEXT NOT NULL,
            system_prompt TEXT NOT NULL,
            allowed_tools_json TEXT NOT NULL,
            mcp_server_ids_json TEXT NOT NULL,
            skill_folders_json TEXT NOT NULL,
            max_turns INTEGER NOT NULL DEFAULT 0,
            env_vars_json TEXT NOT NULL,
            is_default SMALLINT NOT NULL DEFAULT 0,
            is_builtin SMALLINT NOT NULL DEFAULT 0,
            data_scope_json TEXT,
            preset_questions_json TEXT,
            visibility_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_da_agent_profile_default_updated
            ON da_agent_profile(is_default, updated_at);

        CREATE TABLE da_agent_topic (
            topic_id VARCHAR(64) PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            chat_topic_id VARCHAR(64) NOT NULL UNIQUE,
            chat_conversation_id VARCHAR(64) NOT NULL,
            current_task_id VARCHAR(64),
            current_task_status VARCHAR(32),
            last_message_seq BIGINT NOT NULL DEFAULT 0,
            source VARCHAR(32) NOT NULL DEFAULT 'portal',
            website_id VARCHAR(128) NOT NULL DEFAULT '',
            external_user_id VARCHAR(255) NOT NULL DEFAULT '',
            visitor_id VARCHAR(128) NOT NULL DEFAULT '',
            auth_user_id VARCHAR(255) NOT NULL DEFAULT '',
            auth_username VARCHAR(255) NOT NULL DEFAULT '',
            agent_id VARCHAR(64) NOT NULL DEFAULT 'agent_ontofoundry',
            agent_snapshot_json TEXT,
            permission_mode VARCHAR(32) NOT NULL DEFAULT 'default',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_da_agent_topic_updated ON da_agent_topic(updated_at);
        CREATE INDEX idx_da_agent_topic_current_task ON da_agent_topic(current_task_id);
        CREATE INDEX idx_da_agent_topic_context_updated
            ON da_agent_topic(source, website_id, external_user_id, visitor_id, updated_at);
        CREATE INDEX idx_da_agent_topic_auth_updated
            ON da_agent_topic(source, auth_user_id, updated_at);
        CREATE INDEX idx_da_agent_topic_agent_updated ON da_agent_topic(agent_id, updated_at);

        CREATE TABLE da_agent_task (
            task_id VARCHAR(64) PRIMARY KEY,
            topic_id VARCHAR(64) NOT NULL REFERENCES da_agent_topic(topic_id) ON DELETE CASCADE,
            from_task_id VARCHAR(64),
            source_queue_id VARCHAR(64),
            source_schedule_id VARCHAR(64),
            source_schedule_log_id VARCHAR(64),
            task_status VARCHAR(32) NOT NULL DEFAULT 'waiting',
            prompt TEXT NOT NULL,
            provider_id VARCHAR(64) NOT NULL,
            model_name VARCHAR(255) NOT NULL,
            database_hint VARCHAR(255),
            debug_enabled SMALLINT NOT NULL DEFAULT 0,
            timeout_seconds INTEGER NOT NULL DEFAULT 0,
            sql_read_timeout_seconds INTEGER NOT NULL DEFAULT 0,
            sql_write_timeout_seconds INTEGER NOT NULL DEFAULT 0,
            last_event_seq BIGINT NOT NULL DEFAULT 0,
            cancel_requested_at TIMESTAMP,
            started_at TIMESTAMP,
            heartbeat_at TIMESTAMP,
            finished_at TIMESTAMP,
            error_json TEXT,
            agent_id VARCHAR(64) NOT NULL DEFAULT 'agent_ontofoundry',
            agent_snapshot_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_da_agent_task_topic_created ON da_agent_task(topic_id, created_at);
        CREATE INDEX idx_da_agent_task_status_updated ON da_agent_task(task_status, updated_at);
        CREATE INDEX idx_da_agent_task_parent ON da_agent_task(from_task_id);
        CREATE INDEX idx_da_agent_task_source_queue ON da_agent_task(source_queue_id);
        CREATE INDEX idx_da_agent_task_source_schedule ON da_agent_task(source_schedule_id);
        CREATE INDEX idx_da_agent_task_source_schedule_log ON da_agent_task(source_schedule_log_id);
        CREATE INDEX idx_da_agent_task_agent_created ON da_agent_task(agent_id, created_at);

        CREATE TABLE da_agent_message (
            message_id VARCHAR(64) PRIMARY KEY,
            topic_id VARCHAR(64) NOT NULL REFERENCES da_agent_topic(topic_id) ON DELETE CASCADE,
            task_id VARCHAR(64) REFERENCES da_agent_task(task_id) ON DELETE CASCADE,
            sender_type VARCHAR(16) NOT NULL,
            type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'success',
            content TEXT NOT NULL,
            event VARCHAR(64) NOT NULL DEFAULT '',
            steps_json TEXT,
            tool_json TEXT,
            seq_id BIGINT NOT NULL DEFAULT 0,
            correlation_id VARCHAR(128),
            parent_correlation_id VARCHAR(128),
            content_type VARCHAR(64),
            usage_json TEXT,
            error_json TEXT,
            show_in_ui SMALLINT NOT NULL DEFAULT 1,
            feedback VARCHAR(16) NOT NULL DEFAULT '',
            attachments_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_da_agent_message_topic_seq
            ON da_agent_message(topic_id, show_in_ui, seq_id);
        CREATE INDEX idx_da_agent_message_task_seq
            ON da_agent_message(task_id, show_in_ui, seq_id);
        CREATE INDEX idx_da_agent_message_task_ui
            ON da_agent_message(task_id, sender_type, show_in_ui);
        CREATE INDEX idx_da_agent_message_correlation ON da_agent_message(correlation_id);

        CREATE TABLE da_agent_chunk (
            id BIGSERIAL PRIMARY KEY,
            topic_id VARCHAR(64) NOT NULL REFERENCES da_agent_topic(topic_id) ON DELETE CASCADE,
            task_id VARCHAR(64) NOT NULL REFERENCES da_agent_task(task_id) ON DELETE CASCADE,
            seq_id BIGINT NOT NULL DEFAULT 0,
            request_id VARCHAR(128) NOT NULL,
            chunk_id BIGINT NOT NULL,
            content TEXT,
            delta_status VARCHAR(16) NOT NULL,
            finish_reason VARCHAR(64),
            delta_extra_json TEXT,
            correlation_id VARCHAR(128),
            parent_correlation_id VARCHAR(128),
            model_id VARCHAR(255),
            content_type VARCHAR(64),
            metadata_extra_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_da_agent_chunk_task_seq ON da_agent_chunk(task_id, seq_id);
        CREATE INDEX idx_da_agent_chunk_topic_seq ON da_agent_chunk(topic_id, seq_id);
        CREATE INDEX idx_da_agent_chunk_correlation ON da_agent_chunk(correlation_id);

        CREATE TABLE da_agent_event_record (
            id BIGSERIAL PRIMARY KEY,
            topic_id VARCHAR(64) NOT NULL,
            task_id VARCHAR(64) NOT NULL,
            turn_index SMALLINT NOT NULL DEFAULT 0,
            record_type VARCHAR(32) NOT NULL,
            event_type VARCHAR(64),
            data JSONB NOT NULL,
            contract_version SMALLINT,
            engine_kind VARCHAR(32),
            event_id VARCHAR(64),
            run_id VARCHAR(64),
            task_attempt_id VARCHAR(64),
            engine_sequence BIGINT,
            occurred_at TIMESTAMP(3),
            created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_agent_event_task_id ON da_agent_event_record(task_id, id);
        CREATE INDEX idx_da_agent_event_record_event_id
            ON da_agent_event_record(task_id, event_id);

        CREATE TABLE da_agent_message_queue (
            queue_id VARCHAR(64) PRIMARY KEY,
            topic_id VARCHAR(64) NOT NULL REFERENCES da_agent_topic(topic_id) ON DELETE CASCADE,
            source_schedule_id VARCHAR(64),
            source_schedule_log_id VARCHAR(64),
            message_type VARCHAR(64) NOT NULL,
            message_content_json TEXT NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'queued',
            last_task_id VARCHAR(64),
            error_message TEXT,
            consumed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_da_agent_message_queue_topic_created
            ON da_agent_message_queue(topic_id, created_at);
        CREATE INDEX idx_da_agent_message_queue_status_updated
            ON da_agent_message_queue(status, updated_at);
        CREATE INDEX idx_da_agent_message_queue_last_task ON da_agent_message_queue(last_task_id);
        CREATE INDEX idx_da_agent_message_queue_source_schedule
            ON da_agent_message_queue(source_schedule_id);

        CREATE TABLE da_agent_message_schedule (
            schedule_id VARCHAR(64) PRIMARY KEY,
            topic_id VARCHAR(64) NOT NULL REFERENCES da_agent_topic(topic_id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            message_type VARCHAR(64) NOT NULL,
            message_content_json TEXT NOT NULL,
            cron_expr VARCHAR(128) NOT NULL,
            timezone VARCHAR(64) NOT NULL,
            enabled SMALLINT NOT NULL DEFAULT 1,
            last_task_id VARCHAR(64),
            last_queue_id VARCHAR(64),
            last_run_at TIMESTAMP,
            next_run_at TIMESTAMP,
            last_error_message TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_da_agent_message_schedule_topic_updated
            ON da_agent_message_schedule(topic_id, updated_at);
        CREATE INDEX idx_da_agent_message_schedule_enabled_next
            ON da_agent_message_schedule(enabled, next_run_at);

        CREATE TABLE da_agent_message_schedule_log (
            schedule_log_id VARCHAR(64) PRIMARY KEY,
            schedule_id VARCHAR(64) NOT NULL
                REFERENCES da_agent_message_schedule(schedule_id) ON DELETE CASCADE,
            queue_id VARCHAR(64),
            task_id VARCHAR(64),
            status VARCHAR(32) NOT NULL DEFAULT 'running',
            error_message TEXT,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_da_agent_message_schedule_log_schedule_created
            ON da_agent_message_schedule_log(schedule_id, created_at);
        CREATE INDEX idx_da_agent_message_schedule_log_task
            ON da_agent_message_schedule_log(task_id);

        CREATE TABLE da_agent_widget_event (
            id BIGSERIAL PRIMARY KEY,
            event_type VARCHAR(64) NOT NULL,
            source VARCHAR(32) NOT NULL DEFAULT 'portal',
            website_id VARCHAR(128) NOT NULL DEFAULT '',
            external_user_id VARCHAR(255) NOT NULL DEFAULT '',
            visitor_id VARCHAR(128) NOT NULL DEFAULT '',
            agent_id VARCHAR(64) NOT NULL DEFAULT '',
            topic_id VARCHAR(64),
            task_id VARCHAR(64),
            message_id VARCHAR(64),
            payload_json JSONB,
            client_ts TIMESTAMP(3),
            created_at TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_widget_event_context
            ON da_agent_widget_event(source, website_id, external_user_id, visitor_id, created_at);
        CREATE INDEX idx_widget_event_type ON da_agent_widget_event(event_type, created_at);
        CREATE INDEX idx_widget_event_topic ON da_agent_widget_event(topic_id);

        CREATE TABLE da_model_provider (
            provider_id VARCHAR(64) PRIMARY KEY,
            provider_type VARCHAR(32) NOT NULL,
            display_name VARCHAR(128) NOT NULL,
            provider_group VARCHAR(64) NOT NULL DEFAULT '',
            base_url VARCHAR(512) NOT NULL DEFAULT '',
            api_key VARCHAR(512) NOT NULL DEFAULT '',
            auth_token VARCHAR(512) NOT NULL DEFAULT '',
            provider_enabled SMALLINT NOT NULL DEFAULT 0,
            supports_partial_messages SMALLINT NOT NULL DEFAULT 1,
            enabled_models_json TEXT NOT NULL,
            custom_models_json TEXT NOT NULL,
            models_json TEXT NOT NULL,
            model_detections_json TEXT NOT NULL,
            validation_status VARCHAR(32) NOT NULL DEFAULT 'unverified',
            validation_message VARCHAR(512) NOT NULL DEFAULT '',
            validated_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_da_model_provider_enabled
            ON da_model_provider(provider_enabled, updated_at);

        CREATE TABLE da_mcp_server (
            server_id VARCHAR(128) PRIMARY KEY,
            name VARCHAR(128) NOT NULL UNIQUE,
            source VARCHAR(32) NOT NULL,
            transport VARCHAR(16) NOT NULL,
            url VARCHAR(1024) NOT NULL DEFAULT '',
            headers_json TEXT NOT NULL,
            command_name VARCHAR(512) NOT NULL DEFAULT '',
            args_json TEXT NOT NULL,
            env_json TEXT NOT NULL,
            enabled SMALLINT NOT NULL DEFAULT 1,
            oauth_required SMALLINT NOT NULL DEFAULT 0,
            tool_count INTEGER NOT NULL DEFAULT 0,
            description VARCHAR(512) NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_da_mcp_server_source_enabled ON da_mcp_server(source, enabled);

        """
    )


def downgrade() -> None:
    for table in (
        "da_mcp_server",
        "da_model_provider",
        "da_agent_widget_event",
        "da_agent_message_schedule_log",
        "da_agent_message_schedule",
        "da_agent_message_queue",
        "da_agent_event_record",
        "da_agent_chunk",
        "da_agent_message",
        "da_agent_task",
        "da_agent_topic",
        "da_agent_profile",
        "da_skill_document_version",
        "da_skill_document",
        "da_agent_settings",
        "metadata_snapshots",
        "service_token_scopes",
        "service_tokens",
        "data_connections",
        "material_chunks",
        "materials",
        "modeling_sessions",
        "ontology_versions",
        "workspace_members",
        "workspaces",
        "users",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
