import { useCallback, useEffect, useRef, useState } from "react";
import { modelingApi } from "../api/client";
import type { ModelingSession } from "../api/types";
import { ONTOLOGY_SAVED, type OntologySaved } from "../lib/elementInspector";

/**
 * Tracks the user's personal modeling session for unpublished change counts and
 * delivery links from default catalog views.
 */
export function usePersonalSession(workspaceId: string, enabled: boolean, refreshKey: unknown = 0) {
  const [session, setSession] = useState<ModelingSession | null>(null);
  const sessionRef = useRef<ModelingSession | null>(null);
  sessionRef.current = session;
  const requestSeq = useRef(0);

  const load = useCallback(() => {
    const seq = ++requestSeq.current;
    if (!enabled) {
      sessionRef.current = null;
      setSession(null);
      return;
    }
    modelingApi
      .personal(workspaceId)
      .then((next) => {
        if (seq === requestSeq.current) {
          sessionRef.current = next;
          setSession(next);
        }
      })
      .catch(() => undefined);
  }, [workspaceId, enabled]);

  useEffect(() => {
    const seq = requestSeq;
    load();
    return () => {
      seq.current++;
    };
  }, [load, refreshKey]);

  useEffect(() => {
    const saved = (event: Event) => {
      const detail = (event as CustomEvent<OntologySaved>).detail;
      if (detail.workspaceId !== workspaceId) return;
      if (!detail.session) {
        load();
        return;
      }
      const current = sessionRef.current;
      if (!current || detail.session.id === current.id) {
        requestSeq.current++;
        sessionRef.current = detail.session;
        setSession(detail.session);
      }
    };
    window.addEventListener(ONTOLOGY_SAVED, saved);
    return () => window.removeEventListener(ONTOLOGY_SAVED, saved);
  }, [workspaceId, load]);

  return session;
}
