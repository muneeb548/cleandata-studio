/**
 * A tiny client-side router (History API). The app only has a handful of
 * pages, so a full routing library would add weight without adding value.
 */
import { useEffect, useSyncExternalStore, type AnchorHTMLAttributes, type MouseEvent } from "react";

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

function getPath() {
  return window.location.pathname;
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, getPath, () => "/");
}

function scrollToHash(hash: string) {
  if (!hash) {
    window.scrollTo({ top: 0 });
    return;
  }
  // Wait a frame so the target page has rendered.
  requestAnimationFrame(() => {
    const el = document.getElementById(decodeURIComponent(hash.slice(1)));
    if (el) {
      el.scrollIntoView({ block: "start" });
      el.focus({ preventScroll: true });
    }
  });
}

export function navigate(to: string, { replace = false } = {}) {
  const url = new URL(to, window.location.origin);
  const samePath = url.pathname === window.location.pathname;
  if (replace) window.history.replaceState(null, "", url);
  else window.history.pushState(null, "", url);
  listeners.forEach((l) => l());
  if (!samePath || url.hash) scrollToHash(url.hash);
}

type LinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & { href: string };

/** Anchor that navigates without a full page reload for internal links. */
export function Link({ href, onClick, ...props }: LinkProps) {
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      !href.startsWith("/") ||
      props.target === "_blank"
    ) {
      return;
    }
    event.preventDefault();
    navigate(href);
  };
  return <a href={href} onClick={handleClick} {...props} />;
}

/** On first load, honour a hash in the URL (e.g. /#faq). */
export function useInitialHashScroll() {
  useEffect(() => {
    if (window.location.hash) scrollToHash(window.location.hash);
  }, []);
}
