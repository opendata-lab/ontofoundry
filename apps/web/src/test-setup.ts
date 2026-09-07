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
