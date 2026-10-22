# TVWCS: project overview

*Updated for 3.0.*

This document is for people working on TVWCS: what it is meant to do, how it behaves, and how the code is laid out. The user guide is [README.md](README.md).

## Goal

**Make a Linux computer as easy to use from the couch as a TV, without taking control away from Linux or its apps.**

A normal desktop assumes a mouse, a keyboard and a screen at arm's length. On a TV across the room, small controls and taskbars are hard to use. Media centers help, but often need a plugin for each service. TVWCS keeps the computer general-purpose and adds one remote-friendly way to find, start and return to apps.

**TVWCS is:** a TV-style launcher and app switcher; one search for apps, profiles, channels and open windows; a user-made channel list and favorites; a Settings app for what a TV computer needs; built on standard `.desktop` metadata and the sway IPC.

**TVWCS is not:** an operating system or window manager; a media player (Kodi, VLC, Jellyfin); a promise that every app becomes D-pad friendly; a plugin system; a fixed channel list.

## Design

The look follows Metro (Modern UI): flat and typographic.

- **Square.** No rounded corners, gradients or shadows.
- **Solid colour.** Dark surfaces by default (a light mode is an option), one accent colour (chosen in Settings), large light type, small spaced capitals for section titles. Text contrast is kept high.
- **Clear focus.** The selected item is a solid accent block with a white frame. Dangerous actions turn red.
- **Real icons.** App logos wherever an app is listed; a coloured letter tile when there is none. Symbols where the meaning is universal (⏻ ✕ ⋯ ≡ ☆ ✎), words elsewhere.
- **Scales to the room.** Desktop, TV Mode (1080p) and 4K TV Mode sizes. The size applies at once.
- **Calm motion.** Short fades, turned off by **Reduce motion**.
- **Everything in one window.** Dialogs, editors, messages and the on-screen keyboard are drawn inside the TVWCS window, so they cannot get lost behind it.
- **Remote first.** Every control is reachable with arrows, OK and Back. In TV mode the key hints name the remote's keys (OK, Back).

## How it behaves

### Layout

TVWCS is one borderless floating window placed in the usable area of the workspace on the monitor under the pointer (sway already excludes the bar). It holds up to two panels:

- **Quick Menu:** a column at the left, always shown when TVWCS is open. It is full height on a TV and whenever Applications is open. At a desk with Applications closed it is only as tall as its contents, kept in the bottom-left corner with the same margins, and it grows upwards as search results appear.
- **Applications:** opens to the right of it and fills the rest on a TV. At a desk it is only as wide as its rows need (the widest row without its description, plus room for four in five descriptions); a longer description is cut with … and scrolls by while its row is selected, and the pointer shows all of it.

The same margin (the **Screen edge margin**, which also handles TV overscan) separates panels from each other and from the screen edges. TVWCS computes the exact position at run time.

Navigation is spatial. → past the Quick Menu opens Applications; ← goes back. Back/Esc steps back one level: dialog, Applications, Quick Menu. Typing anywhere goes into search.

### Quick Menu

The header is at the top; everything else sits at the bottom, nearest the search field, with any spare height above it. From top to bottom:

- **Header:** the title and ✕ close (it can be hidden).
- **Favorites and open applications, in one list without headings.** Favorites (pinned launch profiles) come first, in their order; a favorite that is open stands in its place as the open app. Favorites have a grey ★; open apps (and workspaces) a 3 px band down their left side. The other open applications follow, by workspace. A workspace is the unit you "change channel" between. An app alone on its workspace is listed as that app. Several apps on one workspace are one entry named after its contents ("Brave + Text Editor"). With neither favorites nor open apps, a note points to Applications (→) for the installed apps.
- **Search results**, listed upwards from the search field: the best match is the one nearest it, and ↑ moves on to the next.
- **Search:** profiles, app names, commands, channel numbers and open windows. Typing a channel number and pressing OK opens it. On a TV the field starts three characters wide (**___**) with a short hint beside it, and widens for a letter or a fourth digit. OK on the empty field opens the on-screen keyboard (or number keypad).
- **Status rows:** above, waiting updates, network, volume, Bluetooth, the battery with its charge (charging, plugged in or on battery; only on a computer with a battery), and ⏻ power at the right; below, the time with the date to its right, and ⊞. The clock and the updates icon open their Settings page. The others unfold a panel above the row, indented a little, like a row's options:
  - **⏻ Power:** Lock (nearest the button), Sleep, Reboot, Shut down, and Log out when there is a login screen.
  - **Network:** the connection in use (Wi-Fi network and signal, or the wired connection) with its address, Wi-Fi on or off, and Network settings.
  - **Volume:** mute, − and + (and a slider) for the output and the input, and Sound settings.
  - **Bluetooth:** the connected devices, each with Disconnect, Bluetooth on or off, and Bluetooth settings.
  - **Battery:** the charge and about how long until it is empty (or charged), from the kernel's estimate or the rate it drains at, and Power settings.
  Details that need a command (network, Bluetooth, sound) are read in the background; the selection moves into the panel once they arrive. A panel folds away when the selection leaves it and its icon, with Back, or with its icon again.
