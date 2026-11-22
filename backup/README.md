# Backup: the systems before the two-system cleanup

Nothing here is built or published. It is what `LFXX` shipped up to the AIRAC 2611 builds, kept
for reference while NeoRadar is tested on approach and below.

| Path | What it was |
| --- | --- |
| `systems/irma`, `systems/cdg`, `systems/nce` | The hand-made IRMA, Paris-CDG and Nice systems (sprite tracks) |
| `systems/default` | CoFrance's base look, used by the FIR/UIR displays and the AVISOs |
| `systems/expressions.json`, `shapes.json`, `lists.yaml` | The shared files as they were |
| `images/symbols.png`, `symbols.json` | The sprite atlas the old tracks drew from |
| `scripts/tag_formats.py` | Generated one `cf-<format>` system per CoFrance tag format on every build |
| `scripts/build.py` | The build script that used it |

They were replaced by `shared/package/systems/neoirma` and `shared/package/systems/cdg` (see
[docs/maintaining.md](../docs/maintaining.md#tag-colours-labels-symbols-radar-systems)).
The old `irma` and `nce` targets named trail frames the atlas does not have (`plots/nce/*/t6`), and
`lists.yaml` named a rule that did not exist (`incorrectSquawkColor`).

To use an old system again, copy it back into `shared/package/systems/`, and the atlas into
`shared/package/images/` if it draws sprites.
