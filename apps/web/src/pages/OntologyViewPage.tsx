import { Download, Upload, Rocket } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, modelingApi, workspaceRequest } from "../api/client";
import type { Draft, LegacyDraft, WorkspaceOverview } from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import type { SelectedGraphItem } from "../components/OntologyGraph";
import { SemanticView } from "../components/SemanticView";
import { editorDraft } from "../lib/nativeDraft";
import { useElementInspector } from "../hooks/useElementInspector";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { EmptyModel } from "../components/EmptyModel";
import { OntologyOverview } from "../components/OntologyOverview";
import { OssieImportDialog } from "../components/OssieImportDialog";

export function OntologyViewPage() {
  const { workspace } = useWorkspaceContext();
  const [overview, setOverview] = useState<WorkspaceOverview | null>(null);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"global" | "semantic">("global");
  const [attempt, setAttempt] = useState(0);
  const [model, setModel] = useState<LegacyDraft | null>(null);
  const [resourceError, setResourceError] = useState("");
  const inspector = useElementInspector();
  const inspect = (selected: SelectedGraphItem) => {
    if (selected?.category === "node" && selected.item.kind === "object_type")
      inspector.open({
        kind: "object_type",
        id: selected.item.id,
        tab: "basic",
        sessionId: null,
      });
    else if (
      selected?.category === "node" &&
      selected.item.kind === "link_type"
    )
      inspector.open({
        kind: "link_type",
        id: selected.item.id,
        tab: "basic",
        sessionId: null,
      });
    else if (selected?.category === "edge" && selected.item.kind === "role")
      inspector.open({
        kind: "link_type",
        id: selected.item.link_type_id ?? selected.item.source,
        tab: "basic",
        sessionId: null,
      });
    else if (
      selected?.category === "edge" &&
      selected.item.kind === "link_type"
    )
      inspector.open({
        kind: "link_type",
        id: selected.item.id,
        tab: "basic",
        sessionId: null,
      });
  };
  const [importing, setImporting] = useState(false);
  const load = () => setAttempt((value) => value + 1);
  const switchMode = (value: "global" | "semantic") => {
    setMode(value);
  };
  useEffect(() => {
    let active = true;
    setError("");
    setOverview(null);
    if (!workspace.current_version) return;
    api
      .overview(workspace.id)
      .then((value) => {
        if (active) setOverview(value);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [workspace.id, workspace.current_version, attempt]);
  // Accepted proposals live in a session until someone publishes it. Point at
  // the most recent session whose draft moved away from its base version, so
  // its changes do not look lost. Best effort: the hint never blocks the view.
  const [draftSession, setDraftSession] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setDraftSession(null);
    if (!workspace.role) return;
    modelingApi
      .sessions(workspace.id)
      .then(({ items }) => {
        if (active)
          setDraftSession(
            items.find((item) => item.has_unpublished_changes)?.id ?? null,
          );
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [workspace.id, workspace.role, workspace.current_version]);
  const graph = overview?.graph;
  useEffect(() => {
    let live = true;
    setModel(null);
    setResourceError("");
    if (!overview) return;
    workspaceRequest<{ model: Draft }>(
      workspace.id,
      `/versions/${overview.version.version_id}/presentation`,
    )
      .then((result) => {
        if (live) setModel(editorDraft(result.model));
      })
      .catch(() => {
        if (live) setResourceError("规则读取失败，请重新打开本体视图。");
      });
    return () => {
      live = false;
    };
  }, [workspace.id, overview]);
  if (error) return <ErrorSurface message={error} retry={load} />;
  if (workspace.current_version && !overview)
    return <LoadingSurface label="正在读取本体图谱…" />;
  const objects = graph?.nodes.filter((n) => n.kind === "object_type") ?? [];
  return (
    <div className="ref-view">
      <div className="view-tabs-bar">
        <div
          className="view-mode-pills"
          role="tablist"
          aria-label="本体视图模式"
          onKeyDown={(e) => {
            if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key))
              return;
            e.preventDefault();
            const next =
              e.key === "Home"
                ? "global"
                : e.key === "End"
                  ? "semantic"
                  : mode === "global"
                    ? "semantic"
                    : "global";
            switchMode(next);
            e.currentTarget
              .querySelector<HTMLButtonElement>("#view-tab-" + next)
              ?.focus();
          }}
        >
          <button
            role="tab"
            id="view-tab-global"
            aria-controls="ontology-view-panel"
            tabIndex={mode === "global" ? 0 : -1}
            aria-selected={mode === "global"}
            onClick={() => switchMode("global")}
          >
            全局
          </button>
          <button
            role="tab"
            id="view-tab-semantic"
            aria-controls="ontology-view-panel"
            tabIndex={mode === "semantic" ? 0 : -1}
            aria-selected={mode === "semantic"}
            onClick={() => switchMode("semantic")}
          >
            语义视图
          </button>
        </div>
        <div className="view-row-actions">
          {workspace.role && (
            <>
              <Link className="view-tool view-tool--primary" to="../delivery">
                <Rocket size={15} />
                发布
              </Link>
              <button className="view-tool" onClick={() => setImporting(true)}>
                <Upload size={15} />
                导入
              </button>
            </>
          )}
          {overview && (
            <a
              className="view-tool"
              href={api.exportUrl(workspace.id, overview.version.version_id)}
              download
            >
              <Download size={15} />
              导出
            </a>
          )}
        </div>
        <span className="muted">
          {overview ? "v" + overview.version.version + " · 已发布" : "尚未发布"}
          {draftSession && (
            <>
              {" · "}
              <Link to={"../delivery?session=" + draftSession}>
                有未发布的草稿修改 · 去发布
              </Link>
            </>
          )}
        </span>
      </div>
      <div
        className="view-canvas"
        id="ontology-view-panel"
        role="tabpanel"
        aria-labelledby={"view-tab-" + mode}
      >
        {overview && objects.length && mode === "global" ? (
          <OntologyOverview
            overview={overview}
            onSemantic={() => switchMode("semantic")}
            onSelect={inspect}
          />
        ) : graph?.nodes.length && mode === "semantic" ? (
          <SemanticView
            graph={graph}
            model={model}
            resourceError={resourceError}
            onOpen={inspector.open}
          />
        ) : (
          <div className="view-empty">
            <EmptyModel
              text={
                graph?.nodes.length
                  ? "没有匹配的本体"
                  : "工作空间还没有已发布本体"
              }
            />
            {workspace.role && (
              <Link className="button button--primary" to="../builder">
                开始建模
              </Link>
            )}
          </div>
        )}
      </div>
      {importing && (
        <OssieImportDialog
          workspaceId={workspace.id}
          onClose={(imported) => {
            setImporting(false);
            if (imported) load();
          }}
        />
      )}
    </div>
  );
}