- **Applications button:** ⊞ in the Quick Menu's bottom-right corner, beside the clock, opens or closes Applications (highlighted while it is open). With a remote, → past the end of a row does the same.

Each row has a menu button (⋯), also opened with ← on the row or a right-click. Its options unfold upwards, above the row, indented a little on both sides, close to their row and with a small gap to the row above. From the top: the app's own `.desktop` actions, opening it the other way, and Close nearest the row (the selection lands on the option just above Close). ↑ from the row goes into them; they fold away when the selection leaves them and their row, with Back, or with ⋯ again:

- **App:** its own `.desktop` actions, open it the other way (alongside the apps on screen, or in its own workspace), Close when it is open.
- **Workspace:** move it to another monitor, or close it and everything on it (asks first). Its ▴ button unfolds its individual apps upwards, above it.
- **Favorite:** its launch mode and `.desktop` actions.

Messages and errors are shown in the window. While an app starts, a spinner takes the place of its icon in its button (a "Starting <app>…" card only when it was started with no button on screen, such as by its hotkey). The first time TVWCS opens it asks whether it is used on a TV or at a desk.

In **TV mode** the sway bar is hidden (the status row replaces it), and while no app is open the Quick Menu stays on screen and returns when the last app closes. Both can be turned off.

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

The power menu has Lock, Sleep, Reboot and Shut down, and Log out when there is a login screen. Reboot, Shut down and Log out ask first, with Cancel selected. Power actions use `systemctl`. When polkit refuses, TVWCS uses a no-password sudo or doas rule if there is one, else asks for the sudo password in its own dialog and passes it to `sudo -S` without storing it.

Settings keeps idle times for screen off, lock and sleep, which TVWCS hands to `swayidle` (each timeout calls `tvwcs idle <action>` back), and a second set for a laptop on battery, plus what to do when its battery is nearly empty (`power.py` reads `/sys/class/power_supply`). Nothing happens while sound plays or an app inhibits idle.

The mouse pointer is hidden by sway (`seat * hide_cursor`, `cursor.py`), in TV mode only.

The **lock screen** (`lockscreen.py`), used in TV mode only, is swaylock on a dark background with a ring in the accent colour. The power menu's Lock, the idle lock and `tvwcs lock` use it. A desktop session's lock screen is never changed.

## Settings app

A separate GTK app (`tvwcs settings [page]`, launcher "TVWCS Settings", hidden in GNOME and KDE menus) in the same style. Pages are tabs on the left: Appearance, User, Remote and hotkeys, Sound, Displays, Power and sleep, Bluetooth, Date and time, Software updates, System information, Network, Storage. Each page is also a `.desktop` action, so it can be a channel or favorite.

It drives standard tools rather than services: `pactl` (PipeWire/PulseAudio), `swaymsg`, `bluetoothctl`, `nmcli` (read-only `ip` fallback), `timedatectl`, apt, `udisksctl` and OpenSSH via `systemctl`. A page whose tool is missing says what to install. Changes TVWCS needs to know about are sent with `tvwcs reload`.

**Software a page needs** (`features.py`): a page whose software is missing (sound, Bluetooth) offers to install it with apt; there is no on/off switch, and its Quick Menu icon is hidden until it is installed.

## Supported systems

Debian and its family (apt), with systemd. Support for Arch, Fedora, Void, Alpine, Gentoo and non-systemd init systems was removed in 3.0, and openSUSE in 3.0.2. [TODO.md](TODO.md) lists, place by place, what bringing them back would take (the last commit with that code is `9e7ef12`), and holds researched but unstarted work on a tablet mode and a dedicated passwordless TV user.

## Packages and installer

One repository and one Debian package, built by `scripts/build-debs.sh` with plain `dpkg-deb` (no compiling) and attached to each GitHub release:

