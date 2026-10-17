# TVWCS: project overview

*Updated for 3.0.*

This document is for people working on TVWCS: what it is meant to do, how it behaves, and how the code is laid out. The user guide is [README.md](README.md).

## Goal

**Make a Linux computer as easy to use from the couch as a TV, without taking control away from Linux or its apps.**

A normal desktop assumes a mouse, a keyboard and a screen at arm's length. On a TV across the room, small controls and taskbars are hard to use. Media centers help, but often need a plugin for each service. TVWCS keeps the computer general-purpose and adds one remote-friendly way to find, start and return to apps.

**TVWCS is:** a TV-style launcher and app switcher; one search for apps, profiles, channels and open windows; a user-made channel list and favorites; a Settings app for what a TV computer needs; built on standard `.desktop` metadata and the i3 / sway IPC.

**TVWCS is not:** an operating system or window manager; a media player (Kodi, VLC, Jellyfin); a promise that every app becomes D-pad friendly; a plugin system; a fixed channel list.

## Design

The look follows Metro (Modern UI): flat and typographic.

- **Square.** No rounded corners, gradients or shadows.
- **Solid colour.** Dark surfaces by default (a light mode is an option), one accent colour (chosen in Settings), large light type, small spaced capitals for section titles. Text contrast is kept high.
- **Clear focus.** The selected item is a solid accent block with a white frame. Dangerous actions turn red.
- **Real icons.** App logos wherever an app is listed; a coloured letter tile when there is none. Symbols where the meaning is universal (⚙ ⏻ ✕ ⊞ ⋯ ≡ ☆ ✎), words elsewhere.
- **Scales to the room.** Desktop, TV Mode (1080p) and 4K TV Mode sizes. The size applies at once.
- **Calm motion.** Short fades, turned off by **Reduce motion**.
- **Everything in one window.** Dialogs, editors, messages and the on-screen keyboard are drawn inside the TVWCS window, so they cannot get lost behind it.
- **Remote first.** Every control is reachable with arrows, OK and Back. In TV mode the key hints name the remote's keys (OK, Back).

## How it behaves

### Layout

TVWCS is one borderless floating window placed in the usable area of the workspace on the monitor under the pointer (i3 already excludes the bar). It holds up to two panels:

- **Quick Menu:** a column at the left, always shown when TVWCS is open. It is full height on a TV and whenever Applications is open. At a desk with Applications closed it is only as tall as its contents, kept in the bottom-left corner with the same margins, and it grows upwards as search results appear.
- **Applications:** opens to the right of it and fills the rest on a TV. At a desk it is only as wide as its rows need (the widest row without its description, plus room for four in five descriptions); a longer description is cut with … and scrolls by while its row is selected, and the pointer shows all of it.

The same margin (the **Screen edge margin**, which also handles TV overscan) separates panels from each other and from the screen edges. TVWCS computes the exact position at run time.

Navigation is spatial. → past the Quick Menu opens Applications; ← goes back. Back/Esc steps back one level: dialog, Applications, Quick Menu. Typing anywhere goes into search.

### Quick Menu

The header is at the top; everything else sits at the bottom, nearest the search field, with any spare height above it. From top to bottom:

- **Header:** ⚙ Settings, ⏻ power menu, ✕ close (⚙ and ✕ can be hidden), ⊞ Applications, then the **key hints**.
- **Favorites:** pinned launch profiles. Hidden when there are none.
- **Open applications, by workspace.** A workspace is the unit you "change channel" between. An app alone on its workspace is listed as that app. Several apps on one workspace are one entry named after its contents ("Brave + Text Editor"). Hidden when nothing is open. With neither favorites nor open apps, a note points to the guide (⊞) for the installed apps.
- **Search results**, listed upwards from the search field: the best match is the one nearest it, and ↑ moves on to the next.
- **Search:** profiles, app names, commands, channel numbers and open windows. Typing a channel number and pressing OK opens it. On a TV the field starts three digits wide with a short hint beside it, and widens for a letter or a fourth digit. OK on the empty field opens the on-screen keyboard (or number keypad).
- **Status row:** clock, network, volume, Bluetooth, waiting updates, and the battery with its charge (charging, plugged in or on battery; only on a computer with a battery). Each opens its Settings page.

