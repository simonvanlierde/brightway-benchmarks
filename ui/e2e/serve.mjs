// The built site at /, with the real fixture data at /data/, for the browser tests only.
import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const TYPES = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

createServer((req, res) => {
  const requested = normalize(decodeURIComponent(new URL(req.url ?? "/", "http://x").pathname));
  const path = requested.startsWith("/ui/") ? requested.slice(3) : requested;
  const file = path.startsWith("/data/")
    ? join(root, "test/fixtures/real", path.slice("/data/".length))
    : join(root, "dist", path.endsWith("/") ? `${path}index.html` : path);
  try {
    if (!statSync(file).isFile()) throw new Error("not a file");
  } catch {
    // As GitHub Pages does: the site's own 404 page, with the 404 status, for a page it does not have.
    const missing = join(root, "dist/404.html");
    if (path.startsWith("/data/") || !statSync(missing, { throwIfNoEntry: false })?.isFile()) res.writeHead(404).end();
    else createReadStream(missing).pipe(res.writeHead(404, { "content-type": "text/html" }));
    return;
  }
  res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
  createReadStream(file).pipe(res);
}).listen(Number(process.argv[2]), "127.0.0.1"); // this host only