**tvwcs**: the Python package in `/usr/lib/tvwcs`, `/usr/bin/tvwcs`, `/usr/bin/tvwcs-session` (TVWCS's sway session: it makes `~/.config/tvwcs/sway-session.conf` from `/etc/sway/config` the first time, with its bar commented out so swaybar never starts, writes default hotkeys, exports `TVWCS_SESSION` and runs sway), the session entry `tvwcs-sway.desktop`, `/usr/share/tvwcs/tvwcs.conf` and the Settings launcher. Its dependencies are what apt installs with it. It conflicts with 5.0.x's tvwcs-boot-logo, so apt removes that.

There is no login screen of TVWCS's own (from 5.0). `loginscreen.py` sets the automatic login where the login screen in use keeps it: greetd's initial session, LightDM's or SDDM's settings. Without a login screen, the installer sets up greetd with its text login (agreety). `loginscreen.py migrate` removes 4.x's greeter: another graphical login screen takes over, else greetd's text login, keeping the automatic login.

`install.sh` (POSIX sh, at the repository root) runs in a terminal, on its own (`wget -qO- …/main/install.sh | bash`, then it downloads the chosen release's packages) or from an unpacked `tvwcs.tar.gz` (it then offers the packages next to it). It asks everything first (version, automatic login, desktop mode in the usual sway config), then installs with apt. Upgrading from 4.x it removes `~/.local/share/tvwcs` and what 4.x put elsewhere (its session files, i3 include lines, console start lines). Without a terminal (4.x's in-app updater) it says to run it in one. `--remove` purges the packages. The in-app updater (`selfupdate.py`) downloads the release's .deb files and installs them with `apt-get install` as root.

## Where things live

| What | Where |
|---|---|
| The program | `/usr/lib/tvwcs/` (`/usr/bin/tvwcs`, `/usr/bin/tvwcs-session`) |
| sway fragment (starts TVWCS, includes hotkeys, window rules) | `/usr/share/tvwcs/tvwcs.conf` |
| User data and settings | `~/.config/tvwcs/config.json` |
| Hotkeys, written by TVWCS | `~/.config/tvwcs/hotkeys.conf` |
| Kept display settings | `~/.config/tvwcs/displays.json` |
| TVWCS's own session config (TV mode) | `~/.config/tvwcs/sway-session.conf` |
| PID file and per-session files | `$XDG_RUNTIME_DIR` |

User data is kept apart from the program so upgrades never touch it. TVWCS recognises its own windows by the exact title `TVWCS` or the prefix `TVWCS · `.

## Code

Logic modules have no GTK dependency and are tested without a display.

| Area | Modules |
|---|---|
| Core | `model` (profiles, settings, layout, search), `applications` (discovery, window matching), `workspaces`, `ownership`, `profile_draft`, `pinlock`, `hotkeys` |
| System | `window_manager` (sway IPC), `system_actions`, `privilege`, `power`, `lockscreen`, `cursor`, `features`, `session`, `tv_mode`, `quick_status`, `selfupdate`, `loginscreen`, `account`, `appearance` (light/dark for apps, background colour) |
| Settings back ends | `control_cmd`, `control_sound`, `control_display`, `control_bluetooth`, `control_network`, `control_datetime`, `control_storage`, `control_updates`, `control_ssh`, `control_sysinfo` |
| GTK interface | `main` (app, CLI), `ui_window` (Quick Menu, Applications, dialogs, on-screen keyboard), `ui_editors` (profile editor), `ui_control` and `ui_control_pages` (Settings), `widgets`, `theme` |

```
package/tvwcs/   modules                  package/tests/  unit tests
package/bin/     the tvwcs launcher       data/           tvwcs.conf, the session, the Settings .desktop file
scripts/         tests, packages, release packaging/      each package's control file and scripts
docs/            Debian guide, release process
```

```sh
./scripts/run-tests.sh            # unit tests (no display needed)
./scripts/build-debs.sh           # the .deb packages in resources/
```

Release steps are in [docs/RELEASES.md](docs/RELEASES.md).

## In one paragraph

TVWCS is a Metro-styled, TV-like layer for a Linux computer on a television. A menu at the left shows your favorites, open apps and search; a full list of applications opens beside it. You give apps your own channel numbers and choose whether they open full screen or side by side. It does not replace Linux or apps like Jellyfin and Steam; it sits on top of sway and makes them usable with a remote, without a plugin for every app.
