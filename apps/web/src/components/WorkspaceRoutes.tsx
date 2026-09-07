import { lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
const BuilderPage = lazy(() =>
  import("../pages/BuilderPage").then((module) => ({
    default: module.BuilderPage,
  })),
);
const OntologyViewPage = lazy(() =>
  import("../pages/OntologyViewPage").then((module) => ({
    default: module.OntologyViewPage,
  })),
);
const TypeCatalogPage = lazy(() =>
  import("../pages/TypeCatalogPage").then((module) => ({
    default: module.TypeCatalogPage,
  })),
);
const ObjectDetailPage = lazy(() =>
  import("../pages/ObjectDetailPage").then((module) => ({
    default: module.ObjectDetailPage,
  })),
);
const ObjectEditorPage = lazy(() =>
  import("../pages/ObjectEditorPage").then((module) => ({
    default: module.ObjectEditorPage,
  })),
);
const MappingsPage = lazy(() =>
  import("../pages/MappingsPage").then((module) => ({
    default: module.MappingsPage,
  })),
);
const InstancesPage = lazy(() =>
  import("../pages/InstancesPage").then((module) => ({
    default: module.InstancesPage,
  })),
);
const DeliveryPage = lazy(() =>
  import("../pages/DeliveryPage").then((module) => ({
    default: module.DeliveryPage,
  })),
);
const SettingsPage = lazy(() =>
  import("../pages/SettingsPage").then((module) => ({
    default: module.SettingsPage,
  })),
);

// Freeze each mounted page's route params and query string while another tab is active.
export function WorkspaceRoutes({ href }: { href: string }) {
  return (
    <Routes location={href}>
      <Route index element={<Navigate to="view" replace />} />
      <Route path="view" element={<OntologyViewPage />} />
      <Route path="objects" element={<TypeCatalogPage kind="object_type" />} />
      <Route path="objects/:typeId" element={<ObjectDetailPage />} />
      <Route path="objects/:typeId/edit" element={<ObjectEditorPage />} />
      <Route path="objects/:typeId/instances" element={<InstancesPage />} />
      <Route
        path="objects/:typeId/instances/:objectId"
        element={<InstancesPage />}
      />
      <Route path="relations" element={<TypeCatalogPage kind="link_type" />} />
      <Route path="relations/:typeId" element={<ObjectDetailPage relation />} />
      <Route
        path="relations/:typeId/edit"
        element={<ObjectEditorPage relation />}
      />
      <Route path="builder" element={<BuilderPage />} />
      <Route path="mappings" element={<MappingsPage />} />
      <Route path="delivery" element={<DeliveryPage />} />
      <Route path="settings" element={<SettingsPage />} />

      <Route path="*" element={<Navigate to="../view" replace />} />
    </Routes>
  );
}
