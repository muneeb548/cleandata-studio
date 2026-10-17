import { useEffect, useId, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { Button } from "./button";
import { cn } from "@/lib/utils";

type DialogProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  className?: string;
};

/**
 * Accessible modal built on the native <dialog> element: the browser handles
 * focus trapping, Escape to close and the inert background.
 */
export function Dialog({ open, onClose, title, description, children, footer, className }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descId = useId();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal?.();
    if (!open && el.open) el.close?.();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={description ? descId : undefined}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose(); // click on backdrop
      }}
      className={cn(
        "m-auto w-[calc(100%-2rem)] max-w-md rounded-lg border border-border bg-background p-0 text-foreground shadow-raised",
        className,
      )}
    >
      {open && (
        <div className="flex flex-col">
          <div className="flex items-start justify-between gap-4 px-5 pt-5">
            <div>
              <h2 id={titleId} className="text-h3 font-semibold">
                {title}
              </h2>
              {description && (
                <div id={descId} className="mt-1 text-body text-muted-foreground">
                  {description}
                </div>
              )}
            </div>
            <Button variant="ghost" size="icon" className="-mt-1 -mr-2 size-8" onClick={onClose} aria-label="Close dialog">
              <X />
            </Button>
          </div>
          {children && <div className="px-5 pt-4">{children}</div>}
          <div className="mt-5 flex flex-col-reverse gap-2 border-t border-border bg-canvas px-5 py-3 sm:flex-row sm:justify-end">
            {footer}
          </div>
        </div>
      )}
    </dialog>
  );
}
