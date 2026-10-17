import { useEffect } from "react";

const SITE_URL = (import.meta.env.VITE_SITE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

type PageMeta = {
  title: string;
  description: string;
  path: string;
  /** Set false for pages search engines should not index (e.g. the workspace). */
  index?: boolean;
};

function setMeta(selector: string, attr: "name" | "property", key: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(selector);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

/** Per-page <title>, description, canonical URL and Open Graph tags. */
export function usePageMeta({ title, description, path, index = true }: PageMeta) {
  useEffect(() => {
    document.title = title;
    setMeta('meta[name="description"]', "name", "description", description);
    setMeta('meta[property="og:title"]', "property", "og:title", title);
    setMeta('meta[property="og:description"]', "property", "og:description", description);
    setMeta('meta[property="og:url"]', "property", "og:url", `${SITE_URL}${path}`);
    setMeta('meta[name="robots"]', "name", "robots", index ? "index, follow" : "noindex, nofollow");
    const canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (canonical) canonical.href = `${SITE_URL}${path}`;
  }, [title, description, path, index]);
}
