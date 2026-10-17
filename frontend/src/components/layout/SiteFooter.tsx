import { Link } from "@/lib/router";
import { SITE } from "@/content/site";
import { Logo } from "./Logo";

const COLUMNS = [
  {
    title: "Product",
    links: [
      { href: "/app", label: "Cleaning workspace" },
      { href: "/#features", label: "Features" },
      { href: "/#operations", label: "Supported operations" },
      { href: "/#faq", label: "FAQ" },
    ],
  },
  {
    title: "Company",
    links: [
      { href: "/about", label: "About" },
      { href: "/contact", label: "Contact & feedback" },
    ],
  },
  {
    title: "Legal",
    links: [
      { href: "/privacy", label: "Privacy & data handling" },
      { href: "/privacy#terms", label: "Terms of use" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-canvas">
      <div className="container-page grid gap-8 py-10 sm:grid-cols-2 lg:grid-cols-[1.5fr_1fr_1fr_1fr]">
        <div className="max-w-xs">
          <Logo />
          <p className="mt-3 text-body text-muted-foreground">{SITE.description}</p>
        </div>
        {COLUMNS.map((col) => (
          <div key={col.title}>
            <h2 className="text-caption font-semibold tracking-wide text-slate-600 uppercase">{col.title}</h2>
            <ul className="mt-3 space-y-2">
              {col.links.map((l) => (
                <li key={l.href}>
                  <Link href={l.href} className="text-body text-slate-600 hover:text-primary">
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-border">
        <div className="container-page flex flex-col gap-1 py-4 text-caption text-muted-foreground sm:flex-row sm:justify-between">
          <p>
            © {new Date().getFullYear()} {SITE.name}. {SITE.tagline}
          </p>
          <p>Version 1.1 · CSV, TSV, Excel and JSON files</p>
        </div>
      </div>
    </footer>
  );
}
