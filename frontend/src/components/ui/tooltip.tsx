import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type TooltipProps = {
  content: ReactNode;
  children: ReactElement<{ "aria-describedby"?: string }>;
  side?: "top" | "bottom";
  align?: "center" | "start" | "end";
  className?: string;
};

/**
 * Lightweight tooltip shown on hover and keyboard focus. The text is linked to
 * the trigger with aria-describedby, so screen readers announce it too.
 * Works for disabled buttons because the wrapper, not the button, receives hover.
 */
export function Tooltip({ content, children, side = "top", align = "center", className }: TooltipProps) {
  const id = useId();
  const trigger = isValidElement(children) ? cloneElement(children, { "aria-describedby": id }) : children;
  return (
    <span className={cn("group/tooltip relative inline-flex", className)}>
      {trigger}
      <span
        id={id}
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-50 w-max max-w-64 rounded-md bg-slate-900 px-2.5 py-1.5 text-caption font-medium text-white opacity-0 shadow-raised transition-opacity duration-150",
          "group-hover/tooltip:opacity-100 group-focus-within/tooltip:opacity-100",
          side === "top" ? "bottom-full mb-2" : "top-full mt-2",
          align === "center" && "left-1/2 -translate-x-1/2",
          align === "start" && "left-0",
          align === "end" && "right-0",
        )}
      >
        {content}
      </span>
    </span>
  );
}
