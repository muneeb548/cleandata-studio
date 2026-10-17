import { forwardRef, type HTMLAttributes, type InputHTMLAttributes, type LabelHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const field =
  "h-9 w-full rounded-md border border-border-strong bg-background px-3 text-body text-foreground shadow-xs placeholder:text-slate-500 focus-visible:border-primary focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-primary/30 disabled:cursor-not-allowed disabled:bg-muted";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
  <input ref={ref} className={cn(field, className)} {...props} />
));
Input.displayName = "Input";

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <div className="relative">
      <select ref={ref} className={cn(field, "appearance-none pr-8", className)} {...props}>
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute top-1/2 right-2.5 size-4 -translate-y-1/2 text-slate-500" aria-hidden="true" />
    </div>
  ),
);
Select.displayName = "Select";

export function Label({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-small font-medium text-slate-700", className)} {...props} />;
}

export function FieldHint({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-caption text-muted-foreground", className)} {...props} />;
}

type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { label: ReactNode; description?: ReactNode };

export function Checkbox({ label, description, className, id, ...props }: CheckboxProps) {
  return (
    <label htmlFor={id} className={cn("flex cursor-pointer items-start gap-2.5 text-body", className)}>
      <input id={id} type="checkbox" className="mt-0.5 size-4 shrink-0 cursor-pointer rounded border-border-strong accent-primary" {...props} />
      <span>
        <span className="font-medium text-foreground">{label}</span>
        {description && <span className="block text-caption text-muted-foreground">{description}</span>}
      </span>
    </label>
  );
}

type RadioCardProps = {
  name: string;
  value: string;
  checked: boolean;
  onChange: (value: string) => void;
  label: ReactNode;
  description?: ReactNode;
};

export function RadioCard({ name, value, checked, onChange, label, description }: RadioCardProps) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-2.5 rounded-md border px-3 py-2.5 text-body transition-colors",
        checked ? "border-primary bg-primary-soft" : "border-border hover:bg-muted",
      )}
    >
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={() => onChange(value)}
        className="mt-0.5 size-4 shrink-0 accent-primary"
      />
      <span>
        <span className="font-medium text-foreground">{label}</span>
        {description && <span className="block text-caption text-muted-foreground">{description}</span>}
      </span>
    </label>
  );
}
