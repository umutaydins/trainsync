import { type VariantProps, cva } from "class-variance-authority";
import { Slot } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap font-semibold transition-[background,color,transform,opacity] duration-150 active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-[1.1em] [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-accent text-accent-contrast hover:brightness-95",
        secondary: "bg-surface-2 text-text hover:bg-surface-3",
        outline: "border border-border bg-transparent text-text hover:bg-surface-2",
        ghost: "bg-transparent text-muted hover:bg-surface-2 hover:text-text",
        danger: "bg-bad text-white hover:brightness-95",
      },
      size: {
        sm: "h-9 rounded-control px-3 text-sm",
        md: "h-touch rounded-control px-4 text-sm",
        lg: "h-14 rounded-card px-6 text-base",
        icon: "size-touch rounded-full",
        stepper: "size-16 rounded-card text-2xl",
      },
      block: { true: "w-full" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export type ButtonProps = ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    /** Render the child (e.g. a `Link`) with the button styles instead of a `<button>`. */
    asChild?: boolean;
  };

export function Button({ className, variant, size, block, asChild = false, ...props }: ButtonProps) {
  const Component = asChild ? Slot.Root : "button";
  return (
    <Component
      data-slot="button"
      className={cn(buttonVariants({ variant, size, block }), className)}
      {...props}
    />
  );
}
