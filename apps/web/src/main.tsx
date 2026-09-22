import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@xyflow/react/dist/style.css";
import "./styles/tokens.css";
import "./styles/global.css";
import "./styles/reference.css";
import { defineAgentConversation } from "@opendataworks/agent-conversation";
import { App } from "./App";

// Registers <dataagent-conversation>. Without this the browser treats the tag
// as an unknown element and renders an inert empty box — no error, nothing in
// the console, and every build and type check still passes.
defineAgentConversation();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
