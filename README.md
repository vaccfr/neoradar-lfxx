# neoradar-lfxx

NeoRadar packages for the French vACC, built from the French vACC Controller Pack
([vaccfr/Sector-Files](https://github.com/vaccfr/Sector-Files)), the CoFrance maps and the GNG
AIRAC data.

TO BE USED SOLELY ON THE VATSIM NETWORK - NOT TO BE USED FOR REAL WORLD AVIATION PURPOSES

## Packages

One package covers all of France. It is built from the French vACC military GNG sector file
(`LFFM`), which holds every French FIR:

| Package | FIRs | Provider URL |
| --- | --- | --- |
| `LFXX` | Paris, Reims, Brest, Bordeaux, Marseille, plus the military airfields | `https://pkg.neoradar.app/lfxx` |

NeoRadar is used for approach and below for now. The package has the converted sector file, the
approach (CCA/EGA) and AVISO ASRs as NeoRadar profiles (the centre FIR/UIR displays are left out),
the CoFrance maps, and two radar systems:

- **`neoirma`**: a stripless IRMA for every approach, and the ground look for every AVISO.
- **`cdg`**: the Paris-CDG approach, with CoFrance's Paris-CDG track colours and letters.

The systems before this change are kept in [backup/](backup/README.md).

## Documentation

- **[Maintainer guide](docs/maintaining.md)**: the AIRAC update, releasing, building locally,
  changing tags, maps or profiles, and what each build warning means.
- [diffs/README.md](diffs/README.md): patching upstream files before conversion.
- [transforms/README.md](transforms/README.md): text replacements in copied files.

## Never commit

GNG sector files (`.sct`, `.ese`), built packages (`build/`, `dist/`, zips), `server-dataset.json`
and airways databases. The sector data is licensed: it lives only in the private
`vaccfr/data-sectorfiles` repo. `.gitignore` covers these and the Validate workflow fails if one is
tracked.
