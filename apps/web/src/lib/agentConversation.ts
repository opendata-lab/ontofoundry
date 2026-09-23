import {
  createHttpTransport,
  type ConversationTransport,
} from "@opendataworks/agent-conversation";

function fileUrl(endpoint: string, relPath: string): string {
  const base = endpoint.replace(/\/$/, "");
  const path = relPath
    .replace(/^\/+/, "")
    .split("/")
    .map(encodeURIComponent)
    .join("/");
  return `${base}/files/${path}`;
}

/**
 * OntoFoundry implements the SDK's core BFF protocol plus authenticated file
 * reads. The latter is added explicitly so history attachments can be
 * previewed and downloaded through fetch instead of a bare navigation.
 * Unsupported optional capabilities stay absent and therefore stay hidden.
 */
export function createOntoFoundryConversationTransport(
  endpoint: string,
): ConversationTransport {
  const transport = createHttpTransport(endpoint);
  return {
    ...transport,
    async readFile(relPath: string) {
      const response = await fetch(fileUrl(endpoint, relPath), {
        credentials: "same-origin",
      });
      if (!response.ok) {
        throw new Error(`附件读取失败（HTTP ${response.status}）`);
      }
      return response.blob();
    },
  };
}
