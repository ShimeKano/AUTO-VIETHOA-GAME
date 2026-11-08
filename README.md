# AUTO-VIETHOA-GAME

A Windows desktop manager for installing and managing Unity game translation support without cloning or downloading plugin source code.

## Current approach

The app downloads **compiled release assets only** from the official XUnity.AutoTranslator GitHub Releases page. It does not clone the repository or download source archives. The first adapter targets Unity Mono games using the standalone ReiPatcher package.

This is an integration/manager, not a reimplementation of XUnity's runtime text hooks. It provides a simple desktop workflow around the compiled plugin:
- Select a Unity game folder and inspect its executable/runtime layout.
- Download the official prebuilt XUnity ReiPatcher release asset.
- Back up files before installing; keep a manifest so the app can roll back only files it installed or replaced.
- Run the official setup helper and launch the patched game.
- Open the game's translation/configuration folders and edit generated text files.
- Keep a local log of actions and errors.

## MVP scope

- Windows 10/11, Unity Mono games first.
- Unity IL2CPP is detected and clearly reported as unsupported by this first MVP; it must not be force-installed with the Mono package.
- No promise of universal compatibility: custom Unity loaders, anti-cheat, protected executables, and unsupported game layouts can prevent injection.
- Automatic machine translation requires a supported online endpoint. Offline translation is possible only when the user configures a compatible local translator or supplies translation files.

## Run from source

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Build Windows executable

```powershell
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name AutoVietHoaGame main.py
```

## Safety

- Use only with games you own or are authorized to modify.
- Do not use with multiplayer games protected by anti-cheat.
- The installer must not overwrite game files without backing them up.
- The user must confirm before installing or restoring.
- Plugin binaries remain the property of their respective authors and are downloaded from the official release page at runtime. See the upstream project's redistribution guidance and license before redistributing any plugin binaries.

## Upstream

- XUnity.AutoTranslator: https://github.com/bbepis/XUnity.AutoTranslator
- Releases: https://github.com/bbepis/XUnity.AutoTranslator/releases

