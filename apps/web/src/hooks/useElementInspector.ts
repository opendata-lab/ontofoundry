import { createPath, useLocation, useNavigate } from "react-router-dom";
import { inspectorHref, type ElementRequest } from "../lib/elementInspector";

/** URL-backed, independent of an entry point's rendering or data-fetching hooks. */
export function useElementInspector() {
  const location = useLocation();
  const navigate = useNavigate();
  const href = (request: ElementRequest) =>
    inspectorHref(createPath(location), request);
  return {
    href,
    open: (request: ElementRequest) => void navigate(href(request)),
  };
}
