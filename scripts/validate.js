#!/usr/bin/env node
// Validates built packages against the NeoRadar JSON Schemas (neoradar-project/schemas).
//
//   node scripts/validate.js <schemas checkout> <package dir> [<package dir> ...]
//
// Needs ajv@8 and js-yaml@4 resolvable (npm install --no-save --prefix scripts ajv@8 js-yaml@4,
// or NODE_PATH pointing at a neoradar-cli checkout's node_modules).
// Exit code 1 when any file is invalid.
//
// Tolerated: map.items[].pointType in profiles. neoradar-cli's ASR converter writes it on every
// navaid item and profile.schema.json does not list it; that is a CLI/schema drift, not ours.
const path = require("path");
const fs = require("fs");
const Ajv = require("ajv");
const yaml = require("js-yaml");

const [schemasDir, ...packages] = process.argv.slice(2);
if (!schemasDir || packages.length === 0) {
  console.error("usage: validate.js <schemas checkout> <package dir> [...]");
  process.exit(2);
}

const BASE = "https://raw.githubusercontent.com/neoradar-project/schemas/refs/heads/main/";
const SCHEMAS = [
  "package/manifest.schema.json",
  "profile.schema.json",
  "systems/expressions.schema.json",
  "systems/labels.schema.json",
  "systems/lists.schema.json",
  "systems/mapstyle.schema.json",
  "systems/shapes.schema.json",
  "systems/targets.schema.json",
  "systems/policy.schema.json",
  "datasets/map-layer.schema.json",
  "datasets/radars.schema.json",
];
const SYSTEM_FILES = {
  expressions: "systems/expressions.schema.json",
  labels: "systems/labels.schema.json",
  lists: "systems/lists.schema.json",
  mapstyle: "systems/mapstyle.schema.json",
  shapes: "systems/shapes.schema.json",
  targets: "systems/targets.schema.json",
  policy: "systems/policy.schema.json",
};

const ajv = new Ajv({ allErrors: true, strict: false, logger: false });
for (const rel of SCHEMAS) {
  const file = path.join(schemasDir, rel);
  if (!fs.existsSync(file)) continue;
  const schema = JSON.parse(fs.readFileSync(file, "utf8"));
  schema.$id = BASE + rel;
  delete schema.$schema;
  ajv.addSchema(schema, schema.$id);
}

const read = (f) => {
  const text = fs.readFileSync(f, "utf8").replace(/^﻿/, "");
  return /\.ya?ml$/.test(f) ? yaml.load(text) : JSON.parse(text);
};
const walk = (d) =>
  fs.existsSync(d) ? fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)])) : [];
const tolerated = (rel, e) =>
  rel === "profile.schema.json" && e.keyword === "additionalProperties" && e.params.additionalProperty === "pointType";

let bad = 0;
let total = 0;
function check(pkg, file, rel) {
  const validate = ajv.getSchema(BASE + rel);
  if (!validate) return;
  total++;
  let data;
  try {
    data = read(file);
  } catch (e) {
    bad++;
    console.log(`PARSE ${path.relative(pkg, file)}: ${e.message}`);
    return;
  }
  if (validate(data)) return;
  const errors = validate.errors.filter((e) => !["anyOf", "oneOf", "if"].includes(e.keyword) && !tolerated(rel, e));
  if (errors.length === 0) return;
  bad++;
  console.log(`INVALID ${path.relative(pkg, file)} (${rel})`);
  for (const e of errors.slice(0, 8)) console.log(`    ${e.instancePath || "/"} ${e.message} ${JSON.stringify(e.params).slice(0, 120)}`);
}

// The schemas check each file alone. The client also ignores a reference that leads nowhere (a
// "=rule", "$expression", shape or "#system" no file defines), so a typo there draws nothing and
// says nothing: those are checked here across the systems folder.
function checkReferences(pkg) {
  const dir = path.join(pkg, "systems");
  if (!fs.existsSync(dir)) return;
  const load = (f) => (fs.existsSync(f) ? read(f) : {});
  const expressions = load(path.join(dir, "expressions.json"));
  const rules = new Set(Object.keys(expressions.rules || {}));
  const exprs = new Set(Object.keys(expressions.expressions || {}));
  const shapes = new Set(Object.keys(load(path.join(dir, "shapes.json")).shapes || {}));
  const systems = new Set(fs.readdirSync(dir, { withFileTypes: true }).filter((e) => e.isDirectory()).map((e) => e.name));
  const atlas = path.join(pkg, "images", "symbols.json");
  const frames = fs.existsSync(atlas) ? new Set(Object.keys(read(atlas).frames || {})) : new Set();
  const SHAPE_KEYS = new Set(["plotShape", "hoverShape", "shapeRef"]);
  for (const f of walk(dir).filter((f) => /\.(json|ya?ml)$/.test(f))) {
    const problems = new Set();
    const visit = (value, key, parentKey) => {
      if (Array.isArray(value)) return value.forEach((v) => visit(v, key, parentKey));
      if (value && typeof value === "object") return Object.entries(value).forEach(([k, v]) => visit(v, k, key));
      if (typeof value !== "string" || key === "$schema") return;
      let m;
      if ((m = /^=([A-Za-z_]\w*)$/.exec(value)) && !rules.has(m[1])) problems.add(`rule ${value}`);
      if ((m = /^\$([A-Za-z_]\w*)$/.exec(value)) && !exprs.has(m[1])) problems.add(`expression ${value}`);
      if ((SHAPE_KEYS.has(key) || (key === "shape" && (parentKey === "historyTrailShape" || parentKey === "leaderBase"))) && !shapes.has(value)) problems.add(`shape ${value}`);
      if ((key === "ground" || key === "groundSymbology") && value.startsWith("#") && !systems.has(value.slice(1))) problems.add(`system ${value}`);
      if ((key === "plotImage" || key === "historyTrailImages") && !frames.has(value)) problems.add(`sprite ${value}`);
    };
    visit(read(f), "", "");
    total++;
    if (problems.size === 0) continue;
    bad++;
    console.log(`UNRESOLVED ${path.relative(pkg, f)}: ${[...problems].sort().join(", ")}`);
  }
}

for (const pkg of packages) {
  const before = { total, bad };
  checkReferences(pkg);
  check(pkg, path.join(pkg, "manifest.json"), "package/manifest.schema.json");
  for (const f of walk(path.join(pkg, "systems"))) {
    const base = path.basename(f).replace(/\.(json|ya?ml)$/, "");
    if (SYSTEM_FILES[base] && /\.(json|ya?ml)$/.test(f)) check(pkg, f, SYSTEM_FILES[base]);
  }
  for (const f of walk(path.join(pkg, "profiles")).filter((f) => f.endsWith(".stp"))) check(pkg, f, "profile.schema.json");
  for (const f of walk(path.join(pkg, "datasets")).filter((f) => f.endsWith(".geojson"))) check(pkg, f, "datasets/map-layer.schema.json");
  const radars = path.join(pkg, "datasets", "radars.json");
  if (fs.existsSync(radars)) check(pkg, radars, "datasets/radars.schema.json");
  console.log(`${pkg}: ${total - before.total - (bad - before.bad)}/${total - before.total} valid`);
}
process.exitCode = bad ? 1 : 0;
