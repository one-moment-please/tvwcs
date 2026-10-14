# Changelog

## Unreleased

**Hotkeys**
- The remote set has a new *Fullscreen* key (unset by default) that toggles fullscreen on the focused app. It never acts on TVWCS's own windows.
- The remote's Applications key now starts unset (it was Shift+F2). A key you already chose is kept.
- Any launch profile can have a hotkey that launches it, set in its editor (`tvwcs launch <profile id>` from a terminal). A profile with a PIN shows the Quick Menu to ask for it.
- New *Application hotkeys* section in Settings: it counts the mapped application hotkeys and opens a list where each can be changed or removed.
- Choosing a key that is already used (by another device slot or an application) now warns and asks for confirmation, then moves the key, instead of refusing it.

**Behavior**
- New setting *Always open apps in a new workspace*: every app, launched or selected while open, gets a workspace of its own.
- An app that was fullscreen when TVWCS opened is made fullscreen again when TVWCS closes or switches to it.
- Clicking the TVWCS window while a profile editor or the application profiles window is open closes those windows (unsaved changes are dropped), instead of leaving TVWCS in front and frozen.

**Install**
- TVWCS now installs into `~/.local/share/tvwcs` (it was `~/.config/i3/tvwcs`); your data stays in `~/.config/tvwcs`. `install.sh` points `tvwcs.conf`'s exec line at wherever it installs, so `TVWCS_DEST` needs no hand edit any more.
- `install.sh` offers (asking first, and backing the file up as `config.tvwcs-backup`) to add the include line to your i3 and/or sway config, and reloads the window manager if it is running.
- An install in the old location is moved: the include line is updated after asking, hotkeys point at the new launcher, and the old copy is deleted after asking once nothing uses it. *Check for updates* moves it too, after saying so in its confirmation.
- With no i3 or sway config, `install.sh` offers to create one from the standard template (i3-config-wizard's, or sway's), asking for the `$mod` key (Super or Alt) and whether to use the current keyboard layout or another one.

**sway**
- TVWCS runs on sway: it uses `swaymsg`, lists native Wayland windows (by app_id), and takes the monitor from sway's focus instead of xdotool.
- Opening TVWCS over a fullscreen app takes the app out of fullscreen while TVWCS is open (sway would otherwise keep TVWCS hidden behind it); it is made fullscreen again when TVWCS closes.

**At login**
- New setting *Open the Quick Menu at login* (off by default): shows the Quick Menu once per login, after the login app if one is chosen.

**Quick Menu**
- Typing a three-digit channel number and then nothing for a second launches that channel, without Enter.

**Display**
- The interface sizes are now *Desktop*, *TV Mode* and *4K TV Mode*. 4K TV Mode is only offered when a 4K or larger display is connected (or when it is already the chosen size).

## 2.6.0 — 2026-10-14

**Applications pane**
- Removed the Networking and Updates tabs (and their `network`, `updates`, `ui_network`, `ui_updates` modules); TVWCS no longer needs NetworkManager or apt.
- No more tab bar: the pane always opens on the applications guide, and a button at its top right switches between the guide and Settings. Esc in Settings returns to the guide.
- Settings rows are reachable with the arrow keys again (they were registered with a panel that no longer exists).

**Settings**
- New *Check for updates*: looks up the latest published GitHub release, and if it is newer asks whether to install it, then downloads it to a temporary folder, runs its `install.sh` over the current install (your data is kept), deletes the download and restarts TVWCS.

**Quick Menu rows**
- ← on a favorite, search result, open application or workspace opens its options, with the option next to it selected. The options close again as soon as the selection moves away from them (they stay open while a pop-up or confirmation opened from them is up).
- The options button is a ☰ and every option inside is a square button.

**Look and feel**
- Every close button is red.
- The Quick Menu's close and Applications buttons are square, and the Applications button (now a ☰ menu symbol) lines up with the right edge of the search field.
- *Your channels* is now *Channel Guide*. Each application's Edit button is a ✎ symbol, and it and the favorite star are square.
- New *Button hints* setting (off by default): an icon-only button selected for 3 seconds shows its tooltip for 6 seconds.

