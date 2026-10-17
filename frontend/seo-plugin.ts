/**
 * Build-time SEO files. robots.txt, sitemap.xml and the canonical / Open Graph URLs
 * in index.html need the site's absolute address, which is only known at deploy
 * time, so they are generated from VITE_SITE_URL during `npm run build`.
 */
import type { Plugin } from "vite";

/** Public pages that should be indexed (the workspace /app is excluded on purpose). */
export const PUBLIC_PAGES = [
  { path: "/", changefreq: "monthly", priority: "1.0" },
  { path: "/about", changefreq: "yearly", priority: "0.5" },
  { path: "/privacy", changefreq: "yearly", priority: "0.5" },
  { path: "/contact", changefreq: "yearly", priority: "0.4" },
];

export function normaliseSiteUrl(raw: string | undefined): string {
  const value = (raw ?? "").trim().replace(/\/+$/, "");
  if (!value) return "";
  if (!/^https?:\/\/[^/\s]+$/i.test(value)) {
    throw new Error(`VITE_SITE_URL must look like https://example.com (no path), got "${raw}"`);
  }
  return value;
}

export function robotsTxt(site: string): string {
  const lines = ["User-agent: *", "Allow: /", "Disallow: /app", "Disallow: /api/"];
  if (site) lines.push("", `Sitemap: ${site}/sitemap.xml`);
  return lines.join("\n") + "\n";
}

const xmlEscape = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export function sitemapXml(site: string): string {
  const urls = PUBLIC_PAGES.map(
    (p) => `  <url><loc>${xmlEscape(site + p.path)}</loc><changefreq>${p.changefreq}</changefreq><priority>${p.priority}</priority></url>`,
  );
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join("\n")}\n</urlset>\n`;
}

/** Make the canonical link and Open Graph image absolute and add og:url (crawlers don't run JavaScript). */
export function absolutiseHtml(html: string, site: string): string {
  if (!site) return html;
  return html
    .replace('<link rel="canonical" href="/" />', `<link rel="canonical" href="${site}/" />`)
    .replace('<meta property="og:image" content="/og-image.png" />', `<meta property="og:image" content="${site}/og-image.png" />\n    <meta property="og:url" content="${site}/" />`);
}

export function seoFiles(rawSiteUrl: string | undefined): Plugin {
  const site = normaliseSiteUrl(rawSiteUrl);
  return {
    name: "cleandata-seo-files",
    apply: "build",
    buildStart() {
      if (!site) this.warn("VITE_SITE_URL is not set: robots.txt has no Sitemap line and sitemap.xml is not generated.");
      else if (/localhost|127\.0\.0\.1/.test(site)) this.warn(`VITE_SITE_URL is ${site}; set your public address before deploying.`);
    },
    transformIndexHtml(html: string) {
      return absolutiseHtml(html, site);
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "robots.txt", source: robotsTxt(site) });
      if (site) this.emitFile({ type: "asset", fileName: "sitemap.xml", source: sitemapXml(site) });
    },
  };
}
