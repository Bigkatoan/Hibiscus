import { mkdirSync, writeFileSync } from "node:fs";

mkdirSync("dist/assets", { recursive: true });
writeFileSync(
  "dist/index.html",
  '<!doctype html><html><head><meta charset="utf-8"><title>Hibiscus stub</title>' +
    '<script type="module" src="/assets/app-abc123.js"></script></head><body>hibiscus-spa-stub</body></html>\n',
);
writeFileSync("dist/assets/app-abc123.js", "console.log('stub');\n");
