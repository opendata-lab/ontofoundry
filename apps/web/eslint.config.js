import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

// Controls come from Ant Design. Files that still render a native <select> or
// <dialog> are listed here until they are migrated; remove a file from the list
// when it moves to Select/Modal/Drawer. New files may not be added.
const legacyNativeControls = [
  "src/components/AppShell.tsx",
  "src/components/DataAssets.tsx",
  "src/components/DataConnections.tsx",
  "src/components/DatasetPicker.tsx",
  "src/components/OssieImportDialog.tsx",
  "src/components/ReleaseReview.tsx",
  "src/components/SemanticModels.tsx",
  "src/components/TableMaterialPicker.tsx",
  "src/components/WorkspaceTabs.tsx",
  "src/components/elements/ElementInspector.tsx",
  "src/components/elements/ElementInstances.tsx",
  "src/components/elements/InspectorDialog.tsx",
  "src/components/elements/MappingWidgets.tsx",
  "src/components/elements/PropertyMappingTable.tsx",
  "src/components/elements/RelationCards.tsx",
  "src/components/proposals/ReviewOverlays.tsx",
  "src/components/publish/PublishPanel.tsx",
  "src/components/semantic/MappingTreeEditor.tsx",
  "src/components/semantic/SemanticObjectForm.tsx",
  "src/pages/InstancesPage.tsx",
  "src/pages/SettingsPage.tsx",
  "src/pages/TypeCatalogPage.tsx",
  "src/pages/WorkspaceDirectoryPage.tsx",
];

export default tseslint.config(
  { ignores: ["dist"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
    },
  },
  {
    files: ["src/**/*.tsx"],
    ignores: ["src/**/*.test.tsx", ...legacyNativeControls],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXOpeningElement[name.name='select']",
          message: "Use Ant Design Select instead of a native <select>.",
        },
        {
          selector: "JSXOpeningElement[name.name='dialog']",
          message: "Use Ant Design Modal or Drawer instead of a native <dialog>.",
        },
      ],
    },
  },
);
