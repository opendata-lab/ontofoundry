import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "./utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-sm text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-accent text-white hover:bg-[#004fca]",
        outline: "border border-rule bg-surface hover:bg-surface-soft",
        ghost: "hover:bg-surface-soft text-ink-2",
        dashed: "border border-dashed border-rule bg-surface hover:border-accent hover:text-accent",
      },
      size: { md: "h-9 px-3.5", sm: "h-8 px-2.5", icon: "h-9 w-9" },
    },
    defaultVariants: { variant: "outline", size: "md" },
  },
);

export function Button({ className, variant, size, asChild, ...props }: ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
