# Promise Minimap Mover

**Version 1.2.1** — an unofficial World of Tanks client mod that lets you move the in-battle minimap and remember its position **and size** between battles.

## Features

- Reposition the minimap during battle using **Ctrl + Shift + left-click and drag**.
- Preserve normal **Ctrl + click** minimap actions, such as pings.
- Remember the minimap position between battles and game restarts.
- Remember the minimap size selected with the game's normal **+ / -** controls.
- Enable or disable the mod using a checkbox in **Aslain's Mod Menu**.
- Keep the minimap partially visible when moving it toward the screen edge.
- Save settings locally; no manual configuration is needed for normal use.

## Controls

| Action | Control |
| --- | --- |
| Move minimap | Hold **Ctrl + Shift**, then **left-click and drag** |
| Normal minimap action (e.g., ping) | **Ctrl + click** |
| Increase/decrease minimap size | Game's standard **+ / -** keys |
| Enable/disable mod | **Mod Menu → Promise Minimap Mover → Enable Minimap Mover** |

Dragging begins after approximately **5 pixels** of movement to distinguish a click from a drag. Release the left mouse button to save the new position.

**Note:** The drag shortcut does not perform a minimap hit-test before beginning a drag. Avoid using Ctrl + Shift + drag elsewhere on the screen.

## Dependencies and compatibility

| Component | Requirement | Purpose |
| --- | --- | --- |
| **World of Tanks (PC)** | **Required** | Runs the client mod; install a `.wotmod` built for your game version. |
| **Aslain’s Mod Menu** | **Optional for minimap movement; required for the in-game checkbox** | Provides the settings-menu API (`gui.aslainMenu.g_modsSettingsApi`) used by v1.2.1. |
| **Python 2.7** | **Build-time only** | Used to compile/package the Python mod; not a separate end-user installation requirement. |
| **ProMod / OldSkool ProMod** | **Not required** | Appreciated community project, but not a dependency of Promise Minimap Mover. |

The mod's minimap controls and saved position/size work independently of Aslain’s Mod Menu. Without a compatible menu, the enable/disable checkbox will not be available in the game UI. CHAMPi’s settings GUI and Izeberg’s ModsSettingsAPI are **not** substitutes for the Aslain menu integration in this release.

## Installation

1. Build or obtain the **Promise Minimap Mover 1.2.1** `.wotmod` package for your installed World of Tanks client version.
2. Place the package in the corresponding game mod folder:

   ```text
   World_of_Tanks/mods/<game-version>/
   ```

3. Remove older Promise Minimap Mover `.wotmod` packages from the same game-version folder to avoid loading multiple versions.
4. Start World of Tanks and enter a battle.

### Settings-menu integration (Aslain Mod Menu)

To use the in-game enable/disable checkbox, install a compatible **Aslain Mod Menu** providing `gui.aslainMenu.g_modsSettingsApi`.

Open **Mod Menu** from the game's **Open settings** menu, then find **Promise Minimap Mover → Enable Minimap Mover**. The setting is saved and restored on restart. For a complete layout change after toggling, enter a new battle.

The movement functionality and the settings-menu integration are separate: the mod may load even when the optional menu API is unavailable, but its checkbox will not appear there.

## Configuration

The mod stores its settings in the World of Tanks preferences directory, under:

```text
<preferences>/mods/promise/
```

**Position and size:** `minimap_mover.cfg`

```text
offset_x offset_y size_index
```

- `offset_x` — horizontal offset from the minimap's original position.
- `offset_y` — vertical offset from the minimap's original position.
- `size_index` — minimap size index (normally `0` through `5`).

The mod saves the position when a drag finishes and updates the saved size when it detects a user-initiated resize.

**Enabled state:** `minimap_mover_enabled.json`

```json
{"enabled": true}
```

This file stores the enable/disable setting independently from the minimap's position and size.

To reset the saved placement, **close the game** and delete `minimap_mover.cfg`. To reset the enable/disable preference, delete `minimap_mover_enabled.json` while the game is closed.

## Building from source

The repository uses `build.py` to package the Python client mod into a `.wotmod` file. The World of Tanks client uses **Python 2.7**, so use the Python 2.7 interpreter expected by the project's build script.

To inspect available build options:

```powershell
python .\build.py --help
```

Build with the game version matching your installed client. The source imports World of Tanks client APIs and cannot be run as a standalone desktop Python program.

## Troubleshooting

**The checkbox does not appear:** Confirm that Aslain Mod Menu is installed and working. This release registers its checkbox with **Aslain's menu**, not CHAMPi's settings window. Check `game.log` for `Aslain Mod Menu registered`.

**The mod does not move the minimap:** Confirm the checkbox is enabled, enter a new battle, and try **Ctrl + Shift + left-click and drag**.

**Position or size is not remembered:** Confirm the game can write to `<preferences>/mods/promise/minimap_mover.cfg`. Change size using the normal `+ / -` controls, then check again in a new battle.

**Disabling the mod does not immediately restore the current battle layout:** The full change takes effect when a new battle starts.

**The mod fails to load:** Check that the `.wotmod` matches the installed game version, that no older copy is installed alongside it, and that `game.log` contains `[MinimapMover 1.2.1] Loaded` or relevant error messages.

## Release notes

### 1.2.1

- Added a working **Enable Minimap Mover** checkbox to **Aslain's Mod Menu**.
- Kept the enable/disable preference in a separate JSON configuration file.
- Preserved the existing minimap movement and position/size persistence behavior.

### 1.1.9

- Fixed minimap size persistence by tracking user-initiated size changes through the game's minimap component.

## Acknowledgements

Special thanks to **Aslain** for the excellent work on **Aslain’s Modpack and Mod Menu**, which makes managing World of Tanks mods easier and provides the settings integration used by Promise Minimap Mover.

We also appreciate the **OldSkool ProMod (ProMod) team** and their great work for the World of Tanks modding community. Thank you for the time, care, and ongoing effort you put into your projects.

These acknowledgements are expressions of appreciation, not claims of sponsorship, endorsement, or a technical dependency on ProMod.

## Disclaimer

Promise Minimap Mover is an independent, unofficial community modification for **World of Tanks** and is not affiliated with or endorsed by Wargaming. Compatibility and permitted use depend on the game version and applicable mod policies.

## License

No license is specified in the supplied project documentation. Add a `LICENSE` file before granting others explicit permission to reuse, modify, or redistribute the source.