Each row has a menu button (⋯), also opened with ← on the row or a right-click. It opens one list of labelled choices in a dialog:

- **App:** open it the other way (tiled here, or in its own workspace), its own `.desktop` actions, Close when it is open.
- **Workspace:** move it to another monitor, expand it into its apps, or close it and everything on it (asks first).
- **Favorite:** its launch mode and `.desktop` actions.

Messages, errors and a "Starting <app>…" card are shown in the window. The first time TVWCS opens it asks whether it is used on a TV or at a desk.

In **TV mode** the i3/sway bar is hidden (the status row replaces it), and while no app is open the Quick Menu stays on screen and returns when the last app closes. Both can be turned off.

### Applications

- **Channels:** every profile with a channel number.
- **All applications:** every installed graphical app from XDG `.desktop` entries, in foldable categories (Media, Internet, Games, Office, Graphics, Development, Utilities, System, Other). Each row shows logo, channel, name and description, then ☆ favorite and ✎ edit.

A **secondary profile** (a second way to start the same app) sits under its app with ↳ in place of the logo, and shows what makes it different (its action or command, or its own description). A lock mark shows a PIN. Edits never make the list jump or fold.

### Launch profiles

An application is the installed program. A launch profile is one way to start it, such as a browser opened on a streaming site. A profile has a name and, optionally, a command, a `.desktop` action, a channel, a favorite flag, a launch mode, a description, a hotkey and a PIN.

- An empty command uses the app's standard launcher. A custom command runs as an argument list, not through a shell.
- The editor opens inside the TVWCS window. Each field is a row that opens the on-screen keyboard, the keypad, a list or hotkey capture. Nothing is stored until **Save**; **Cancel** and **Delete** are beside it. An app's profile list opens the same way.
- **PIN:** asked when launching, or also when showing the app on a workspace that is not on screen. Editing or deleting a protected profile asks for it first. It is a convenience lock, not security.
- **Plain profiles follow renamed apps:** a profile with no changes of its own keeps working when its `.desktop` file is renamed (such as the old Control Panel launcher).

### Where apps open

One setting, **Where apps open**:

- **Full screen, one per workspace:** every app, launched or selected, gets a workspace of its own. The TV default.
- **Side by side:** every app opens tiled beside what is on screen. The desktop default.
- **As each app's profile says:** each profile chooses "tiled here" or "always in a new workspace". The default for config files from before 3.0.

Nothing is moved, closed or minimized: other workspaces are just not shown. An app's options always offer the opposite for one time. TVWCS restores fullscreen on an app that was fullscreen when TVWCS opened over it.

### Switching to open apps

TVWCS focuses an existing window rather than starting a second copy when it can match one. Matching uses window class, instance, `StartupWMClass` and names, so it is best-effort. The window manager stays in charge of windows and workspaces; TVWCS only sends it commands.

### Channels and favorites

Channel numbers (000 to 999) are the user's own shortcuts to profiles. They are unique, optional and stored locally. Channel 000 goes to Settings once, on a new install or the first start of 3.1, when nothing else has it. Favorites are independent of channels.

### Hotkeys

Three sets: keyboard (default: tap Super for the Quick Menu), remote (default: F2) and gamepad (none; needs a mapper such as AntiMicroX). Each has a Quick Menu key and an Applications key; the remote also has a fullscreen key. Any profile can have its own hotkey. A key does one thing: choosing a key already in use warns and asks before moving it. A modifier tapped alone is bound by keycode on release, so Super combinations keep working. While a key is being chosen, the D-pad, OK and Back keep navigating the dialog. Remote media keys are written with their `XF86` names.

### Power and locking

