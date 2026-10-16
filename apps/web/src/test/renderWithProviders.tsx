import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement } from "react";
import { UiProvider } from "../theme/UiProvider";

/** render() inside the same Ant Design providers the app uses. */
export function renderWithProviders(ui: ReactElement, options?: RenderOptions) {
  return render(ui, { wrapper: UiProvider, ...options });
}
