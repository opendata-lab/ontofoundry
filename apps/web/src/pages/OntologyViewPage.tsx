import {
  Download,
  Search,
  Upload,
  X,
  Plus,
  Rocket,
  Box,
  GitBranch,
  Braces,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { WorkspaceOverview } from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import {
  OntologyGraph,
  type SelectedGraphItem,
} from "../components/OntologyGraph";
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
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState("");
  const [attributes, setAttributes] = useState(false);
  const [selected, setSelected] = useState<SelectedGraphItem>(null);
  const [importing, setImporting] = useState(false);
  const load = () => setAttempt((value) => value + 1);
  const switchMode = (value: "global" | "semantic") => {
    setMode(value);
    setSelected(null);
  };
  useEffect(() => {
    let active = true;
    setError("");
    setOverview(null);
    setSelected(null);
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
  const graph = overview?.graph;
  const visible = useMemo(() => {
    if (!graph) return null;
    const objectIds = new Set(
      graph.nodes
        .filter(
          (n) => n.kind === "object_type" && (!tag || n.tags.includes(tag)),
        )
        .map((n) => n.id),
    );
    const attributeIds = new Set(
      graph.edges
        .filter((e) => e.kind === "attribute" && objectIds.has(e.source))
        .map((e) => e.target),
    );
    const nodes = graph.nodes.filter(
      (n) => objectIds.has(n.id) || (attributes && attributeIds.has(n.id)),
    );
    const ids = new Set(nodes.map((n) => n.id));
    return {
      ...graph,
      nodes,
      edges: graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
    };
  }, [graph, attributes, tag]);
  if (error) return <ErrorSurface message={error} retry={load} />;
  if (workspace.current_version && (!overview || !visible))
    return <LoadingSurface label="正在读取本体图谱…" />;
  const tags = [...new Set(graph?.nodes.flatMap((n) => n.tags) ?? [])];
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
        <span className="muted">
          {overview ? "v" + overview.version.version + " · 已发布" : "尚未发布"}
        </span>
      </div>
      {mode === "semantic" && (
        <div className="view-toolbar">
          <span className="view-kind">实体</span>
          <label className="ref-search">
            <input
              placeholder="请输入检索关键字"
              aria-label="搜索图谱"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <Search size={15} />
          </label>
          <select
            aria-label="图谱标签"
            value={tag}
            onChange={(e) => setTag(e.target.value)}
          >
            <option value="">请选择标签</option>
            {tags.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
          <label className="show-attributes">
            <input
              type="checkbox"
              checked={attributes}
              onChange={(e) => setAttributes(e.target.checked)}
            />
            显示属性
          </label>
          <div className="toolbar-spacer" />
          {workspace.role && (
            <>
              <Link className="view-tool" to="../builder">
                <Plus size={15} />
                <span>构建本体</span>
              </Link>
              <Link className="view-tool" to="../relations">
                <GitBranch size={15} />
                <span>本体关系</span>
              </Link>
              <Link className="view-tool view-tool--primary" to="../delivery">
                <Rocket size={15} />
                <span>发布</span>
              </Link>
            </>
          )}
          {workspace.role && (
            <button className="view-tool" onClick={() => setImporting(true)}>
              <Upload size={15} />
              <span>导入</span>
            </button>
          )}
          {overview && (
            <a
              className="view-tool"
              href={api.exportUrl(workspace.id, overview.version.version_id)}
              download
            >
              <Download size={15} />
              <span>导出</span>
            </a>
          )}
        </div>
      )}
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
            onSelect={setSelected}
          />
        ) : visible?.nodes.length ? (
          <OntologyGraph
            key={String(attributes) + tag}
            graph={visible}
            mode="semantic"
            query={query}
            onSelect={setSelected}
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
        {mode === "semantic" && graph && (
          <div className="view-legend">
            <span>
              <Box size={12} />
              实体 {objects.length}
            </span>
            <span>
              <GitBranch size={12} />
              关系 {graph.edges.filter((e) => e.kind === "link_type").length}
            </span>
            <span>
              <Braces size={12} />
              属性 {graph.nodes.length - objects.length}
            </span>
          </div>
        )}
        {selected && (
          <aside className="view-inspector">
            <header>
              <h2>{selected.item.label}</h2>
              <button
                className="icon-button"
                onClick={() => setSelected(null)}
                aria-label="关闭详情"
              >
                <X size={16} />
              </button>
            </header>
            <code>{selected.item.technical_name}</code>
            <p>{selected.item.description || "尚未填写描述"}</p>
            {selected.category === "node" &&
              selected.item.kind === "object_type" && (
                <>
                  <p>属性：{selected.item.attribute_count ?? 0} 项</p>
                  <Link
                    className="button button--primary"
                    to={"../objects/" + selected.item.id}
                  >
                    打开本体详情
                  </Link>
                </>
              )}
            {selected.category === "edge" &&
              selected.item.kind === "link_type" && (
                <Link
                  className="button button--primary"
                  to={"../relations/" + selected.item.id}
                >
                  打开关系详情
                </Link>
              )}
          </aside>
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
