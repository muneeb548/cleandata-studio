import { useEffect, useState } from "react";
import { ArrowRight, Menu, X } from "lucide-react";
import { Link, usePathname } from "@/lib/router";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Logo } from "./Logo";

const NAV = [
  { href: "/#features", label: "Features" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#privacy", label: "Privacy" },
  { href: "/#faq", label: "FAQ" },
  { href: "/about", label: "About" },
];

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  useEffect(() => setOpen(false), [pathname]);

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/85">
      <div className="container-page flex h-14 items-center justify-between gap-4">
        <Logo />
        <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-md px-3 py-1.5 text-body text-slate-600 transition-colors hover:bg-muted hover:text-foreground"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Link href="/app" className={cn(buttonVariants({ size: "sm" }), "hidden sm:inline-flex")}>
            Start Cleaning <ArrowRight />
          </Link>
          <button
            type="button"
            className="inline-flex size-9 items-center justify-center rounded-md text-slate-700 hover:bg-muted md:hidden"
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </div>
      {open && (
        <nav id="mobile-nav" aria-label="Mobile" className="border-t border-border bg-background md:hidden">
          <div className="container-page flex flex-col py-2">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className="rounded-md px-2 py-2.5 text-body text-slate-700 hover:bg-muted"
              >
                {item.label}
              </Link>
            ))}
            <Link href="/app" className={cn(buttonVariants(), "my-2")}>
              Start Cleaning <ArrowRight />
            </Link>
          </div>
        </nav>
      )}
    </header>
  );
}
