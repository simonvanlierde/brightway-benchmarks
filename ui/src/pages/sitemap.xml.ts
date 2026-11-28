import { STATIC_PAGES } from "../lib/pages";

export function GET() {
  const home = "https://simonvanlierde.com/brightway-benchmarks/";
  const urls = ["", ...STATIC_PAGES.map((page) => page.path)];
  const entries = urls.map((path) => `<url><loc>${new URL(path, home)}</loc></url>`);
  return new Response(
    `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${entries.join("")}</urlset>`,
    { headers: { "Content-Type": "application/xml; charset=utf-8" } },
  );
}
