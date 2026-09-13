import { transferableAbortController } from "node:util";
import "@testing-library/jest-dom/vitest";

// jsdom ships no <dialog> behaviour; give it the open/close semantics the app
// relies on so dialog components can be tested like any other markup.
const dialog = window.HTMLDialogElement?.prototype;
if (dialog && !dialog.showModal) {
  dialog.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
  dialog.show = function show(this: HTMLDialogElement) {
    this.open = true;
  };
  dialog.close = function close(this: HTMLDialogElement) {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
}

// React Router uses Node's Request implementation. Pair it with Node's abort
// primitives; jsdom's signal belongs to a different realm and fails validation.
const nativeController = transferableAbortController();
Object.assign(globalThis, {
  AbortController: nativeController.constructor,
  AbortSignal: nativeController.signal.constructor,
});
