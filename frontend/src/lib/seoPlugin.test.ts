import { absolutiseHtml, normaliseSiteUrl, robotsTxt, sitemapXml } from "../../seo-plugin";

describe("build-time SEO files", () => {
  it("normalises the site URL and rejects paths", () => {
    expect(normaliseSiteUrl(" https://cleandata.example.com/ ")).toBe("https://cleandata.example.com");
    expect(normaliseSiteUrl(undefined)).toBe("");
    expect(() => normaliseSiteUrl("cleandata.example.com")).toThrow();
    expect(() => normaliseSiteUrl("https://example.com/app")).toThrow();
  });

  it("writes robots.txt that hides the workspace and API", () => {
    const txt = robotsTxt("https://cleandata.example.com");
    expect(txt).toContain("Disallow: /app");
    expect(txt).toContain("Disallow: /api/");
    expect(txt).toContain("Sitemap: https://cleandata.example.com/sitemap.xml");
    expect(robotsTxt("")).not.toContain("Sitemap");
  });

  it("lists only public pages in the sitemap", () => {
    const xml = sitemapXml("https://cleandata.example.com");
    expect(xml).toContain("<loc>https://cleandata.example.com/</loc>");
    expect(xml).toContain("<loc>https://cleandata.example.com/privacy</loc>");
    expect(xml).not.toContain("/app<");
  });

  it("makes canonical and og:image absolute", () => {
    const html = '<link rel="canonical" href="/" />\n    <meta property="og:image" content="/og-image.png" />';
    const out = absolutiseHtml(html, "https://cleandata.example.com");
    expect(out).toContain('href="https://cleandata.example.com/"');
    expect(out).toContain('content="https://cleandata.example.com/og-image.png"');
    expect(out).toContain('og:url" content="https://cleandata.example.com/"');
    expect(absolutiseHtml(html, "")).toBe(html);
  });
});
