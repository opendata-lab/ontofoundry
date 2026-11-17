/** The focused element, looking inside open shadow roots (the conversation is a web component). */
function deepActiveElement(): HTMLElement | null {
  let active: Element | null = document.activeElement;
  while (active?.shadowRoot?.activeElement) active = active.shadowRoot.activeElement;
  return active instanceof HTMLElement ? active : null;
}

function focusWithoutScroll(el: HTMLElement | null) {
  if (!el || typeof el.focus !== "function") return;
  try {
    el.focus({ preventScroll: true });
  } catch {
    el.focus();
  }
}

/**
 * Copy text, also on the plain-HTTP LAN deployment where
 * `navigator.clipboard` does not exist (insecure context).
 */
export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Fall through to the textarea path.
    }
  }
  const active = deepActiveElement();
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.top = "0";
  area.style.left = "0";
  area.style.width = "1px";
  area.style.height = "1px";
  area.style.opacity = "0";
  document.body.appendChild(area);
  let copied = false;
  try {
    focusWithoutScroll(area);
    area.select();
    area.setSelectionRange(0, area.value.length);
    copied = !!document.execCommand?.("copy");
  } finally {
    area.remove();
    focusWithoutScroll(active);
  }
  if (!copied) throw new Error("浏览器不允许复制，请手动选择文本");
}

export function downloadText(filename: string, text: string, type = "text/markdown;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
