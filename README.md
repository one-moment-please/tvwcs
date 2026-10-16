# TVWCS

TVWCS (TV Window Channel Switcher) lets you use an ordinary Linux computer from the couch with a remote. It runs on top of the i3 or sway window manager and gives you:

- a **Quick Menu** at the bottom left of the screen: your favorites, your open apps, search, and a status row with the clock, network, sound, Bluetooth and battery;
- an **Applications** pane beside it: every installed app by category, plus your own numbered **Channels**;
- a **Settings** app for the things a TV computer needs: sound, displays, Wi-Fi, Bluetooth, power, updates and more.

It works with normal desktop apps. It is not a media center and needs no plugins. What's new is in [CHANGELOG.md](CHANGELOG.md).

<table>
  <tr>
    <th width="25%">Quick Menu</th>
    <th width="75%">Quick Menu and Applications</th>
  </tr>
  <tr>
    <td valign="top"><img src="assets/quick-menu.png" alt="The TVWCS Quick Menu" width="100%"></td>
    <td valign="top"><img src="assets/guide-menu.png" alt="The Quick Menu with the Applications pane open beside it" width="100%"></td>
  </tr>
  <tr>
    <td valign="top">Buttons at the top: ⚙ Settings, ⏻ power menu, ✕ close, ⊞ Applications. Below: <b>Favorites</b>, <b>Open applications</b> (by workspace; ▾ shows the apps that share one), then the search field. At the bottom: the clock, and icons for network, volume, Bluetooth and updates.</td>
    <td valign="top"><b>Channels</b> lists apps you gave a number. <b>All applications</b> lists every app by category; OK/Enter folds a category. ☆ makes an app a favorite, ✎ edits its launch profiles.</td>
  </tr>
  <tr>
    <th colspan="2">Settings › Options</th>
  </tr>
  <tr>
    <td colspan="2"><img src="assets/options.png" alt="The Options page of the Settings app" width="100%"></td>
  </tr>
  <tr>
    <td colspan="2" valign="top">Each row shows its current value on the right. OK/Enter changes it.</td>
  </tr>
</table>

### Demo videos

The apps in these videos are mockups made for the demo (a window with a still picture), labelled MOCKUP on screen. Click a picture to play its video.

<table>
  <tr>
    <th width="50%">TV mode</th>
    <th width="50%">Desktop mode</th>
  </tr>
  <tr>
    <td valign="top"><a href="assets/demo-tv-mode.mp4"><img src="assets/demo-tv-mode.jpg" alt="Play the TV mode demo video" width="100%"></a></td>
    <td valign="top"><a href="assets/demo-desktop-mode.mp4"><img src="assets/demo-desktop-mode.jpg" alt="Play the desktop mode demo video" width="100%"></a></td>
  </tr>
  <tr>
    <td valign="top">With the remote: open an app by its channel number, open a second one by channel, go back to the first from <b>Open applications</b>, and open a third by searching its name. Each app gets a workspace of its own.</td>
    <td valign="top">With the keyboard and mouse, in the light theme: open apps by name so they tile side by side, fill a second workspace, switch between workspaces from the Quick Menu, then close one app and a whole workspace.</td>
  </tr>
</table>

## What you need

- **Debian or a Debian-based system** (Ubuntu, Linux Mint, Pop!_OS, Raspberry Pi OS).
- **systemd.**
- i3 4.20 or newer, or sway. The installer can install i3 for you.
- Python 3.9 or newer with GTK 4 (PyGObject). The installer lists and installs anything missing.

Other distributions and systems without systemd are not supported. [TODO.md](TODO.md) records what it would take to bring them back.

**On a system that isn't Debian-based**, TVWCS's own windows may still run if you install its packages by hand, but:

- the installer can't install anything: it only knows apt and Debian's package names, so it lists what is missing and stops;
- **Software updates** can't check for or install system updates (apt only); Flatpak and TVWCS's own updates still work;
- **System information** can't install the SSH server, and **Apps** can't install Flatpak itself;
- **Network** can't take over an Ethernet port set up in `/etc/network/interfaces` (Debian's ifupdown);
- the hints that name a missing tool give Debian's package names;
- without systemd, Sleep, Reboot and Shut down, the network-time switch, starting PipeWire and the SSH switch don't work, and the installer can't set up automatic login.

**New computer?** [Setting up a TV computer with Debian](docs/INSTALL-DEBIAN.md) goes from an empty computer to one that boots into TVWCS.

## Install

Download the latest release of TVWCS into a temporary folder and run its installer. It installs into `~/.local/share/tvwcs`. Your own data (channels, favorites, settings, hotkeys) is kept separately in `~/.config/tvwcs/`.

```bash
cd "$(mktemp -d)"
wget -qO- https://github.com/one-moment-please/tvwcs/releases/latest/download/tvwcs.tar.gz | tar -xz
./tvwcs/install.sh
```

