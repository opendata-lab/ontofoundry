"""Retire old sessions on both databases without touching published business data."""
import hashlib
import importlib
from copy import deepcopy
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, select
from test_modeling import ROOT, create_session, publish
from test_t2_pinned_context import call as run_call
from test_t4_proposal_decisions import chain, decide, seed_batch

from ontofoundry_api.db_models import (
    ConnectionRecord,
    ModelingSessionRecord,
    OntologyVersionRecord,
    ProposalBatchRecord,
    ProposalDecisionItemRecord,
    ProposalDecisionRequestRecord,
    ProposalItemDependencyRecord,
    ProposalItemRecord,
    ServiceTokenRecord,
    ServiceTokenScopeRecord,
    WorkspaceRecord,
    utc_now,
)
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.run_credentials import RunGrant, issue

cleanup = importlib.import_module('ontofoundry_api.alembic.versions.20261009_000001_discard_legacy_sessions')
previous = importlib.import_module('ontofoundry_api.alembic.versions.20261008_000001_session_v3_cutover')
USER = '00000000-0000-0000-0000-000000000001'


@pytest.fixture(params=['client', 'pg_client'])
def cleanup_client(request):
    return request.getfixturevalue(request.param)


def old_dependencies(db, session):
    scope = dict(workspace_id=session.workspace_id, session_id=session.id)
    batch_id, first, second, request = [str(uuid4()) for _ in range(4)]
    db.add(ProposalBatchRecord(id=batch_id, **scope, run_token=uuid4().hex, schema_version='ontofoundry.proposals/v1',
           base_version_sha256='a'*64, source_session_revision=1, source_draft_sha256='b'*64,
           result_sha256='c'*64, status='available'))
    db.flush()
    for ordinal, item_id in enumerate((first, second)):
        db.add(ProposalItemRecord(id=item_id, batch_id=batch_id, **scope, ordinal=ordinal,
               fingerprint=str(ordinal)*64, operation='create', target_kind='mapping', target_id=str(uuid4()),
               after_json={}, status='pending'))
    db.add(ProposalDecisionRequestRecord(id=request, **scope, idempotency_key=uuid4().hex,
           request_sha256='d'*64, expected_session_revision=0, result_session_revision=1,
           response_json={}, actor_id=USER))
    db.flush()
    db.add(ProposalItemDependencyRecord(**scope, batch_id=batch_id, item_id=second, depends_on_item_id=first))
    db.add(ProposalDecisionItemRecord(**scope, request_id=request, batch_id=batch_id, item_id=first, decision='reject'))


