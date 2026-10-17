import { ArrowRight, Check, Lock, Plus, ServerCog, Timer, UserX } from "lucide-react";
import { AppPreview } from "@/components/landing/AppPreview";
import { PageShell } from "@/components/layout/PageShell";
import { buttonVariants } from "@/components/ui/button";
import { FAQ, FEATURES, OPERATIONS, SITE, STEPS } from "@/content/site";
import { fillLimits, useServerLimits } from "@/lib/limits";
import { Link, useInitialHashScroll } from "@/lib/router";
import { usePageMeta } from "@/lib/seo";
import { cn } from "@/lib/utils";

function SectionHeading({ eyebrow, title, intro, id }: { eyebrow: string; title: string; intro?: string; id: string }) {
  return (
    <div className="max-w-2xl">
      <p className="text-caption font-semibold tracking-wide text-primary uppercase">{eyebrow}</p>
      <h2 id={id} className="mt-2 text-h1 font-semibold text-foreground">
        {title}
      </h2>
      {intro && <p className="mt-3 text-body leading-relaxed text-muted-foreground">{intro}</p>}
    </div>
  );
}

const PRIVACY_POINTS = [
  { icon: ServerCog, title: "Processed on the server", text: "Your data is cleaned in the server's memory. Temporary files used during import and download are deleted right away." },
  { icon: Lock, title: "No AI services or third-party APIs", text: "Your data is never sent to external AI services or other APIs." },
  { icon: Timer, title: "Deleted after inactivity", text: "Sessions are removed after {ttl} without activity, or when you replace the file." },
  { icon: UserX, title: "No account required", text: "No registration. Each session is isolated behind a random private ID." },
];