**Hotkeys: one set per device**
- A modifier tapped on its own (the default keyboard hotkey, Super) is now bound directly in i3 as `bindcode --release <keycode>`, using the keyboard's real keycode. xcape is no longer used or needed; it depended on spare F13/F14 keys that many keyboard layouts do not define.
- Separate hotkeys for the keyboard, the remote and a gamepad, each with a Quick Menu key and an Applications key. Defaults: keyboard taps Super for the Quick Menu; remote keeps F2 / Shift+F2; gamepad is unset (map its buttons to keys with a tool such as AntiMicroX, then capture them).
- Any hotkey can be cleared from its capture dialog, and a key can only be used once across all sets.
- An existing single hotkey pair is kept as the remote set.

**Settings layout**
- Settings uses the pane's width: two columns (Display and Behavior; Hotkeys, At login and Updates), with the System actions in a grid across the bottom. ← and → jump between the columns; ↑ and ↓ stay in one.

**Install and release**
- README rewritten: shorter, screenshots side by side with descriptions, and the zip install now extracts into a temporary folder instead of `~/.config/i3/`.
- The installed copy reports its real version (it read `VERSION` from the wrong folder).
- `install.sh` notices a running TVWCS and, after asking (Y/n), restarts it on the version just installed (through i3 when i3 is running). Without a terminal it only says how to restart; the in-app updater skips this and restarts TVWCS itself.
- `make-release.sh` replaces an existing zip of the same name instead of adding to it.

**Quick Menu**
- Swapped the positions of the "＋ ›" (open applications) button and the "✕" (close) button in the Quick Menu header; keyboard focus order follows the new left-to-right layout.

## 2.5.0

**Removed: launching a profile as another Linux user** (the same result is available with a custom launch command). The *Launch as user* choice, the password prompt, the `runas` module and its tests are gone, along with the `.desktop` action command parsing that only it used. Old config files that contain a `run_as_user` key load fine; the key is ignored and dropped on the next save.

**PIN-protected profiles (replaces it)**
- Any profile can be protected with a 4–8 digit PIN of its own, set in the profile editor. PINs are stored only as salted hashes.
- Choose when it is asked: *only when launching*, or *when launching and when showing it* — bringing up an open app (or a workspace holding one) from a workspace that is not on screen. Showing an app that is already visible never asks.
- The PIN is entered on an on-screen keypad that works with the D-pad (digit keys and Backspace work too). Five wrong tries lock that profile for 30 seconds. Protected profiles carry a lock mark in the Guide and Favorites.
- Changing or deleting a protected profile needs its current PIN, and the application's own desktop actions respect the main profile's PIN, so neither is a way around the lock.
- Which profile an open window belongs to is remembered when TVWCS launches it (for this session); a window TVWCS did not launch falls back to its application's main profile.
- The app chosen under *At login* is opened without a PIN, since the owner chose it in Settings.
- This is a convenience lock for a shared TV, not strong security: anyone who can edit `~/.config/tvwcs/config.json` can remove it.

**Descriptions can be overridden**
- The application's page (Guide > Edit on a main profile) has a Description field; empty uses the `.desktop` description, shown as the hint.
- A secondary profile's editor has its own Description field; empty shows its launch options (action and command).

**Settings**
- Multiple-choice settings (Interface size, Open at login) now open a small pop-up of the choices with the current one ticked, instead of cycling.
- Choosing an app for *Open at login* lists Favorites first, then apps with channel numbers, then everything else.

**Remote**
- The browser Back key (XF86Back) works exactly like Esc: it closes dialogs, Settings, the Guide and the Quick Menu in turn, cancels hotkey capture and the PIN keypad, and dismisses pop-up menus.

**Code**
- New `pinlock` (hashing and the try limit) and `ownership` modules; 111 tests.

## 2.4.0

