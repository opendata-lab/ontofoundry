import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

// Controls come from Ant Design; native <select> and <dialog> are not used.
const nativeControlSelectors = [
  {
    selector: "JSXOpeningElement[name.name='select']",
    message: "Use Ant Design Select instead of a native <select>.",
  },
  {
    selector: "JSXOpeningElement[name.name='dialog']",
    message: "Use Ant Design Modal or Drawer instead of a native <dialog>.",
  },
];

// Visual consistency rules (docs/design/2026-10-17-ui-visual-consistency.md §5.1).
const arbitraryClassSelectors = [
  {
    selector: "JSXAttribute[name.name='className'] Literal[value=/-\\[/]",
    message: "Do not use Tailwind arbitrary values (-[...]) in className; use tokens from styles/tokens.css.",
  },
  {
    selector: "JSXAttribute[name.name='className'] TemplateElement[value.raw=/-\\[/]",
    message: "Do not use Tailwind arbitrary values (-[...]) in className; use tokens from styles/tokens.css.",
  },
];

const importantClassSelectors = [
  {
    selector: "JSXAttribute[name.name='className'] Literal[value=/(?:^|[\\s:])![a-z-]/i]",
    message: "Do not use Tailwind '!' important overrides in className; configure tokens or theme instead.",
  },
  {
    selector: "JSXAttribute[name.name='className'] TemplateElement[value.raw=/(?:^|[\\s:])![a-z-]/i]",
    message: "Do not use Tailwind '!' important overrides in className; configure tokens or theme instead.",
  },
];

const inlineStyleSelector = {
  selector: "JSXAttribute[name.name='style']",
  message: "Do not use inline JSX style attributes; use layout components and Tailwind token classes.",
};

const colorLiteralSelectors = [
  {
    selector: "Literal[value=/#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})\\b|(?:rgba?|hsla?)\\(/i]",
    message: "Do not hardcode color literals in component files; define colors in styles/tokens.css.",
  },
  {
    selector: "TemplateElement[value.raw=/#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})\\b|(?:rgba?|hsla?)\\(/i]",
    message: "Do not hardcode color literals in component files; define colors in styles/tokens.css.",
  },
];

const tagColorSelector = {
  selector: "JSXOpeningElement[name.name='Tag'] > JSXAttribute[name.name='color']",
  message: "Do not pass color to Tag for status display; use StatusMark instead.",
};

const visualConsistencySelectors = [
  ...arbitraryClassSelectors,
  ...importantClassSelectors,
  inlineStyleSelector,
  ...colorLiteralSelectors,
  tagColorSelector,
];

export default tseslint.config(
  { ignores: ["dist", "playwright-report", "test-results"] },
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
    ignores: ["src/**/*.test.tsx"],
    rules: {
      "no-restricted-syntax": [
        "error",
        ...nativeControlSelectors,
        ...visualConsistencySelectors,
      ],
    },
  },
  // Migrated U0–U5 files enforce all visual consistency rules as errors.
  {
    files: [
      "src/pages/BuilderPage.tsx",
      "src/components/BuilderConversationEmpty.tsx",
      "src/components/SessionPicker.tsx",
      "src/components/TableMaterialPicker.tsx",
      "src/pages/OntologyViewPage.tsx",
      "src/components/OntologyOverview.tsx",
      "src/components/Markdown.tsx",
      "src/pages/InstancesPage.tsx",
      "src/pages/MappingsPage.tsx",
      "src/pages/TypeCatalogPage.tsx",
      "src/pages/ConnectionsPage.tsx",
      "src/components/DataConnections.tsx",
      "src/pages/SettingsPage.tsx",
      "src/pages/WorkspaceDirectoryPage.tsx",
      "src/pages/DeliveryPage.tsx",
      "src/components/AppShell.tsx",
      "src/components/WorkspaceTabs.tsx",
      "src/components/Brand.tsx",
      "src/components/AsyncState.tsx",
      "src/components/TagList.tsx",

      "src/components/publish/PublishPanel.tsx",
      "src/components/publish/ConflictResolver.tsx",
      "src/components/ReleaseReview.tsx",
      "src/components/proposals/ProposalPanel.tsx",
      "src/components/proposals/ProposalCard.tsx",
      "src/components/proposals/ProposalDetail.tsx",
      "src/components/proposals/EvidencePopover.tsx",
      "src/components/ModelResults.tsx",
      "src/components/DatasetPicker.tsx",
      "src/components/elements/ElementInspector.tsx",
      "src/components/elements/ElementPanels.tsx",
      "src/components/elements/PropertyMappingTable.tsx",
      "src/components/elements/RelationMappingTable.tsx",
      "src/components/elements/LinkMappingPanel.tsx",
      "src/components/elements/ObjectTablePicker.tsx",
      "src/components/elements/DatasetPanel.tsx",
      "src/components/elements/MetricPanel.tsx",
      "src/components/elements/MetricForm.tsx",
      "src/components/elements/MetricPreview.tsx",
      "src/components/elements/DerivedConditionEditor.tsx",
      "src/components/elements/ElementInstances.tsx",
      "src/components/elements/MappingWidgets.tsx",
      "src/components/PageHeader.tsx",
      "src/components/layout/**/*.tsx",
    ],
    ignores: ["src/**/*.test.tsx"],
    rules: {
      "no-restricted-syntax": [
        "error",
        ...nativeControlSelectors,
        ...visualConsistencySelectors,
      ],
    },
  },
  // Design §7: only canvas coordinates and dimensions may use JSX style.
  {
    files: [
      "src/components/OntologyGraph.tsx",
      "src/components/elements/ObjectRelationGraph.tsx",
      "src/components/SemanticView.tsx",
    ],
    rules: {
      "no-restricted-syntax": [
        "error",
        ...nativeControlSelectors,
        ...arbitraryClassSelectors,
        ...importantClassSelectors,
        ...colorLiteralSelectors,
        tagColorSelector,
      ],
    },
  },
);