export function LandingPage() {
  const limits = useServerLimits();
  usePageMeta({
    title: "CleanData Studio — Clean CSV, Excel and JSON Data Without Code",
    description:
      "Upload a CSV, Excel or JSON file, find missing values, duplicates and formatting issues, apply the cleaning steps you choose, and download a cleaner dataset. No sign-up required.",
    path: "/",
  });
  useInitialHashScroll();

  return (
    <PageShell>
      {/* Hero */}
      <section className="border-b border-border bg-gradient-to-b from-canvas to-background" aria-labelledby="hero-title">
        <div className="container-page grid grid-cols-1 items-center gap-12 py-14 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)] lg:py-20">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-border bg-background px-3 py-1 text-caption font-medium text-slate-600">
              <span className="size-1.5 rounded-full bg-success" aria-hidden="true" />
              Free · No sign-up · CSV, Excel, JSON up to {fillLimits("{limit}", limits)}
            </p>
            <h1 id="hero-title" className="mt-5 text-h1 font-semibold text-foreground sm:text-display">
              Turn messy data into <span className="text-primary">clean, reliable</span> data.
            </h1>
            <p className="mt-4 max-w-xl text-body leading-relaxed text-muted-foreground sm:text-h3 sm:leading-relaxed">
              Upload your file, see every data quality issue at a glance, apply only the fixes you approve, and download a cleaner
              dataset in minutes — no code required.
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <Link href="/app" className={buttonVariants({ size: "lg" })}>
                Start Cleaning <ArrowRight />
              </Link>
              <Link href="/#features" className={buttonVariants({ size: "lg", variant: "secondary" })}>
                Explore Features
              </Link>
            </div>
            <ul className="mt-8 grid gap-2.5 text-small text-slate-600 sm:grid-cols-2">
              {["Preview every change before applying", "Undo or reset at any time", "Original values preserved", "Not sent to AI services"].map((point) => (
                <li key={point} className="flex items-center gap-2">
                  <span className="flex size-4 items-center justify-center rounded-full bg-success-soft text-success">
                    <Check className="size-3" aria-hidden="true" />
                  </span>
                  {point}
                </li>
              ))}
            </ul>
          </div>
          <AppPreview />
        </div>
      </section>

      {/* Features */}
      <section id="features" tabIndex={-1} className="scroll-mt-16 py-16 outline-none lg:py-20" aria-labelledby="features-title">
        <div className="container-page">
          <SectionHeading
            id="features-title"
            eyebrow="Features"
            title="Everything you need to trust a dataset"
            intro="A focused toolkit for the most common data quality problems, with clear feedback at every step."
          />
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <article key={f.title} className="rounded-lg border border-border bg-background p-5 shadow-card">
                <span className="inline-flex size-9 items-center justify-center rounded-md bg-primary-soft text-primary">
                  <f.icon className="size-5" aria-hidden="true" />
                </span>
                <h3 className="mt-4 text-h3 font-semibold text-foreground">{f.title}</h3>
                <p className="mt-1.5 text-small leading-relaxed text-muted-foreground">{fillLimits(f.description, limits)}</p>
              </article>
            ))}
          </div>
          <div id="operations" className="mt-8 scroll-mt-20 rounded-lg border border-border bg-canvas p-5">
            <h3 className="text-small font-semibold text-foreground">Included cleaning operations</h3>
            <ul className="mt-3 flex flex-wrap gap-2">
              {OPERATIONS.map((op) => (
                <li key={op.title} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1 text-small text-slate-700">
                  <op.icon className="size-3.5 text-accent" aria-hidden="true" />
                  {op.title}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" tabIndex={-1} className="scroll-mt-16 border-y border-border bg-canvas py-16 outline-none lg:py-20" aria-labelledby="how-title">
        <div className="container-page">
          <SectionHeading id="how-title" eyebrow="How it works" title="From messy file to clean data in three steps" />
          <ol className="mt-10 grid gap-4 md:grid-cols-3">
            {STEPS.map((step, i) => (
              <li key={step.title} className="rounded-lg border border-border bg-background p-5 shadow-card">
                <div className="flex items-center gap-3">
                  <span className="tabular flex size-7 items-center justify-center rounded-full bg-primary text-small font-semibold text-white">{i + 1}</span>
                  <h3 className="text-h3 font-semibold">{step.title}</h3>
                </div>
                <p className="mt-3 text-small leading-relaxed text-muted-foreground">{fillLimits(step.description, limits)}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Privacy */}
      <section id="privacy" tabIndex={-1} className="scroll-mt-16 py-16 outline-none lg:py-20" aria-labelledby="privacy-title">
        <div className="container-page grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] lg:items-start">
          <div>
            <SectionHeading
              id="privacy-title"
              eyebrow="Privacy & data handling"
              title="Your data stays under your control"
              intro="CleanData Studio needs to receive your file to clean it. This is exactly what happens to it — no more, no less."
            />
            <Link href="/privacy" className={cn(buttonVariants({ variant: "secondary" }), "mt-6")}>
              Read the privacy details <ArrowRight />
            </Link>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {PRIVACY_POINTS.map((item) => (
              <div key={item.title} className="rounded-lg border border-border bg-background p-5 shadow-card">
                <item.icon className="size-5 text-primary" aria-hidden="true" />
                <h3 className="mt-3 text-small font-semibold">{item.title}</h3>
                <p className="mt-1 text-small text-muted-foreground">{fillLimits(item.text, limits)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" tabIndex={-1} className="scroll-mt-16 border-t border-border bg-canvas py-16 outline-none lg:py-20" aria-labelledby="faq-title">
        <div className="container-page grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
          <SectionHeading id="faq-title" eyebrow="FAQ" title="Frequently asked questions" intro="Short answers to the questions people ask before uploading their data." />
          <div className="divide-y divide-border rounded-lg border border-border bg-background shadow-card">
            {FAQ.map((item) => (
              <details key={item.q} className="group px-5 py-4 [&_summary::-webkit-details-marker]:hidden">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 rounded text-body font-medium text-foreground">
                  {item.q}
                  <Plus className="size-4 shrink-0 text-slate-500 transition-transform group-open:rotate-45" aria-hidden="true" />
                </summary>
                <p className="mt-2.5 text-small leading-relaxed text-muted-foreground">{fillLimits(item.a, limits)}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-16" aria-labelledby="cta-title">
        <div className="container-page">
          <div className="flex flex-col items-start justify-between gap-6 rounded-xl border border-blue-100 bg-primary-soft px-6 py-8 sm:flex-row sm:items-center sm:px-10">
            <div>
              <h2 id="cta-title" className="text-h2 font-semibold">
                {SITE.tagline}
              </h2>
              <p className="mt-1 text-body text-slate-600">Open the workspace and upload a file — no account needed.</p>
            </div>
            <Link href="/app" className={cn(buttonVariants({ size: "lg" }), "shrink-0")}>
              Start Cleaning <ArrowRight />
            </Link>
          </div>
        </div>
      </section>
    </PageShell>
  );
}