**Bug fix: apps missing from Open applications**
- TVWCS used to hide any window whose title *began with "tvwcs"* (meant for its own dialogs). Opening a document called `tvwcs.conf`, `TVWCS notes.txt` and so on made the editor disappear from the list. TVWCS's own windows are now recognised by an exact title (`TVWCS`) or the distinctive prefix `TVWCS · `, so no other app's window can match. Windows with no title are also kept (listed by their class) instead of dropped.

**Navigation**
- Pressing Right at the end of a Quick Menu row opens the Guide (or moves into it if it is open). Past the end of the Guide it opens Settings; Left in Settings closes it and returns to the Guide.
- Pressing Left on a Quick Menu row's options button expands that row's options.
- Typing anywhere in TVWCS goes into the search field and searches. (Not while a dialog is open, in another text field, or with Ctrl/Alt/Super held.)

**Quick Menu: workspace-centric**
- Favorites now sit *below* Open applications.
- Open applications lists workspaces, not windows. An app alone on its workspace is listed as that app; apps sharing a workspace are grouped into one entry named after what is in it ("Brave + Text Editor").
- A workspace entry's options (left): move to another monitor (only shown when there is another monitor; offers a choice of monitors), expand into its individual apps (to open just one, or use that app's own options), and close the workspace and all its apps (asks first).
- An open app's options now include opening it the other way: tiled in the current workspace, or in a workspace of its own.

**Guide**
- Secondary profiles show a "↳" mark in the logo's place and list their `.desktop` action, custom command and run-as user instead of the application's description.
- A Settings button at the top right of the Guide opens a third panel, as wide as the Quick Menu. The Guide now fills only the middle.
- Secondary profiles can be launched as another Linux user (see below).

**Settings panel (new; the System menu moved here)**
- Interface size: Desktop, 10-foot (1080p TV), 10-foot (4K TV).
- Close when clicking outside TVWCS.
- Open running apps in a new workspace (instead of tiling them into the current one). Apps individually set to always launch in a new workspace are unaffected.
- Hotkeys: choose the keys that show the Quick Menu and the Guide. A lone modifier such as Super can be used and does not break Super+key shortcuts (uses xcape). Written to `~/.config/tvwcs/hotkeys.conf`, which `tvwcs.conf` includes.
- At login: open a chosen app, or reopen the last app, once per login.
- System: Lock, Refresh applications, Sleep, Log out, Reboot, Shut down (the last three still confirm). The System button is gone from the Quick Menu header.

**Run a profile as another user**
- Secondary profiles have a *Launch as user* choice. If sudo allows it without a password the app just starts; otherwise a password prompt appears. Authentication uses `su` over a pseudo-terminal; the app is given access to your X display with `xhost`.

**Code**
- Split into smaller modules: `widgets`, `theme`, `ui_window`, `ui_settings`, `ui_editors`, `main`, plus `hotkeys`, `workspaces`, `runas`. 90 tests, including navigation tests that run without a display.

**Upgrade notes**
- `tvwcs.conf` no longer binds keys; run `install.sh` (or create `~/.config/tvwcs/hotkeys.conf`) so its `include` line has a file to read. Dialog titles changed to start with `TVWCS · `, matching the new window rules in `tvwcs.conf`; replace your copy of that file.
- `config.json` gains settings keys and a per-profile `run_as_user`; older files load unchanged.

## 2.3.1

- **Guide navigation fixed.** Application categories are now focusable header buttons (▾ open / ▸ closed) instead of expanders. The focused category is highlighted like every other control, Enter folds or unfolds it, and Up/Down/Left/Right work on every application inside it. (The old behaviour came from the category being treated as the owner of the rows inside it, and from its focus not being styleable.)
- **Descriptions in the Guide.** Application rows (and the channel lineup) show the application's description beside its name, in a smaller, dimmer font.
- **Quick Menu rows mirror the Guide.** Favorites, open applications and search results now have one options button on the *left*. It expands in place into launch mode, desktop actions (only when the app has any) and, for open windows, close. The application button stays on the right and is where Up/Down lands. From the search field, Right at the end of the text jumps to the highlighted result's options; Left returns to typing.
- **No more jumping when favoriting.** Starring or un-starring now updates the star and the Quick Menu's favorites in place. The Guide keeps its scroll position, focus and open categories. Open categories and scroll position are also kept when a profile is edited or applications are refreshed; a freshly opened Guide starts at the top.

