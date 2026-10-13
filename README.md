# TVWCS

TVWCS (TV Window Channel Switcher) is a lightweight, remote-friendly, TV-style interface for launching and switching between ordinary Linux desktop applications on i3. It is not a media center and needs no application-specific plugins. See `PROJECT_OVERVIEW.md` for goals and intended behaviour.

Quick menu: <img src="assets/quick-menu.png" height="300">  Full Menu: <img src="assets/guide-menu.png" height="300">

## Requirements

Linux Mint/Debian/Ubuntu with i3, Python 3, GTK 4 and PyGObject. `i3-msg` is used for windows and workspaces; `xdotool` finds the monitor under the pointer. The Networking tab talks to NetworkManager via `nmcli`; the Updates tab uses `apt` (and `sudo` to install). Optional: `xcape` (lone-modifier hotkeys such as Super).

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 i3 xdotool network-manager xcape
```

## Install

### From the repository

```bash
git clone <this repo> && cd tvwcs
./scripts/install.sh        # copies TVWCS into ~/.config/i3/tvwcs, checks dependencies,
                            # creates default hotkeys, and prints the i3 include line if missing
```

Run it again at any time to **upgrade**: program files are replaced in place, your data in
`~/.config/tvwcs/` (channels, favorites, settings, hotkeys) is never touched, and a hand-edited
`tvwcs.conf` is kept as `tvwcs.conf.bak`. If you cloned with an older version installed, just pull
and re-run `./scripts/install.sh`.

### From a release zip

```bash
unzip TVWCS-2.6.0.zip -d ~/.config/i3/     # creates ~/.config/i3/tvwcs
cd ~/.config/i3/tvwcs && ./install.sh      # same script; detects the release layout automatically
```

To upgrade from an older zip, extract the new one over the old folder (or anywhere else) and run its
`install.sh`; it installs/copies into `~/.config/i3/tvwcs` and keeps your settings. You can also point
it somewhere else with `TVWCS_DEST=/some/path ./install.sh`.

Then add **one line** to `~/.config/i3/config` and reload i3 (`Mod+Shift+R`) — `install.sh` prints the
exact line if it is still missing:

```i3
include ~/.config/i3/tvwcs/tvwcs.conf
```

`tvwcs.conf` starts TVWCS, includes your hotkeys and sets the window rules, so nothing else in your i3 config needs editing. `include` needs i3 4.20 or newer; on older versions paste the file's contents into your config instead. If you install elsewhere, edit the `exec` path in `tvwcs.conf`.

Your own data stays separate from the program in `~/.config/tvwcs/` (`config.json`, `hotkeys.conf`), so replacing the program folder to upgrade never touches your channels, favorites or hotkeys.

#Note: setting the launcher key to the Windows key in the settings is still somewhat dodgy. It might be better to determine the key number and then add a line in your i3 config like the following ("133" should be the left windows key)
`bindcode --release 133 exec --no-startup-id ~/.config/i3/tvwcs/bin/tvwcs toggle`

## Using it

| Key | Action |
|---|---|
| **F2** (default; changeable in Settings) | Show or hide the Quick Menu |
| **Shift+F2** (default) | Open the Applications window beside the Quick Menu; press again to close it |
| **↑ / ↓** | Move between rows |
| **← / →** | Move along a row. Past the right-hand end of the Quick Menu, **→** opens Applications. Inside Applications, **→** moves into the tab bar and content; **←** goes back toward the Quick Menu |
| **←** on a row's options button | Expands that row's options (this also works when the options buttons are hidden in Settings) |
| **Right-click** an app or workspace in the Quick Menu | Opens that row's options menu (same as the options button) |
| **Enter** | Launch, switch to, or activate the highlighted item |
| **Esc** or the remote's **Back** key | Back: closes a dialog, then the Applications window, then the Quick Menu |
| *any letter or digit* | Starts a search, wherever the focus is |

`tvwcs toggle`, `tvwcs guide` and `tvwcs stop` do the same from a terminal (`guide` opens the Applications window).

### Layout: two panels

```
┌ Quick Menu ┐ ┌──────────── Applications (tabbed) ────────────┐
│            │ │  Applications · Networking · Updates · Settings │
```

The Quick Menu is a full-height column at the left of the active workspace. The Applications window opens beside it and fills the rest. It is one window with four tabs — Applications, Networking, Updates and Settings — so opening Settings no longer grows anything. All panels keep the same margin from every edge and from each other. The workspace used is the one on the monitor under the mouse, so the bar is never covered.

### Quick Menu

- **Search** is at the top. Just type; results appear under the field. A channel number then Enter launches that channel.
- **Open applications** is organised by workspace. An app alone on its workspace appears as that app. Apps sharing a workspace appear as one entry named after its contents (for example *Brave + Text Editor*); selecting it shows the whole workspace on the monitor under the pointer.
- **Favorites** are listed below.
- **Row options** are on the left, behind one button (or press ← on it, or right-click the row). For an app: open it the other way (tiled here, or in a workspace of its own), its `.desktop` actions, close. For a workspace: move it to another monitor (only shown with more than one monitor; pick which), expand it into its individual apps, close it (asks first). A favorite's options hold its launch-mode icon and `.desktop` actions. The Settings tab can hide the options buttons; right-click (or ←) still reaches them.
- In search, press → at the end of the text to reach the highlighted result's options.

### Applications window

The tab bar sits at the top: **Applications · Networking · Updates · Settings**.

#### Applications tab

Categories are header buttons: Enter folds or unfolds one. Each row shows the logo, channel, name and, smaller and dimmer, the application's description, then the favorite star and Edit. A **secondary profile** shows a ↳ in the logo's place, hanging from its application, and describes itself by its `.desktop` action and custom command (or a description you write). A 🔒 marks a PIN-protected profile. Favoriting never moves the list.

#### Networking tab

Lists wired (ethernet) connections and Wi-Fi with their IP addresses, default gateway, DNS servers and the connected network. You can scan for Wi-Fi networks and connect (with password prompt), turn Wi-Fi off or on, and edit IPv4 settings per interface — DHCP or manual address / netmask / gateway / DNS. Changes go through NetworkManager (`nmcli`) and apply immediately.

#### Updates tab

A GUI over apt. The top bar has **Check for updates** (it becomes **Refresh** once you have checked), **Install updates**, **Clear** (unchecks everything) and **Select all**. Below, the left list (about two-thirds the width of the right panel) shows one row per pending upgrade — its kind (*Security update*, *Software update*, *3rd party repository update*), a checkbox deciding whether it is installed, the package name, new version and size. The right panel shows details of the selected package: description, information, packages affected and changelog. Installing runs apt in the background and asks for your sudo password.

#### Settings tab

Every row is one button: Enter flips an On/Off toggle, or opens a small pop-up listing the choices.

- **Interface size:** Desktop, 10-foot (1080p TV), 10-foot (4K TV). Scales text, icons, spacing and the panels.
- **Close when clicking outside:** hides TVWCS when another window takes focus.
- **Open running apps in a new workspace:** off (default), selecting an open app tiles it into the current workspace; on, it gets a workspace of its own. Each app's options open it the other way. Apps set to *always launch in a new workspace* in their profile always get one.
- **Hide the options buttons in the Quick Menu:** folds the ⋯ buttons away for a cleaner list. Reminder: the options menu can still be reached by **right-clicking** a row or pressing **←** while it is selected.
- **Hotkeys:** choose a key or combination for the Quick Menu and for the Applications window, or tap a modifier by itself (Super, Alt, Ctrl, Shift). Super+Enter and every other Super shortcut keep working, because a lone-modifier hotkey is delivered by `xcape` only when the modifier is pressed and released alone. TVWCS writes `~/.config/tvwcs/hotkeys.conf` and reloads i3.
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

- **Nothing appears on the hotkey:** start the controller once (`~/.config/i3/tvwcs/bin/tvwcs`), then `i3-msg -t get_config | grep -i tvwcs`. If nothing matches, your i3 may be older than 4.20, or `~/.config/tvwcs/hotkeys.conf` is missing (run `install.sh`).
- **A lone-modifier hotkey (Super) does nothing:** install `xcape`; TVWCS runs it for you while it is open.
- **"TVWCS is already running":** `cat "${XDG_RUNTIME_DIR:-/tmp}/tvwcs.pid"`; stop the stale process or delete the file.
- **Menu overlaps your bar or sits in the wrong place:** TVWCS uses the workspace rectangle i3 reports. Raise `settings.margin`, and make sure `xdotool` is installed so the right monitor is chosen.
- **Text too small or too big:** Settings > Interface size.
- **An app is missing from Open applications:** TVWCS lists every normal window except its own and bars/docks. Windows are matched to workspaces by i3; if one is still missing, check `i3-msg -t get_tree` for its title and class.
- **Missing icons or odd glyphs:** install an icon theme such as `adwaita-icon-theme`; TVWCS falls back to text glyphs.
- Stop TVWCS before hand-editing `config.json`.

## Repository layout

```
package/tvwcs/   the application modules (main.py, model.py, ui_*.py, i3 + window managers, ...)
package/bin/     tvwcs — launcher script used by i3 bindings
package/tests/   unit tests that need no display
data/tvwcs.conf  the i3 config fragment installed to ~/.config/i3/tvwcs
scripts/         install.sh, run-tests.sh, make-release.sh
docs/            RELEASES.md (beta -> publish workflow)
assets/        screenshots; resources/ release zips
```

## Development

```sh
./scripts/run-tests.sh          # all 111 unit tests, no display needed
python3 -m unittest discover -s package/tests -t package
```

## Releases (beta and published)

Every push to the `beta` branch automatically builds a downloadable **beta zip** (GitHub Actions
pre-release + artifact); pushing a `v*` tag publishes the final release. No GitHub? Build one
yourself with `./scripts/make-release.sh --beta`. See `docs/RELEASES.md`.

## License

TVWCS is intended to be distributed under the MIT License. See the `LICENSE` file for details.

## Project Notes:
 - This project consists primarily of AI generated code where an AI was given a description of the project to make and then repeatedly given a list of revisions to remake the project to.
 - This project is not distributed with any code of conduct.
 - This project is free to copy, steal, plagiarize, mimic, reference, etc. 
