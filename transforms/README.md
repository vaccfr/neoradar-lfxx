# Transforms

Literal find/replace rules applied while `scripts/build.py assemble` copies source files into a
package environment. Today they only touch the login profiles.

`replacements.json` holds `rules[]`, each:

```json
{ "appliesTo": "euroscope_data/LoginProfiles.txt*", "find": "UPSTREAM TEXT", "replace": "our text" }
```

- `appliesTo` is an `fnmatch` pattern over the environment-relative target path. Login profiles
  are matched as `euroscope_data/LoginProfiles.txt (<FIR>)`, one FIR file at a time, hence the
  trailing `*`.
- `find`/`replace` are plain strings, not regex. Paste the literal upstream text.
- A rule that matches nothing in a file it applies to prints a warning: upstream probably
  changed its wording and the rule needs updating.

For anything beyond a string swap, use a patch in `diffs/`.
