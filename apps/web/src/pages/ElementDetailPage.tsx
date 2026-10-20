import { useContext } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ElementView } from "../components/elements/ElementInspector";
import { PageTabContext } from "../hooks/usePageTab";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { elementHref } from "../lib/elementInspector";

/** One ontology element in its own workspace tab; the address keeps the selected tab. */
export function ElementDetailPage() {
  const { kind = "", id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { workspace } = useWorkspaceContext();
  const close = useContext(PageTabContext)?.close;
  const sessionId = params.get("session");
  const previewHash = params.get("preview");
  return (
    <ElementView
      key={`${kind}:${id}:${sessionId}:${previewHash}`}
      variant="page"
      kind={kind}
      id={id}
      sessionId={sessionId}
      previewHash={previewHash}
      owner={params.get("owner")}
      startEditing={params.get("mode") === "edit"}
      tab={params.get("tab")}
      onTab={(tab) =>
        setParams(
          (current) => {
            const next = new URLSearchParams(current);
            next.set("tab", tab);
            next.delete("mode");
            return next;
          },
          { replace: true },
        )
      }
      onCreated={(request) => void navigate(elementHref(workspace.id, request), { replace: true })}
      onClose={() => close?.()}
    />
  );
}