Other ways:

- **With curl:** replace `wget -qO-` with `curl -fsSL`.
- **A specific release or a prerelease:** download `TVWCS-<version>.zip` from [Releases](https://github.com/one-moment-please/tvwcs/releases), `unzip TVWCS-*.zip`, then `./tvwcs/install.sh`.
- **The development version (`main`), for testing:** `git clone https://github.com/one-moment-please/tvwcs && cd tvwcs && ./scripts/install.sh`. It can include changes that have not been tested on a TV yet.
- **Over SSH:** sign in with `ssh -t` so the installer can ask its questions.

You can delete the downloaded folder afterwards.

### What the installer asks

It first prints what it found (for example `Found: no login screen, no desktop sessions, i3 installed, sway not installed.`). Then it asks how TVWCS should be set up:

1. **This computer is only for TVWCS.** It can log you in automatically at start-up and go straight into TVWCS, like a TV. It adds one `include` line to your i3/sway config (or creates a config). Automatic login is off unless you say yes: anyone who switches the computer on gets your session.
2. **Next to my other desktops.** It adds **TVWCS (i3)** and/or **TVWCS (sway)** to your login screen. That session uses its own config in `~/.config/tvwcs/`, so your usual i3 or sway is not changed. It never sets up automatic login. Adding TVWCS to your usual i3/sway config as well is a separate question, and the default is no.

**TVWCS's login screen.** TVWCS has a login screen of its own in its look: it shows who can log in, takes the password from a keyboard or from the remote on an on-screen keyboard (the full one, or a number pad for a password of digits), and starts i3, sway or any other desktop installed. It runs on [greetd](https://sr.ht/~kennylevinsen/greetd/) and cage, which the installer installs. With no login screen on the computer, the installer installs it unless you say no (Enter is yes). Automatic login still works with it: the login screen then only shows after logging out. Next to another login screen it is only offered, and the default is no. **Settings › Features** turns it on or off later.

Some login screens, such as LightDM (Linux Mint's), cannot reliably start Wayland sessions like sway. When yours is one of them, the installer warns before setting TVWCS up for sway and offers, in order: TVWCS's login screen, SDDM (a standard one that starts both), keeping yours anyway, or leaving sway out. i3 works with any login screen.

Hiding the mouse pointer only affects TVWCS's own session. If unclutter was set up to start in every X session (Debian's `unclutter-startup` package, which earlier TVWCS versions installed along with `unclutter-xfixes`), the installer offers to turn that off.

On a first install it also asks **what to install**: everything TVWCS can use, or a **minimal install** with the Quick Menu, the applications list and basic Settings. A minimal install leaves out the software of the optional features (sound, Bluetooth, network, storage, the terminal, Flathub apps, the screen saver, hiding the pointer) and turns off those whose software is missing. **Settings › Features** turns them on later.

After that it may ask to:

- install i3 (with Xorg) or sway, if neither is installed;
- install missing packages, each listed with what it is for (GTK, sound, the Settings app's tools, an icon theme, the Open Sans font);
- create an i3/sway config, choosing the `$mod` key and keyboard layout;
- install TVWCS's login screen (see above);
- let TVWCS sleep, reboot and shut down without your password (adds a narrow sudo rule; default no);
- whether TVWCS is used on a TV or a desktop monitor.

It asks before changing any of your files and saves a copy as `<file>.tvwcs-backup` first.

**Settings for scripted installs:** `TVWCS_SETUP=dedicated` or `alongside` answers the first question. `TVWCS_INSTALL=full` or `minimal` answers what to install. `TVWCS_WMS=i3` (or `sway`) sets up only that window manager. `TVWCS_DEST=<folder>` installs somewhere else. `TVWCS_ASSUME_YES=1` answers yes to adding TVWCS to your configs and the login screen (it never installs packages). `TVWCS_NO_RESTART=1` skips restarting a running TVWCS.

## Using it with a remote

Most remotes act like a keyboard. TVWCS names their keys in its hints: **OK** is Enter, **Back** is Esc.

| Key | What it does |
|---|---|
| **F2** on a remote, or tap **Super** on a keyboard | Show or hide the Quick Menu |
| **↑ ↓ ← →** | Move. **→** past the Quick Menu opens Applications |
| **OK** / Enter | Open, switch to or choose the selected item |
| **Back** / Esc | Go back one step |
| **OK** on the empty search field | Open the on-screen keyboard (or number keypad) |
| Any letter or digit | Search. A channel number (000 to 999) then OK opens that channel. On a TV the search field starts three digits wide; typing a letter or a fourth digit widens it |
| **←** on a Quick Menu row (or right-click) | Open that row's menu |

- **First start:** TVWCS asks whether it is used on a TV or at a desk. This sets the interface size and how apps open.
- **Quick Menu layout:** the title and buttons are at the top; your favorites, open apps, search and the status row are at the bottom, with search results appearing above the search field. A section with nothing in it is hidden. At a desk the Quick Menu is only as tall as what it shows; opening Applications stretches it to the full height.
- **Row menu (⋯):** one menu of labelled choices: open the app in a new workspace or this one, start it with one of its own shortcuts, close it, or move a workspace to another monitor.
- **Workspaces with several apps:** the square ▾ button between ⋯ and the workspace's name shows its individual apps, to open just one; ▴ hides them again. It stays visible even when the ⋯ buttons are hidden. On the name, ← moves onto it; ← again opens the row's menu.
- **Channels:** 000 to 999. Channel 000 opens Settings unless you give it to another app. Setting a channel shows three digit boxes; typing replaces the number.
- **Slow apps:** while an app takes a few seconds to open, TVWCS shows "Starting…" so the screen is never blank, and the Quick Menu still opens.
- **Launch profiles (✎):** a profile is one way to start an app. It can have a channel number, a hotkey, a custom command, a description and a PIN. The editor opens inside the TVWCS window: each field is a row, with Save, Cancel and Delete at the bottom. A PIN-protected profile asks for its PIN first. The PIN is a lock for a shared TV, not real security.
- **Power menu (⏻):** Sleep, Reboot, Shut down; Log out when there is a login screen; Lock when switched on in Options. If a power action needs your password, TVWCS asks for it on screen and never stores it.
- **Other keys:** set keys for Applications, fullscreen, a gamepad or any app in **Settings › Remote and hotkeys**. A gamepad needs a key mapper such as AntiMicroX.

From a terminal, `~/.local/share/tvwcs/bin/tvwcs` takes `toggle`, `guide`, `stop`, `lock`, `launch <profile id>` or `settings [page]`.

## Settings

Open **TVWCS Settings** with ⚙ in the Quick Menu, from Applications (under System), or with `tvwcs settings [page]`. Pages are tabs on the left: **→** enters a page, **Back** returns to the tabs. Text is typed on a keyboard or on the on-screen keyboard.

| Page (`tvwcs settings …`) | What it does |
|---|---|
| **Options** (`options`) | TV or desktop monitor (TV also turns on button hints), hiding the mouse pointer after a few seconds without moving (on by default on a TV, off at a desk; a hidden pointer is moved to the corner of the window so nothing stays highlighted), light or dark mode (dark by default; passed on to apps that follow the system's choice), background colour, interface size (applies at once), accent colour, screen edge margin for TVs that cut off the edges (overscan), Reduce motion, Quick Menu buttons, where apps open (full screen one per workspace, side by side, or as each app's profile says), what opens at login, and whether password dialogs open with the full keyboard or a number pad (the one a password was last typed on; the full keyboard at first). |
| **User** (`user`) | Your name (as the login screen shows it) and password, whether you are an administrator, the login screen in use, and whether the computer logs you in by itself at start-up. With TVWCS's login screen, LightDM, SDDM or no login screen, Settings turns the automatic login on and off; with others, use their own settings. |
| **Features** (`features`) | Turn the features that need extra software on or off: sound, Bluetooth, network, storage, the terminal, Flathub apps, the screen saver, the screen saver when locked, and hiding the pointer. Turning one on installs what it needs. Turning one off can also uninstall its packages, but only when nothing else installed needs them. A feature that is off keeps its tab, which offers to turn it on. |
| **TVWCS login screen** (in Features) | Turn TVWCS's login screen on (it installs greetd and cage) or off. Off goes back to the login screen used before. With none to go back to, it asks whether to have no login screen (log you in and start TVWCS by itself) or to install a standard one (SDDM, or LightDM for i3 only). Under sway, going back to a login screen that cannot start sway warns and offers SDDM instead. Changes show from the next start. When the login screen's copy of TVWCS is older than TVWCS, or its colours differ, it offers to update it. |
| **Remote and hotkeys** (`hotkeys`) | Keys for the keyboard, remote and gamepad, and apps that have their own hotkey. |
| **Sound** (`sound`) | Volume, mute, and output (speakers, HDMI, headphones) and microphone. |
| **Displays** (`displays`) | Resolution, refresh rate and arrangement. A change goes back after 15 seconds unless you keep it. |
| **Power and sleep** (`power`) | When the screen saver starts, the screen turns off, the computer locks and it sleeps. A laptop has these times twice, plugged in and on battery, and a choice of what to do when the battery is nearly empty. The screen saver is a bouncing DVD logo, TVWCS's logo or a picture of your own, and can also show while the computer is locked (i3, with xsecurelock). It never runs while the screen is off. The lock screen to use. |
| **Bluetooth** (`bluetooth`) | Pair, connect and forget devices. Shows battery levels. |
| **Date and time** (`datetime`) | Time zone, network time, 12- or 24-hour clock. Setting the time by hand: a box for each of year, month, day, hour and minute, typed in or changed with ▲ and ▼, with AM and PM for the 12-hour clock. |
| **Apps** (`apps`) | Install and remove apps from Flathub, with no password. |
| **Software updates** (`updates`) | System and Flatpak updates, and TVWCS's own updates (including prereleases and rolling back). |
| **System information** (`system`) | Hardware and versions. Turns the SSH server on or off and shows how to connect. |
| **Terminal** (`terminal`) | A terminal, with Tab and Esc buttons for a remote. |
| **Network** (`network`) | Ethernet and Wi-Fi, and fixed IP settings. An Ethernet port the Debian installer set up (shown as "not managed") can be handed to NetworkManager; the old setup is kept as a backup. |
| **Storage** (`storage`) | Drives, with their partitions under them: mount and unmount partitions and safely remove drives. Partitions of the running system are marked as part of it. Network shares (Windows/Samba, NFS, SFTP, WebDAV, FTP): add, connect and disconnect. Passwords are not saved. |

A page whose tool is missing says what to install. When the Settings window is taller than it is wide (a tile, or a monitor turned on its side), the tabs show only their icons.

**Screen saver when locked:** with **Power and sleep › Show it when the computer locks** on, locking shows the screen saver. A key shows the password box; after a minute without a key the screen saver comes back. It uses xsecurelock (X11 only, so not on sway) instead of i3lock and TVWCS's lock screen picture.

**Lock screen:** in **Power and sleep › Lock screen** you can choose the **TVWCS lock screen** (off by default). It shows "Locked" and says whose password to type, then press Enter. It uses i3lock (swaylock on sway), so install that first. The power menu's Lock, the idle lock and xss-lock all use it. Switching back restores your previous locker. `tvwcs lock` locks by hand.

## Update and uninstall

**Update:** **Settings › Software updates › Check for TVWCS updates**, or run a newer installer. When a new version needs packages that are not installed, Settings lists them and offers to install them first. Your data is never changed. If you edited `~/.local/share/tvwcs/tvwcs.conf`, your copy is saved as `tvwcs.conf.bak`.

**Uninstall:**

1. Remove the `include ~/.local/share/tvwcs/tvwcs.conf` line from your i3/sway config (or restore its `.tvwcs-backup`).
2. Delete `~/.local/share/tvwcs` and `~/.local/share/applications/com.tvwcs.ControlPanel.desktop`. Delete `~/.config/tvwcs` too to remove your data.
3. If you set them up, delete:
   - automatic login: `/etc/systemd/system/getty@tty1.service.d/autologin.conf` the marked TVWCS lines in `~/.profile` (or your shell's login file), and `~/.xinitrc` if TVWCS created it;
   - login screen entries: `/usr/share/xsessions/tvwcs-i3.desktop`, `/usr/share/wayland-sessions/tvwcs-sway.desktop` and `/usr/local/bin/tvwcs-session`;
   - the password-free power rule: `/etc/sudoers.d/zz-tvwcs-power-<user>`.

## Troubleshooting

- **The hotkey does nothing:** check that `i3-msg -t get_config | grep -i tvwcs` (`swaymsg` on sway) shows TVWCS and that `~/.config/tvwcs/hotkeys.conf` exists. Running `install.sh` again fixes both.
- **Tapping Super does nothing:** another tool (such as xcape) may grab the key. `xev` shows the keycode your key sends; compare it with the line in `hotkeys.conf`.
- **"TVWCS is already running":** delete the stale `$XDG_RUNTIME_DIR/tvwcs.pid`.
- **The edges of TVWCS are cut off on the TV:** raise **Settings › Options › Screen edge margin**, or turn off overscan in the TV's picture settings.
- **Wrong monitor (i3):** install `xdotool`.
- **sway says "Invalid tiling_drag command" (or other errors about your i3 config):** sway started on its own reads `~/.config/i3/config` when there is no `~/.config/sway/config`, and i3-only lines stop it. Start TVWCS's sway session with `tvwcs-session sway` instead (from a text console, or **TVWCS (sway)** at the login screen; a login screen made only for X, such as Linux Mint's, may not list it). `install.sh` also offers to create a sway config of its own.
- **Letters instead of icons:** install `adwaita-icon-theme` or `papirus-icon-theme`.
- **Check for updates fails:** TVWCS needs internet access to `api.github.com`.

Developer notes (code layout, tests, releases) are in [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) and [docs/RELEASES.md](docs/RELEASES.md).

## License

MIT. See `LICENSE`. Most of the code was written by AI from a project description and rounds of review. You may copy, reuse or adapt it freely.
