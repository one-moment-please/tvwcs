# TVWCS — Phase 2.5

TVWCS (TV Window Channel Switcher) is a lightweight, remote-friendly, TV-style interface for launching and switching between ordinary Linux desktop applications on i3. It is not a media center and needs no application-specific plugins. See `PROJECT_OVERVIEW.md` for goals and intended behaviour.

## Requirements

Linux Mint/Debian/Ubuntu with i3, Python 3, GTK 4 and PyGObject. `i3-msg` is used for windows and workspaces; `xdotool` finds the monitor under the pointer.  Optional: `xcape` (lone-modifier hotkeys such as Super).

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 i3 xdotool xcape
```

## Install

TVWCS is written in python and can be extracted to any folder, and just needs the dependencies installed and for an include to be added to ~/.config/i3/config that points to the tvwcs.conf file in the folder. a install.sh file is included that will move the files to ~/.config/i3/tvwcs and check if the include has been added to the i3 config file.
TVWCS is meant to live in **`~/.config/i3/tvwcs`**, next to your i3 config.

```bash
unzip TVWCS_Phase2_Updated_2_5.zip -d ~/.config/i3/     # creates ~/.config/i3/tvwcs
~/.config/i3/tvwcs/install.sh                          # checks packages, creates default hotkeys, prints the next step
```

Then add **one line** to `~/.config/i3/config` and reload i3 (`Mod+Shift+R`):

```i3
include ~/.config/i3/tvwcs/tvwcs.conf
```

`tvwcs.conf` starts TVWCS, includes your hotkeys and sets the window rules, so nothing else in your i3 config needs editing. `include` needs i3 4.20 or newer; on older versions paste the file's contents into your config instead. If you install elsewhere, edit the `exec` path in `tvwcs.conf`.

Your own data stays separate from the program in `~/.config/tvwcs/` (`config.json`, `hotkeys.conf`), so replacing the program folder to upgrade never touches your channels, favorites or hotkeys.

#Note: setting the launcher key to the Windows key in the settings is still somewhat dodgy. It might be better to determine the key number and then add a line in your i3 config like the following ("133" should be the left windows key)
`bindcode --release 133 exec --no-startup-id ~/.config/i3/tvwcs/tvwcs toggle`

## Using it

| Key | Action |
|---|---|
| **F2** (default; changeable in Settings) | Show or hide the Quick Menu |
| **Shift+F2** (default) | Open the Guide beside the Quick Menu; press again to close it |
| **↑ / ↓** | Move between rows |
| **← / →** | Move along a row. Past the right-hand end of the Quick Menu, **→** opens the Guide; past the end of the Guide, **→** opens Settings. **←** goes back (and closes Settings) |
| **←** on a row's options button | Expands that row's options |
| **Enter** | Launch, switch to, or activate the highlighted item |
| **Esc** or the remote's **Back** key | Back: closes a dialog, then Settings, then the Guide, then the Quick Menu |
| *any letter or digit* | Starts a search, wherever the focus is |

`tvwcs toggle`, `tvwcs guide` and `tvwcs stop` do the same from a terminal.

### Layout: three panels

```
┌ Quick Menu ┐ ┌──── Channel Guide ────┐ ┌ Settings ┐
│            │ │                       │ │          │
```

The Quick Menu is a full-height column at the left of the active workspace. The Guide opens beside it and fills the middle. Settings opens at the far right, exactly as wide as the Quick Menu, and only ever with the Guide. All panels keep the same margin from every edge and from each other. The workspace used is the one on the monitor under the mouse, so the bar is never covered.

### Quick Menu

- **Search** is at the top. Just type; results appear under the field. A channel number then Enter launches that channel.
- **Open applications** is organised by workspace. An app alone on its workspace appears as that app. Apps sharing a workspace appear as one entry named after its contents (for example *Brave + Text Editor*); selecting it shows the whole workspace on the monitor under the pointer.
- **Favorites** are listed below.
- **Row options** are on the left, behind one button (or press ← on it). For an app: open it the other way (tiled here, or in a workspace of its own), its `.desktop` actions, close. For a workspace: move it to another monitor (only shown with more than one monitor; pick which), expand it into its individual apps, close it (asks first). A favorite's options hold its launch-mode icon and `.desktop` actions.
- In search, press → at the end of the text to reach the highlighted result's options.

### Guide

Categories are header buttons: Enter folds or unfolds one. Each row shows the logo, channel, name and, smaller and dimmer, the application's description, then the favorite star and Edit. A **secondary profile** shows a ↳ in the logo's place, hanging from its application, and describes itself by its `.desktop` action and custom command (or a description you write). A 🔒 marks a PIN-protected profile. Favoriting never moves the list. The **⚙** at the top right (or → past the last row) opens Settings.

### Settings

Every row is one button: Enter flips an On/Off toggle, or opens a small pop-up listing the choices.

- **Interface size:** Desktop, 10-foot (1080p TV), 10-foot (4K TV). Scales text, icons, spacing and the panels.
- **Close when clicking outside:** hides TVWCS when another window takes focus.
- **Open running apps in a new workspace:** off (default), selecting an open app tiles it into the current workspace; on, it gets a workspace of its own. Each app's options open it the other way. Apps set to *always launch in a new workspace* in their profile always get one.
- **Hotkeys:** choose a key or combination for the Quick Menu and for the Guide, or tap a modifier by itself (Super, Alt, Ctrl, Shift). Super+Enter and every other Super shortcut keep working, because a lone-modifier hotkey is delivered by `xcape` only when the modifier is pressed and released alone. TVWCS writes `~/.config/tvwcs/hotkeys.conf` and reloads i3.
- **At login:** do nothing, reopen the last app you used, or open a chosen app (the list shows favorites first, then apps with channel numbers, then the rest). Runs once per login, a moment after TVWCS starts, and never asks for a PIN.
- **System:** Lock, Refresh applications, Sleep, Log out, Reboot, Shut down. Log out, Reboot and Shut down ask for confirmation; Cancel is selected by default. Lock auto-detects swaylock, i3lock, cinnamon-screensaver, xdg-screensaver or loginctl; set `settings.lock_command` to use something else.

### Where apps open

Each launch profile has a launch mode: **tiled** (default) beside what is already on the workspace, or **always in a new workspace**, alone on a fresh one with every other app left on its own workspace, out of sight. Set it with the checkbox in the profile editor or the icon beside a favorite. The Settings toggle above governs selecting apps that are *already running*.

### Descriptions

Each row's description defaults to the application's `.desktop` description (main profile) or to the profile's launch options (secondary profile). To write your own, open the application's page (Edit on its main row) for the application, or a profile's editor for a secondary profile. Leave the field empty to go back to the default.

### PIN-protected profiles

In a profile's editor, *PIN protection* sets a 4–8 digit PIN for that profile and when it is asked:

- **Only when launching:** the PIN is asked whenever TVWCS would start the profile.
- **When launching, and when showing it:** also asked when you bring up an open app of that profile (or a workspace holding one) from a workspace that is not currently on screen. An app that is already visible never asks.

The PIN is entered on an on-screen keypad you can drive with the D-pad (or type the digits). Five wrong tries lock that profile for 30 seconds. Editing or deleting a protected profile needs its current PIN. Because a window is just "a Firefox window", TVWCS remembers which profile launched it (for the current session) to know whose PIN applies; a window it did not launch uses its application's main profile. This is a convenience lock for a shared TV, not strong security. If a PIN is lost, remove the profile's `pin_hash` from `~/.config/tvwcs/config.json` while TVWCS is stopped.

## Data and boundaries

- Everything is local; no server or account.
- Apps come from XDG `.desktop` entries. TVWCS does not make mouse-only apps D-pad navigable.
- i3 on X11 is the supported setup. Log out and Lock detect sway, but a sway adapter (windows, workspaces, hotkeys) is future work.
- Window-to-app matching is best-effort (window class, `StartupWMClass`, names). Workspace names shown in TVWCS are derived from their contents; the workspaces themselves are not renamed in i3.

## Troubleshooting

- **Nothing appears on the hotkey:** start the controller once (`~/.config/i3/tvwcs/tvwcs`), then `i3-msg -t get_config | grep -i tvwcs`. If nothing matches, your i3 may be older than 4.20, or `~/.config/tvwcs/hotkeys.conf` is missing (run `install.sh`).
- **A lone-modifier hotkey (Super) does nothing:** install `xcape`; TVWCS runs it for you while it is open.
- **"TVWCS is already running":** `cat "${XDG_RUNTIME_DIR:-/tmp}/tvwcs.pid"`; stop the stale process or delete the file.
- **Menu overlaps your bar or sits in the wrong place:** TVWCS uses the workspace rectangle i3 reports. Raise `settings.margin`, and make sure `xdotool` is installed so the right monitor is chosen.
- **Text too small or too big:** Settings > Interface size.
- **An app is missing from Open applications:** TVWCS lists every normal window except its own and bars/docks. Windows are matched to workspaces by i3; if one is still missing, check `i3-msg -t get_tree` for its title and class.
- **Missing icons or odd glyphs:** install an icon theme such as `adwaita-icon-theme`; TVWCS falls back to text glyphs.
- Stop TVWCS before hand-editing `config.json`.

## Files

- `main.py` — application controller: launching, layout, workspaces, hotkeys, start-up, signals
- `ui_window.py` — the window: three panels, navigation, dialogs; `ui_settings.py` — the Settings panel; `ui_editors.py` — profile editors
- `widgets.py` — scaling, icons, navigation groups; `theme.py` — the Metro CSS
- `model.py` — profiles, settings, layout maths, badges, search
- `workspaces.py` — workspace entries and names; `hotkeys.py` — hotkey specs and i3 output; `pinlock.py` — PIN hashing and try limits; `ownership.py` — which profile launched which window
- `applications.py` — XDG `.desktop` discovery and window-to-app matching; `window_manager.py` — i3 IPC; `system_actions.py` — power and lock commands
- `tvwcs.conf` — i3 fragment; `install.sh` — installer; `tvwcs` — launcher script
- `test_*.py` — unit tests that need no display (`python3 -m unittest`)
- `CHANGELOG.md`, `PROJECT_OVERVIEW.md`, `VERSION`

## License

TVWCS is intended to be distributed under the MIT License. See the `LICENSE` file for details.

## Project Notes:
 - This project consists primarily of AI generated code where an AI was given a description of the project to make and then repeatedly given a list of revisions to remake the project to.
 - This project is not distributed with any code of conduct.
 - This project is free to copy, steal, plagiarize, mimic, reference, etc. 