## 2.3.0

**Look and layout**
- Metro / Modern UI theme: flat solid colours, light Segoe-style type, square 90° corners on every button, entry, popover and dialog, and a solid accent block with a white frame for remote focus. The accent colour is a setting.
- The Quick Menu is now a full-height column at the left of the active workspace, with the same margin on the top, bottom and left. Geometry comes from the usable rectangle of the workspace on the pointer's monitor (bar excluded), so it works on any monitor.
- The Guide is no longer a separate mode. It opens beside the Quick Menu in the same window, fills the rest of the workspace and keeps the same margin on every side. The Quick Menu is always open while the Guide is, but can be open alone. Shift+F2 opens the Guide; pressing it again, or Esc, closes only the Guide.
- Left/Right at the edge of a row hops between the Quick Menu and the Guide.

**System controls**
- The System button is now a power icon grouped with the Close button, as a caption-button pair.
- Refresh moved into the new System dialog, and a Lock action was added (auto-detects swaylock, i3lock, cinnamon-screensaver, xdg-screensaver or loginctl; override with `settings.lock_command`).
- Log out, Reboot and Shut down now ask for confirmation first. Cancel is focused by default and Esc returns to the System dialog.

**Workspaces**
- New per-profile launch mode: *Always launch in a new workspace* (checkbox in the profile editor). Such apps open alone on a fresh workspace; everything else stays on its own workspace, out of sight.
- A mode icon beside the app name in the Quick Menu (favorites and open applications) flips that app between "own new workspace" and "tiled in the current workspace".
- Open Applications now lists every workspace holding more than one app, with member icons. Open shows the whole workspace on the pointer's monitor; on multi-monitor setups a button moves it to the next screen.

**Icons and badges**
- Application logos are used in favorites, search results, the Guide and open-window rows, with a coloured letter tile when no icon is found.
- Open windows show a badge for an unread count in the title (`(3) Inbox`) or i3's urgent flag.
- `.desktop` `StartupWMClass` is read, which makes window-to-app matching (and so icons and launch modes for open windows) more accurate.

**Install**
- Recommended location is `~/.config/i3/tvwcs`. i3 loads `tvwcs.conf` from that folder through one `include` line; it holds the startup, key bindings and window rules. `install.sh` copies the files into place.

**Behaviour changes to know about**
- The scratchpad-hiding "exclusive" launch behaviour is gone; workspaces replace it. The old `tile` field is ignored, and every existing profile loads as "tiled in the current workspace" (the new default). Mark apps that should be alone with the new checkbox or the Quick Menu icon.
- `config.json` is now version 2 and gains an optional `settings` block (`margin`, `quick_width`, `accent`, `lock_command`). Older files load unchanged.
- `i3.conf.tvwcs` is replaced by `tvwcs.conf`.

## 2.2.0

- Simplified guide rows to one line per launch profile: channel (or dash), clickable profile name, favorite toggle, and edit control.
- Moved profile creation into an application profile-management page with a compact `+` button.
- Parsed named `Desktop Action` entries from `.desktop` files and added a None/desktop-action selector to profile editing.
- Added a Quick Menu System popover with Log out, Sleep, Shut down, and Reboot.
- Left-aligned favorite and open-application controls; added close and desktop-action controls for open windows.
- Search-result highlighting integrated with Up/Down navigation while focus stays in the search field.
- Added a persisted optional `desktop_action` field.

## 2.1.0

- Higher-visibility remote focus, vertical guide navigation, per-profile tile option, mouse-monitor targeting, bar/dock windows excluded from the open-application list.
