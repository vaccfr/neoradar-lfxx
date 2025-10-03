# NeoRadar LFXX

This repository contains the configuration and base files to generate & publish the NeoRadar package for LFXX, from its pre-existing EuroScope format.

## Prerequisites

Before you begin, ensure you have the following installed:

### Node.js (LTS Version)
You'll need Node.js LTS version installed on your system.

**Download and install Node.js LTS:**
- Visit [nodejs.org](https://nodejs.org/)
- Download the LTS version (recommended for most users)
- Follow the installation instructions for your operating system

### Yarn Package Manager
Once Node.js is installed, install Yarn via NPM:

```bash
npm install -g yarn
```

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/vaccfr/neoradar-lfxx/
cd neoradar-lfxx
```

### 2. Install NeoRadar CLI

Install the NeoRadar CLI tool globally:

```bash
yarn global add https://github.com/neoradar-project/cli.git
```

### 3. Download the Euroscope Sector File

Navigate to the official source to download the LFFF sector file:

**[https://files.aero-nav.com/LFFF](https://files.aero-nav.com/LFFF)**

Download and unzip the sector file package.

### 4. Copy Required Files

From the unzipped sector file package you downloaded, copy the following files to your cloned repository:

- **ICAO Data:**  
  Copy `LFFF/ICAO/` contents from the sub folder of the unzipped package → `icao_data/`

- **Sector Files:**  
  Copy `.sct` and `.ese` files from the root of the unzipped package → `sector_files/`

Your directory structure should look like:
```
neoradar-lfxx/
├── icao_data/
│   └── [ICAO files from LFFF/ICAO]
├── sector_files/
│   ├── [filename].sct
│   └── [filename].ese
└── ...
```

### 5. Run the Conversion

From the root of the `neoradar-lfxx` directory, run:

```bash
neoradar-cli convert . --no-profiles
```

This will process the sector files and generate the NeoRadar package structure.

### 6. Add Airways Database

After the conversion completes:

1. Obtain the `airways.db` file from your external provider
2. Place it in the `package/datasets/` directory

### 7. Install the Package

You have two options to make the package available to NeoRadar:

#### Option A: Copy the Package (Simple)

1. Rename the `package` folder to `LFXX`
2. Copy it to your NeoRadar packages directory:
   - **Windows:** `%USERPROFILE%\Documents\NeoRadar\packages\`
   - **macOS:** `~/Documents/NeoRadar/packages/`
   - **Linux:** `~/Documents/NeoRadar/packages/`

#### Option B: Create a Symlink (Development)

Create a symbolic link from the package folder to your NeoRadar packages directory named `LFXX`:

**Windows (cmd):**
```cmd
mklink /J "%USERPROFILE%\Documents\NeoRadar\packages\LFXX" "C:\path\to\neoradar-lfxx\package"
```

**macOS/Linux:**
```bash
ln -s /path/to/neoradar-lfxx/package ~/Documents/NeoRadar/packages/LFXX
```

## Troubleshooting

- **neoradar-cli not found:** Ensure Yarn's global bin directory is in your PATH
- **Permission errors:** You may need to run commands with elevated privileges
- **Missing files:** Double-check that all files were copied to the correct directories

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

TO BE USED SOLELY ON THE VATSIM NETWORK - NOT TO BE USED FOR REAL WORLD AVIATION PURPOSES

