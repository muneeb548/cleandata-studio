import { Database } from "lucide-react";
import { Link } from "@/lib/router";
import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <span className={cn("relative inline-flex size-7 items-center justify-center rounded-md bg-primary text-white", className)}>
      <Database className="size-4" strokeWidth={2.2} aria-hidden="true" />
      <span className="absolute -right-0.5 -bottom-0.5 size-2.5 rounded-full border-2 border-white bg-emerald-500" aria-hidden="true" />
    </span>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <Link href="/" className={cn("inline-flex items-center gap-2 rounded-md", className)} aria-label="CleanData Studio home">
      <LogoMark />
      <span className="text-h3 font-semibold tracking-tight text-foreground">
        CleanData<span className="font-medium text-primary"> Studio</span>
      </span>
    </Link>
  );
}
