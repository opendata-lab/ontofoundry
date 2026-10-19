import type { ReactNode } from "react";

/** Keeps related form fields together and stacks them in narrow containers. */
export function FormRow({ children }: { children: ReactNode }) {
  return <div className="form-row">{children}</div>;
}
