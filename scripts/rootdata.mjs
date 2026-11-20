// Move the root desk's inline data (index.html) to and from data/root/*.json.
//   node scripts/rootdata.mjs export   -> writes data/root/<NAME>.json
//   node scripts/rootdata.mjs import   -> writes those JSON files back into index.html
// Only array/object literals listed in NAMES are touched; CURATED_AT and the visible
// "curated <date>" labels follow data/root/meta.json.
import fs from "node:fs";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
let acorn; try { acorn = require("acorn"); } catch { acorn = require("/tmp/node_modules/acorn"); }
const NAMES = ["SRC","GLOBAL","INDIA","FO","PEOPLE","MADEALS","MATRENDS"];
const FILE = "index.html", DIR = "data/root";
const html = fs.readFileSync(FILE, "utf8");
const m = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
const main = m.reduce((a, b) => (b[1].length > a[1].length ? b : a));
const js = main[1], jsStart = main.index + main[0].indexOf(js);
const ast = acorn.parse(js, { ecmaVersion: "latest", sourceType: "script" });
const found = {};
for (const st of ast.body) if (st.type === "VariableDeclaration")
  for (const d of st.declarations) if (d.id.type === "Identifier" && (NAMES.includes(d.id.name) || d.id.name === "CURATED_AT"))
    found[d.id.name] = { start: d.init.start, end: d.init.end, src: js.slice(d.init.start, d.init.end) };
const mode = process.argv[2];
if (mode === "export") {
  fs.mkdirSync(DIR, { recursive: true });
  for (const n of NAMES) {
    if (!found[n]) { console.error("missing", n); process.exit(1); }
    const val = Function('"use strict";return (' + found[n].src + ")")();
    fs.writeFileSync(`${DIR}/${n}.json`, JSON.stringify(val, null, 1) + "\n");
  }
  const cur = Function("return " + found.CURATED_AT.src)();
  fs.writeFileSync(`${DIR}/meta.json`, JSON.stringify({ curated_at: cur }, null, 1) + "\n");
  console.log("exported", NAMES.length, "blocks; curated_at =", cur);
} else if (mode === "import") {
  const meta = JSON.parse(fs.readFileSync(`${DIR}/meta.json`, "utf8"));
  const repl = NAMES.map(n => [found[n], JSON.stringify(JSON.parse(fs.readFileSync(`${DIR}/${n}.json`, "utf8")))]);
  repl.push([found.CURATED_AT, JSON.stringify(meta.curated_at)]);
  repl.sort((a, b) => b[0].start - a[0].start);
  let out = js;
  for (const [loc, text] of repl) out = out.slice(0, loc.start) + text + out.slice(loc.end);
  acorn.parse(out, { ecmaVersion: "latest" }); // throws if broken
  const oldCur = Function("return " + found.CURATED_AT.src)();
  let page = html.slice(0, jsStart) + out + html.slice(jsStart + js.length);
  if (oldCur !== meta.curated_at) page = page.split("curated " + oldCur).join("curated " + meta.curated_at)
                                           .split("Curated " + oldCur).join("Curated " + meta.curated_at)
                                           .split("as of " + oldCur).join("as of " + meta.curated_at);
  fs.writeFileSync(FILE, page);
  console.log("imported", NAMES.length, "blocks; curated_at =", meta.curated_at);
} else { console.error("usage: node scripts/rootdata.mjs export|import"); process.exit(2); }
