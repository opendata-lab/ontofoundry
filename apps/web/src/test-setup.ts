import { transferableAbortController } from "node:util";
import "@ant-design/v5-patch-for-react-19";
import "@testing-library/jest-dom/vitest";

// Browser APIs Ant Design relies on that jsdom does not implement.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}
if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
window.scrollTo = () => {};
Element.prototype.scrollIntoView ??= function scrollIntoView() {};
// jsdom rejects the pseudo-element argument antd passes when measuring.
const computedStyle = window.getComputedStyle.bind(window);
window.getComputedStyle = (element: Element) => computedStyle(element);

// React Router uses Node's Request implementation. Pair it with Node's abort
// primitives; jsdom's signal belongs to a different realm and fails validation.
const nativeController = transferableAbortController();
Object.assign(globalThis, {
  AbortController: nativeController.constructor,
  AbortSignal: nativeController.signal.constructor,
});
