import { ArrowLeft, Compass } from "lucide-react";
import { PageShell } from "@/components/layout/PageShell";
import { buttonVariants } from "@/components/ui/button";
import { Link } from "@/lib/router";
import { usePageMeta } from "@/lib/seo";

export function NotFoundPage() {
  usePageMeta({ title: "Page not found — CleanData Studio", description: "This page does not exist.", path: "/404", index: false });
  return (
    <PageShell>
      <div className="container-page flex flex-col items-center py-24 text-center">
        <span className="flex size-12 items-center justify-center rounded-lg bg-muted text-slate-500">
          <Compass className="size-6" aria-hidden="true" />
        </span>
        <p className="mt-5 text-body font-semibold text-primary">404</p>
        <h1 className="mt-1 text-h1 font-semibold tracking-tight">Page not found</h1>
        <p className="mt-2 max-w-sm text-body text-muted-foreground">The page you are looking for does not exist or has moved.</p>
        <div className="mt-6 flex gap-3">
          <Link href="/" className={buttonVariants({ variant: "secondary" })}>
            <ArrowLeft /> Back to home
          </Link>
          <Link href="/app" className={buttonVariants()}>
            Open workspace
          </Link>
        </div>
      </div>
    </PageShell>
  );
}
