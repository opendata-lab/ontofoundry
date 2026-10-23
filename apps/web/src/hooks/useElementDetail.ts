import { useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { elementHref, type ElementRequest } from "../lib/elementInspector";
import { useWorkspaceContext } from "./useWorkspaceContext";

/** Links to an element's detail page; a request without a session keeps the page's own. */
export function useElementDetail() {
  const { workspace } = useWorkspaceContext();
  const location = useLocation();
  const navigate = useNavigate();
  const sessionId = new URLSearchParams(location.search).get("session");
  const href = useCallback((request: ElementRequest) =>
    elementHref(workspace.id, {
      ...request,
      sessionId: request.sessionId === undefined ? sessionId : request.sessionId,
    }), [workspace.id, sessionId]);
  const open = useCallback((request: ElementRequest) => void navigate(href(request)), [navigate, href]);
  return { href, open };
}