The power menu has Sleep, Reboot and Shut down, Log out when there is a login screen, and Lock when enabled. Reboot, Shut down and Log out ask first, with Cancel selected. Power actions use `systemctl`. When polkit refuses, TVWCS uses a no-password sudo or doas rule (the installer offers a narrow one), else asks for the sudo password in its own dialog and passes it to `sudo -S` without storing it.

Settings keeps idle times for the screen saver (`screensaver.py`, a logo bouncing round a black screen), screen off, lock and sleep (TVWCS watches idle time itself on i3; it runs `swayidle` on sway), and a second set for a laptop on battery, plus what to do when its battery is nearly empty (`power.py` reads `/sys/class/power_supply`). Nothing happens while sound plays or an app inhibits idle. The screen saver ends when the screen turns off.

With "Show it when the computer locks", `tvwcs lock` runs xsecurelock (X11 only) with `tvwcs screensaver --xsecurelock` as its saver: that draws the same logo through Xlib into the window xsecurelock gives it, since GTK cannot draw in another program's window. xsecurelock shows its password box on a key and goes back to the saver after a minute.

The mouse pointer is hidden by TVWCS (`cursor.py`): `unclutter` on i3, `seat * hide_cursor` on sway, after the time in Options (by default on a TV only). On i3 a hidden pointer is moved to the bottom-right corner of the focused window so nothing stays highlighted under it. Only TVWCS's session is affected: its unclutter is stopped by the kernel when TVWCS exits (`PR_SET_PDEATHSIG`), and Debian's `unclutter-startup` (which would start unclutter in every X session) is left out when unclutter-xfixes is installed; `install.sh` offers to turn off an autostart that is already there.

The optional **TVWCS lock screen** (`lockscreen.py`) does not draw a lock itself. It paints one picture per monitor ("Locked — A password is needed. Type <user>'s password, then press Enter to unlock.") and runs i3lock, or swaylock on sway, with it. The power menu's Lock, the idle lock and `tvwcs lock` use it. When the i3 config starts xss-lock, its locker line is replaced too, and restored when the option is turned off.

## Settings app

A separate GTK app (`tvwcs settings [page]`, launcher "TVWCS Settings", hidden in GNOME and KDE menus) in the same style. Pages are tabs on the left: Options, Features, Remote and hotkeys, Sound, Displays, Power and sleep, Bluetooth, Date and time, Apps, Software updates, System information, Terminal, Network, Storage. Each page is also a `.desktop` action, so it can be a channel or favorite.

It drives standard tools rather than services: `pactl` (PipeWire/PulseAudio), `xrandr` or `swaymsg`, `bluetoothctl`, `nmcli` (read-only `ip` fallback), `timedatectl`, apt plus Flatpak, OpenSSH via `systemctl`, and VTE for the terminal. A page whose tool is missing says what to install. Changes TVWCS needs to know about are sent with `tvwcs reload`.

**Features** (`features.py`): the parts that need extra software (sound, Bluetooth, network, storage, terminal, Flathub apps, screen saver, screen saver when locked, hiding the pointer) can be turned off. A page whose feature is off only offers to turn it on, and its Quick Menu icon is hidden. Turning one on installs its packages with apt; turning one off can uninstall them with `apt-get remove`, only after `apt-get -s remove` shows nothing else would go, and never packages TVWCS itself or another feature that is on needs.

## Supported systems

Debian and its family (apt), with systemd. Support for Arch, Fedora, Void, Alpine, Gentoo and non-systemd init systems was removed in 3.0, and openSUSE in 3.0.2. [TODO.md](TODO.md) lists, place by place, what bringing them back would take (the last commit with that code is `9e7ef12`), and holds researched but unstarted work on a tablet mode and a dedicated passwordless TV user.

## Installer

`scripts/install.sh` (POSIX sh) copies the program to `~/.local/share/tvwcs`, adds the Settings launcher, and sets up the window manager. It first asks for the setup, saved in `~/.config/tvwcs/setup`:

