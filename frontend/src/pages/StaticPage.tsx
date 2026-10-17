import type { ReactNode } from "react";
import { PageShell } from "@/components/layout/PageShell";

/** Shared layout for simple content pages (About, Privacy, Contact). */
export function StaticPage({ eyebrow, title, intro, children }: { eyebrow: string; title: string; intro: string; children: ReactNode }) {
  return (
    <PageShell>
      <div className="border-b border-border bg-canvas">
        <div className="container-page max-w-3xl py-12">
          <p className="text-caption font-semibold tracking-wide text-primary uppercase">{eyebrow}</p>
          <h1 className="mt-2 text-h1 font-semibold">{title}</h1>
          <p className="mt-3 text-h3 leading-relaxed text-muted-foreground">{intro}</p>
        </div>
      </div>
      <div className="container-page max-w-3xl py-12">
        <div className="space-y-8 text-body leading-relaxed text-slate-700 [&_h2]:text-h2 [&_h2]:font-semibold [&_h2]:text-foreground [&_li]:ml-5 [&_li]:list-disc [&_ul]:mt-2 [&_ul]:space-y-1.5 [&_p+p]:mt-3">
          {children}
        </div>
      </div>
    </PageShell>
  );
}
