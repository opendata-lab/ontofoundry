import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, modelingApi } from "../api/client";
import type { Draft, WorkspaceOverview } from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { PageBody, PageHeader, Panel, PanelToolbar, StatusMark } from "../components/layout";
import { EmptyModel } from "../components/EmptyModel";
import { SemanticView } from "../components/SemanticView";
import { useElementInspector } from "../hooks/useElementInspector";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { ONTOLOGY_SAVED, type OntologySaved } from "../lib/elementInspector";

export function OntologyViewPage() {
  const { workspace } = useWorkspaceContext();
  const [overview, setOverview] = useState<WorkspaceOverview | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [model, setModel] = useState<Draft | null>(null);
  const [resourceError, setResourceError] = useState("");
  const [draftSession, setDraftSession] = useState<string | null>(null);
  const inspector = useElementInspector();
  const load = () => setAttempt((value) => value + 1);
  useEffect(() => {
    let active = true;
    setError("");
    setOverview(null);
    if (!workspace.current_version) return;
    api
      .overview(workspace.id)
      .then((value) => active && setOverview(value))
      .catch((e: Error) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [workspace.id, workspace.current_version, attempt]);
  // Element saves publish right away; reread so new metrics and datasets show up.
  useEffect(() => {
    const saved = (event: Event) => {
      if ((event as CustomEvent<OntologySaved>).detail.workspaceId === workspace.id) load();
    };
    window.addEventListener(ONTOLOGY_SAVED, saved);
    return () => window.removeEventListener(ONTOLOGY_SAVED, saved);
  }, [workspace.id]);
  // Accepted proposals live in a session until someone publishes it. Point at
  // the most recent session whose draft moved away from its base version, so
  // its changes do not look lost. Best effort: the hint never blocks the view.
  useEffect(() => {
    let active = true;
    setDraftSession(null);
    if (!workspace.role) return;
    modelingApi
      .sessions(workspace.id)
      .then(({ items }) => active && setDraftSession(items.find((item) => item.has_unpublished_changes)?.id ?? null))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [workspace.id, workspace.role, workspace.current_version]);
  useEffect(() => {
    let live = true;
    setModel(null);
    setResourceError("");
    const version = overview?.version;
    if (!version) return;
    (workspace.role ? modelingApi.snapshot(workspace.id) : api.presentation(workspace.id, version.version_id).then((r) => r.model))
      .then((result) => live && setModel(result))
      .catch(() => live && setResourceError("指标和数据集读取失败，请重新打开本体视图。"));
    return () => {
      live = false;
    };
  }, [workspace.id, workspace.role, overview]);
  if (error) return <ErrorSurface message={error} retry={load} />;
  if (workspace.current_version && !overview) return <LoadingSurface label="正在读取本体图谱…" />;
  const graph = overview?.graph;
  const version = overview?.version;
  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <PageHeader
        title="本体视图"
        note={<StatusMark state={version ? "mapped" : "unmapped"} label={version ? `v${version.version} · 已发布` : "尚未发布"} />}
      />
      <PageBody>
        <Panel fill>
          {draftSession && <PanelToolbar><Link to={"../delivery?session=" + draftSession}>有未发布的草稿修改 · 去发布</Link></PanelToolbar>}
          <div className="min-h-0 flex-1">
            {graph ? <SemanticView graph={graph} model={model} onOpen={inspector.open} resourceError={resourceError} canCreate={!!workspace.role} /> : <EmptyModel text="工作空间还没有已发布本体" />}
          </div>
        </Panel>
      </PageBody>
    </div>
  );
}
