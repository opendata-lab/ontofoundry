import { lazy } from "react";
import { Navigate, Route, Routes, useSearchParams } from "react-router-dom";
import { usePageActive } from "../hooks/usePageTab";
import { pageLoaders } from "../lib/workspacePages";
import { ElementInspector } from "./elements/ElementInspector";
import { LegacyElementRoute } from "./elements/LegacyElementRoute";
const BuilderPage = lazy(() =>
  pageLoaders.BuilderPage().then((module) => ({
    default: module.BuilderPage,
  })),
);
const OntologyViewPage = lazy(() =>
  pageLoaders.OntologyViewPage().then((module) => ({
    default: module.OntologyViewPage,
  })),
);
const TypeCatalogPage = lazy(() =>
  pageLoaders.TypeCatalogPage().then((module) => ({
    default: module.TypeCatalogPage,
  })),
);
const ConnectionsPage = lazy(() =>
  pageLoaders.ConnectionsPage().then((module) => ({
    default: module.ConnectionsPage,
  })),
);
const MappingsPage = lazy(() =>
  pageLoaders.MappingsPage().then((module) => ({
    default: module.MappingsPage,
  })),
);
const InstancesPage = lazy(() =>
  pageLoaders.InstancesPage().then((module) => ({
    default: module.InstancesPage,
  })),
);
const DeliveryPage = lazy(() =>
  pageLoaders.DeliveryPage().then((module) => ({
    default: module.DeliveryPage,
  })),
);
const SettingsPage = lazy(() =>
  pageLoaders.SettingsPage().then((module) => ({
    default: module.SettingsPage,
  })),
);

function RelationCatalogRedirect() {
  const [params] = useSearchParams();
  const active = usePageActive();
  if (!active) return null;
  const next = new URLSearchParams(params);
  next.set("catalogTab", "relations");
  return <Navigate to={{ pathname: "../objects", search: `?${next}` }} replace />;
}

// Freeze each mounted page's route params and query string while another tab is active.
export function WorkspaceRoutes({ href }: { href: string }) {
  return (
    <><Routes location={href}>
      <Route index element={<Navigate to="view" replace />} />
      <Route path="view" element={<OntologyViewPage />} />
      <Route path="objects" element={<TypeCatalogPage kind="object_type" />} />
      <Route path="objects/:typeId" element={<LegacyElementRoute />} />
      <Route path="objects/:typeId/edit" element={<LegacyElementRoute editing />} />
      <Route path="objects/:typeId/instances" element={<InstancesPage />} />
      <Route
        path="objects/:typeId/instances/:objectId"
        element={<InstancesPage />}
      />
      <Route path="relations" element={<RelationCatalogRedirect />} />
      <Route path="relations/:typeId" element={<LegacyElementRoute relation />} />
      <Route
        path="relations/:typeId/edit"
        element={<LegacyElementRoute relation editing />}
      />
      <Route path="builder" element={<BuilderPage />} />
      <Route path="connections" element={<ConnectionsPage />} />
      <Route path="mappings" element={<MappingsPage />} />
      <Route path="delivery" element={<DeliveryPage />} />
      <Route path="settings" element={<SettingsPage />} />

      <Route path="*" element={<Navigate to="../view" replace />} />
    </Routes><ElementInspector /></>
  );
}