- **dedicated:** adds `include ~/.local/share/tvwcs/tvwcs.conf` to the user's i3/sway config (or creates one from the standard template), and, with no display manager, offers automatic login on tty1 (a systemd getty drop-in plus marked lines in the shell's login file that run `startx` or `sway`).
- **alongside:** writes `~/.config/tvwcs/<wm>-session.conf` (template plus the include line) and login screen entries `tvwcs-i3.desktop` / `tvwcs-sway.desktop` that run `/usr/local/bin/tvwcs-session <wm>`. The wrapper exports `TVWCS_SESSION` and `TVWCS_SESSION_CONFIG` so TVWCS knows which config is its own. It never sets up automatic login. Adding the include line to the usual config is optional (default no).

On a first install it asks for everything or a minimal install (`TVWCS_INSTALL`); a minimal one skips the features' packages and turns off the features whose software is missing (`python3 -m tvwcs.features minimal`). Later runs, and `--missing`, leave out the packages of features that are off. It also installs missing packages (including an icon theme and Open Sans), offers i3 or sway when neither is installed, offers the power sudo rule, asks TV or desktop, restarts a running TVWCS and migrates installs from `~/.config/i3/tvwcs` (2.6 and older). Every change to a user file is asked first and backed up as `<file>.tvwcs-backup`. Environment variables are listed at the top of the script.

## Where things live

| What | Where |
|---|---|
| The program | `~/.local/share/tvwcs/` |
| i3 / sway fragment (starts TVWCS, includes hotkeys, window rules) | `~/.local/share/tvwcs/tvwcs.conf` |
| User data and settings | `~/.config/tvwcs/config.json` |
| Hotkeys, written by TVWCS | `~/.config/tvwcs/hotkeys.conf` |
| Kept display settings | `~/.config/tvwcs/displays.json` (i3's scale also in `~/.Xresources` and `~/.config/tvwcs/xsettingsd.conf`) |
| TVWCS's own session configs (alongside) | `~/.config/tvwcs/<wm>-session.conf` |
| PID file and per-session files | `$XDG_RUNTIME_DIR` |

User data is kept apart from the program so upgrades never touch it. TVWCS recognises its own windows by the exact title `TVWCS` or the prefix `TVWCS · `.

## Code

Logic modules have no GTK dependency and are tested without a display.

| Area | Modules |
|---|---|
| Core | `model` (profiles, settings, layout, search), `applications` (discovery, window matching), `workspaces`, `ownership`, `profile_draft`, `pinlock`, `hotkeys` |
| System | `window_manager` (i3 / sway IPC), `system_actions`, `privilege`, `power`, `lockscreen`, `cursor`, `features`, `session`, `tv_mode`, `quick_status`, `selfupdate`, `flatpak_env`, `appearance` (light/dark for apps, background colour), `screensaver` |
| Settings back ends | `control_cmd`, `control_sound`, `control_display`, `control_bluetooth`, `control_network` (+ `ifupdown_handover`, run as root), `control_datetime`, `control_storage`, `control_updates`, `control_flatpak`, `control_ssh`, `control_sysinfo` |
| GTK interface | `main` (app, CLI), `ui_window` (Quick Menu, Applications, dialogs, on-screen keyboard), `ui_editors` (profile editor), `ui_control` and `ui_control_pages` (Settings), `widgets`, `theme` |

```
package/tvwcs/   modules                  package/tests/  unit tests
package/bin/     the tvwcs launcher       data/           tvwcs.conf and the Settings .desktop file
scripts/         install, tests, release  docs/           Debian guide, release process
```

```sh
./scripts/run-tests.sh            # unit tests (no display needed)
./scripts/make-release.sh --beta  # a test zip in resources/
```

Release steps are in [docs/RELEASES.md](docs/RELEASES.md).

## In one paragraph

TVWCS is a Metro-styled, TV-like layer for a Linux computer on a television. A menu at the left shows your favorites, open apps and search; a full list of applications opens beside it. You give apps your own channel numbers and choose whether they open full screen or side by side. It does not replace Linux or apps like Jellyfin and Steam; it sits on top of i3 or sway and makes them usable with a remote, without a plugin for every app.
