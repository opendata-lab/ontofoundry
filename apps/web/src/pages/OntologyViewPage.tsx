import { Button, Segmented, Typography } from "antd";
import { Rocket } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, modelingApi } from "../api/client";
import type { Draft, WorkspaceOverview } from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { EmptyModel } from "../components/EmptyModel";
import type { SelectedGraphItem } from "../components/OntologyGraph";
import { OntologyOverview } from "../components/OntologyOverview";
import { SemanticView } from "../components/SemanticView";
import { useElementInspector } from "../hooks/useElementInspector";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { ONTOLOGY_SAVED, type OntologySaved } from "../lib/elementInspector";

const { Text } = Typography;

export function OntologyViewPage() {
  const { workspace } = useWorkspaceContext();
  const [overview, setOverview] = useState<WorkspaceOverview | null>(null);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"global" | "semantic">("global");
  const [attempt, setAttempt] = useState(0);
  const [model, setModel] = useState<Draft | null>(null);
  const [resourceError, setResourceError] = useState("");
  const [draftSession, setDraftSession] = useState<string | null>(null);
  const inspector = useElementInspector();
  const load = () => setAttempt((value) => value + 1);
  const inspect = (selected: SelectedGraphItem) => {
    if (selected?.category === "node") inspector.open({ kind: "object_type", id: selected.item.id, sessionId: null });
    else if (selected?.category === "edge" && selected.item.kind === "link_type")
      inspector.open({ kind: "link_type", id: selected.item.link_type_id ?? selected.item.id, sessionId: null });
  };
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
    (workspace.role
      ? modelingApi.snapshot(workspace.id)
      : api.presentation(workspace.id, version.version_id).then((r) => r.model)
    )
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
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-rule bg-surface px-4 py-2">
        <Segmented
          aria-label="本体视图模式"
          value={mode}
          onChange={(value) => setMode(value as typeof mode)}
          options={[
            { value: "global", label: "全局" },
            { value: "semantic", label: "语义视图" },
          ]}
        />
        {workspace.role && (
          <Link to="../delivery">
            <Button type="primary" size="small" icon={<Rocket size={14} />}>
              发布
            </Button>
          </Link>
        )}
        <Text type="secondary" className="ml-auto text-sm">
          {version ? `v${version.version} · 已发布` : "尚未发布"}
          {draftSession && (
            <>
              {" · "}
              <Link to={"../delivery?session=" + draftSession}>有未发布的草稿修改 · 去发布</Link>
            </>
          )}
        </Text>
      </div>
      <div className="relative min-h-0 flex-1" role="tabpanel" aria-label={mode === "global" ? "全局" : "语义视图"}>
        {overview && graph?.nodes.length && mode === "global" ? (
          <OntologyOverview overview={overview} onSemantic={() => setMode("semantic")} onSelect={inspect} />
        ) : graph && (graph.nodes.length || model?.metrics.length || model?.datasets.length) && mode === "semantic" ? (
          <SemanticView
            graph={graph}
            model={model}
            resourceError={resourceError}
            canCreate={!!workspace.role}
            onOpen={inspector.open}
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-4">
            <EmptyModel text={graph?.nodes.length ? "没有匹配的本体" : "工作空间还没有已发布本体"} />
            {workspace.role && (
              <Link to="../builder">
                <Button type="primary">开始建模</Button>
              </Link>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