def test_cleanup_discards_non_v3_and_dependencies_but_preserves_all_business_data(cleanup_client):
    client = cleanup_client
    material = client.post(ROOT + '/materials?name=kept.md', content='保留材料\n'.encode()).json()
    new_session = create_session(client)
    batch = seed_batch(client, new_session, chain(new_session))
    obsolete = []
    snapshots = [dict(schema_version='2'), dict(schema_version='1'), {},
                 dict(schema_version=None), dict(schema_version=3), []]
    with client.app.state.session_factory() as db:
        original_versions = {v.id: (deepcopy(v.snapshot_json), deepcopy(v.ossie_json), v.sha256)
                             for v in db.scalars(select(OntologyVersionRecord))}
        for snapshot in snapshots:
            row = ModelingSessionRecord(id=str(uuid4()), workspace_id=str(DEMO_WORKSPACE_ID),
                  created_by=USER, title='淘汰会话', draft_json=snapshot, draft_sha256='e'*64,
                  base_version_sha256='f'*64, task_status='running', dataagent_run_token='old-run',
                  material_ids=[material['id']], candidates_json=[{'legacy': True}])
            db.add(row)
            db.flush()
            old_dependencies(db, row)
            obsolete.append(row.id)
        connection = ConnectionRecord(id=str(uuid4()), workspace_id=str(DEMO_WORKSPACE_ID), name='保留连接',
                                     kind='postgresql', config_json={}, secret_encrypted='kept-secret')
        token = ServiceTokenRecord(id=str(uuid4()), workspace_id=str(DEMO_WORKSPACE_ID), created_by=USER,
                                  name='保留令牌', token_hash=hashlib.sha256(b'kept-token').hexdigest())
        db.add_all([connection, token])
        db.flush()
        db.add(ServiceTokenScopeRecord(token_id=token.id, scope='ontology:read'))
        db.commit()
    grant = issue(client.app.state.settings.session_secret, RunGrant(str(DEMO_WORKSPACE_ID), obsolete[0],
                  'old-run', new_session['base_version_id'], USER))
    with client.app.state.engine.connect() as conn:
        if conn.dialect.name == 'sqlite':
            conn.exec_driver_sql('PRAGMA foreign_keys=ON')
            conn.commit()
        with conn.begin(), Operations.context(MigrationContext.configure(conn)):
            previous.upgrade()  # recreate the exact schema already deployed in P1
            audit = sa.Table('modeling_session_migrations', sa.MetaData(), autoload_with=conn, resolve_fks=False)
            # A raw insert validates audit FK cleanup without using retired ORM models.
            conn.execute(audit.insert().values(session_id=obsolete[0], source_revision=0,
                workspace_id=str(DEMO_WORKSPACE_ID), source_schema_version='2', source_draft_json={},
                source_draft_sha256='a'*64, candidates_json=[], result_state='processing', migrated_at=utc_now()))
            cleanup.upgrade()
            cleanup.upgrade()  # both row cleanup and optional audit DDL are idempotent
        assert 'modeling_session_migrations' not in inspect(conn).get_table_names()
        assert 'proposal_item_migrations' not in inspect(conn).get_table_names()
    with client.app.state.session_factory() as db:
        assert set(db.scalars(select(ModelingSessionRecord.id))) == {new_session['id']}
        assert {v.id: (v.snapshot_json, v.ossie_json, v.sha256)
                for v in db.scalars(select(OntologyVersionRecord))} == original_versions
        assert set(db.scalars(select(ProposalBatchRecord.id))) == {batch['id']}
        assert {i.id for i in db.scalars(select(ProposalItemRecord))} == {i['id'] for i in batch['items']}
        assert not list(db.scalars(select(ProposalDecisionRequestRecord)))
        assert not list(db.scalars(select(ProposalDecisionItemRecord)))
        assert len(list(db.scalars(select(ProposalItemDependencyRecord)))) == 2
        assert db.get(ConnectionRecord, connection.id).secret_encrypted == 'kept-secret'
        assert db.get(ServiceTokenRecord, token.id).token_hash == token.token_hash
        assert db.get(ServiceTokenScopeRecord, (token.id, 'ontology:read'))
        assert db.get(WorkspaceRecord, str(DEMO_WORKSPACE_ID))
    assert client.get(ROOT + '/materials/' + material['id']).status_code == 200
    assert client.get(ROOT + f'/sessions/{obsolete[0]}').status_code == 404
    assert client.post(ROOT + f"/sessions/{new_session['id']}/migrate-v3", json={'revision': 0}).status_code == 404
    assert run_call(client, grant, 'get_ontology_version').status_code == 401
    accepted = decide(client, new_session, [(i['id'], 'accept') for i in batch['items']])
    assert accepted.status_code == 200, accepted.text
    assert publish(client, accepted.json()['session']).status_code == 200
    with client.app.state.session_factory() as db:
        for version_id, original in original_versions.items():
            old = db.get(OntologyVersionRecord, version_id)
            assert (old.snapshot_json, old.ossie_json, old.sha256) == original
    assert snapshot_sha256(accepted.json()['session']['draft']) == accepted.json()['session']['draft_sha256']


def test_cleanup_new_instance_proposals_publish_and_query(cleanup_client):
    client = cleanup_client
    from test_p1_roles import nary_items
    session = create_session(client)
    batch = seed_batch(client, session, nary_items())
    with client.app.state.engine.begin() as conn:
        assert cleanup.discard_legacy_sessions(conn) == 0
    response = decide(client, session, [(i['id'], 'accept') for i in batch['items']])
    assert response.status_code == 200, response.text
    session = response.json()['session']
    assert publish(client, session).status_code == 200
    alice = next(o for o in session['draft']['material_objects'] if o['name'] == 'Alice')
    response = client.get(f"/api/v1/ontology/workspaces/{DEMO_WORKSPACE_ID}/objects/doc.{alice['id']}/neighborhood")
    assert response.status_code == 200, response.text
    assert len(response.json()['objects']) == 2 and len(response.json()['links']) == 1
