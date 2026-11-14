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

for (const pkg of packages) {
  const before = { total, bad };
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
