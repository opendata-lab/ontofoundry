// Must run before any antd module renders under React 19.
import "@ant-design/v5-patch-for-react-19";
import "./styles/index.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { defineAgentConversation } from "@opendataworks/agent-conversation";
import { App } from "./App";
import { UiProvider } from "./theme/UiProvider";

// Registers <dataagent-conversation>. Without this the browser treats the tag
// as an unknown element and renders an inert empty box — no error, nothing in
// the console, and every build and type check still passes.
defineAgentConversation();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <UiProvider>
      <App />
    </UiProvider>
  </StrictMode>,
);
