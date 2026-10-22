# TVWCS

TVWCS (TV Window Channel Switcher) lets you use an ordinary Linux computer from the couch with a remote. It runs on top of the i3 or sway window manager and gives you:

- a **Quick Menu** at the bottom left of the screen: your favorites, your open apps, search, and a status row with the clock, network, sound, Bluetooth and battery;
- an **Applications** pane beside it: every installed app by category, plus your own numbered **Channels**;
- a **Settings** app for the things a TV computer needs: sound, displays, Wi-Fi, Bluetooth, power, updates and more.

It works with normal desktop apps. It is not a media center and needs no plugins. What's new is in [CHANGELOG.md](CHANGELOG.md).

TVWCS has two modes:

- **TV mode** is the **TVWCS** session you pick at the login screen. It is made for a remote: every app opens full screen in a workspace of its own, the i3/sway bar is off (the Quick Menu shows the time and status instead), the mouse pointer hides after 3 seconds, the Quick Menu stays open while nothing else is, and the computer locks with TVWCS's own lock screen.
- **Desktop mode** is TVWCS inside your usual i3 or sway session. The Quick Menu is a launcher and switcher; apps open the way i3/sway opens them, and your bar, pointer and lock screen are left as they are.

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
    <td valign="top">In desktop mode, "TVWCS" and ✕ close at the top (TV mode has no header). Below: one list of your favorites, then the other open applications (by workspace; ▴ unfolds the apps that share one, above it), then the search field. Favorites have a grey ★, and open apps a thin band down their left side. At the bottom, two rows: icons for network, volume, Bluetooth and the battery that each unfold a panel, with ⏻ power at the right; below them the clock and, in the bottom-right corner, ⊞, which opens Applications.</td>
    <td valign="top"><b>Channels</b> lists apps you gave a number. <b>All applications</b> lists every app by category; OK/Enter folds a category. ☆ makes an app a favorite, ✎ edits it.</td>
  </tr>
  <tr>
    <th colspan="2">Settings › Appearance</th>
  </tr>
  <tr>
    <td colspan="2"><img src="assets/options.png" alt="The Appearance page of the Settings app" width="100%"></td>
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
    <td valign="top">With the remote: open an app by its channel number, open a second one by channel, go back to the first from the Quick Menu's list, and open a third by searching its name. Each app gets a workspace of its own.</td>
    <td valign="top">With the keyboard and mouse, in the light theme: open apps by name so they tile side by side, fill a second workspace, switch between workspaces from the Quick Menu, then close one app and a whole workspace, unfold the power options above ⏻, and open Applications from ⊞ in the corner.</td>
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

Run this in a terminal (not as root):

```bash
wget -qO- https://raw.githubusercontent.com/one-moment-please/tvwcs/main/install.sh | bash
```

With curl: `curl -fsSL https://raw.githubusercontent.com/one-moment-please/tvwcs/main/install.sh | bash`. Over SSH, sign in with `ssh -t` so the installer can ask its questions.

The installer asks all its questions first and changes nothing until you agree to the list of what it will do. If something fails, it undoes what it had done. It installs TVWCS into `~/.local/share/tvwcs`; your own data (channels, favorites, settings, hotkeys) is kept in `~/.config/tvwcs/`. You can also unpack a release from [Releases](https://github.com/one-moment-please/tvwcs/releases) and run its `./tvwcs/install.sh`: it then offers to install that release, or to download another.

### What the installer asks

1. **When TVWCS is already installed:** upgrade, install a different version (the prerelease when there is one, or one of the two releases before the latest), or remove TVWCS.
2. **i3, sway or both.** It says which are installed and suggests those. With neither, it suggests sway, which plays video more smoothly; i3 can suit games and older apps better.
3. **The login screen.** With no login screen, it installs TVWCS's own. With another one, it offers TVWCS's. TVWCS's login screen shows who can log in, takes the password from the remote on an on-screen keyboard, and starts the TVWCS session by default (the sway one when both are set up). Some login screens, such as LightDM (Linux Mint's), cannot reliably start sway: then it warns and offers TVWCS's login screen, i3 instead, SDDM, installing anyway, or cancelling.
4. **Your usual i3/sway session.** TVWCS always gets its own **TVWCS** session at the login screen, in TV mode. It asks whether to also add TVWCS to your usual i3/sway session, in desktop mode (one `include` line in its config). Without an i3/sway config, it asks whether to create one (choosing the `$mod` key and the keyboard layout) or not now.
5. **The packages.** It lists what it needs, grouped by what each is for, and asks whether to go ahead.

Every file of yours it changes is backed up first as `<file>.tvwcs-backup`.

**Upgrading from 3.x:** TV mode is now the TVWCS session at the login screen, and your usual i3/sway session is desktop mode. The installer cleans up what earlier versions set up and tells you what changed. If you have been logging in to your usual i3 or sway session to use TVWCS on a TV, log in to the **TVWCS** session next time; the installer shows how to put your usual session back to how it was.

**Removing TVWCS:** run the installer and choose **Remove**. It takes out every part of TVWCS. If TVWCS's login screen is in use, it switches to another first; when there is no other, it tells you to install one and stops. It lists the packages it installed that nothing else needs and offers to mark them so `sudo apt autoremove` removes them; it does not remove them itself.

**For scripted installs:** `TVWCS_VERSION=latest` (or `package`, or a version such as `4.0.0`) answers which version, `TVWCS_WMS="i3 sway"` which window managers, `TVWCS_DEST=<folder>` installs somewhere else, and `TVWCS_NO_RESTART=1` leaves a running TVWCS alone. `./install.sh --missing` lists the packages that are not installed, and changes nothing.

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

- **Quick Menu layout:** it sits in the bottom-left corner, only as tall as what it shows. Your favorites and open apps (one list, favorites first), search and the status row are at the bottom, with search results appearing above the search field. Favorites have a grey ★ and open apps a thin band down their left side, so a favorite that is open (shown once, in its place) has both. A name too long to fit scrolls by after it has been selected for 3 seconds. In TV mode the search field is three characters wide and shows **___** for a channel number. The date is short, such as "Sat, Oct 17".
- **Row options (⋯):** they unfold upwards, just above their row and indented a little. From the top: the app's own shortcuts (such as Settings' pages), open it this once the other way (**Open in new workspace** in desktop mode, **Open alongside …** the apps on screen in TV mode), and **Close this application** at the bottom, nearest the row. A workspace's can move it to another monitor. Back folds them away.
- **Workspaces with several apps:** the square ▴ button between ⋯ and the workspace's name unfolds its individual apps above it, to open just one; ▾ folds them again. On the name, ← moves onto it; ← again opens the row's menu.
- **Channels:** 000 to 999. Channel 000 opens Settings unless you give it to another app. Setting a channel shows three digit boxes; typing replaces the number.
- **Slow apps:** while an app takes a few seconds to open, a spinner turns in place of its icon in its button, so the screen is never blank, and the Quick Menu still opens.
- **Editing an app (✎):** opens its launch profile: a channel number, a hotkey, a Desktop Action (one of the app's own shortcuts), a custom command, a description and a PIN. **Copy** makes another profile from what is shown, such as Firefox in a private window; it is listed as "Firefox 2" (rename it to "Firefox Private"). The app's name itself never changes. A PIN-protected profile asks for its PIN first. The PIN is a lock for a shared TV, not real security.
- **Status panels:** network, volume, Bluetooth and battery icons unfold a panel above the status row: the connection and its address, **Find Wi-Fi networks** (choose one to connect; a password is asked when needed) and Wi-Fi on/off; mute and volume for output and input; the connected Bluetooth devices with Disconnect, **Find Bluetooth devices** (choose one to pair) and Bluetooth on/off; the battery's time left or time to full. Each has a button for its Settings page.
- **Power menu (⏻):** at the bottom right: Lock, Sleep, Reboot, Shut down; Log out when there is a login screen.
- **Applications:** ⊞ in the Quick Menu's bottom-right corner (or → on a row) opens Applications; ⊞ again closes it. If a power action needs your password, TVWCS asks for it on screen and never stores it.
- **Mouse and remote:** clicking with the mouse does not move the remote's selection.
- **On-screen keyboard:** wherever text is typed, the on-screen keyboard can be hidden (it starts that way), full, or a number pad; buttons on it switch, and it opens next time as you left it.
- **Other keys:** set the Quick Menu key for a keyboard, a remote or a gamepad in **Settings › Remote and hotkeys**, where the apps with hotkeys of their own are listed too. A gamepad needs a key mapper such as AntiMicroX.

From a terminal, `~/.local/share/tvwcs/bin/tvwcs` takes `toggle`, `guide`, `stop`, `lock`, `launch <profile id>` or `settings [page]`.

## Settings

Open **TVWCS Settings** with channel 000, from a status panel's settings button, from Applications (under System), or with `tvwcs settings [page]`. Pages are tabs on the left: **→** enters a page, **Back** returns to the tabs. Text is typed on a keyboard or on the on-screen keyboard.

| Page (`tvwcs settings …`) | What it does |
|---|---|
| **Appearance** (`appearance`) | Interface size (Automatic is TV size in TV mode and desktop size otherwise), dark or light theme (passed on to apps that follow the system's choice), accent colour, background colour, closing TVWCS when it loses focus (on by default), and the screen edge margin for TVs that cut off the edges (overscan), set on a full-screen preview with a slider. |
| **User** (`user`) | Your name and password, with "Administrator" or "Standard User" beside the page's title. Logging in automatically after start-up, on or off. The login screen: when TVWCS's copy is out of date it says so and offers to update it; with more than one login screen it offers to switch, and to remove TVWCS's. The application to open at login (none, the last one used, or one you choose). |
| **Remote and hotkeys** (`hotkeys`) | The Quick Menu key for the keyboard, remote and gamepad (clearing one asks first), and the apps that have a hotkey of their own (give one with ✎ on the app). **Reset all hotkeys** puts back the defaults and removes the app hotkeys. |
| **Sound** (`sound`) | Volume and mute for the output and the input in use. The others are folded under "2 inactive outputs" or "1 inactive input", which open and close. **Allow over-amplification** lets volumes go up to 150 % (off by default: volumes stop at 100 %). |
| **Displays** (`displays`) | Resolution, refresh rate, arrangement and scale: a row of buttons from 75 % to 200 % (in i3 only 100 % and 200 % unless **Fractional scaling** is on). In i3: **Tear-free video** (Xorg's TearFree, or NVIDIA's full composition pipeline) and, when it is installed, a button that opens NVIDIA's settings (it may need a mouse). A change goes back after 15 seconds unless you keep it. |
| **Power and sleep** (`power`) | When the screen saver starts, the screen turns off, the computer locks and it sleeps. A laptop has these times twice, plugged in and on battery, and a choice of what to do when the battery is nearly empty. The screen saver is TVWCS's logo or a picture of your own, bouncing around. It works on i3 and on sway (where it is drawn over every window and needs gtk4-layer-shell, which the page offers to install). In TV mode on i3 it can also show when the computer locks: any key shows the lock screen, and after a minute without input the screen saver comes back. It never runs while the screen is off. |
| **Bluetooth** (`bluetooth`) | Pair, connect and forget devices. Shows battery levels. |
| **Date and time** (`datetime`) | Time zone, network time, 12- or 24-hour clock. Setting the time by hand: a box for each of year, month, day, hour and minute, typed in or changed with ▲ and ▼, with AM and PM for the 12-hour clock. |
| **Apps** (`apps`) | Install and remove apps from Flathub, with no password. Without Flatpak, it offers to install it and add Flathub. Tabs along the top: **Search** (a search bar that searches as you type; ⌨ beside it opens the on-screen keyboard), **Categories** (two rows of category buttons, Featured first), **Installed**, and **Settings**, on the page: how apps are installed, the repositories (add, turn off or remove them; Flathub can be turned off but is always kept), unverified apps (off, recommended), downloading the list of apps again, and uninstalling every Flatpak app and runtime, each explained. |
| **Software updates** (`updates`) | System and Flatpak updates, and TVWCS's own updates (including prereleases and rolling back). |
| **System information** (`system`) | Hardware and versions. Turns the SSH server on or off and shows how to connect. |
| **Terminal** (`terminal`) | A terminal, with Tab and Esc buttons for a remote. |
| **Network** (`network`) | Ethernet and Wi-Fi, and fixed IP settings. An Ethernet port the Debian installer set up (shown as "not managed") can be handed to NetworkManager; the old setup is kept as a backup. |
| **Storage** (`storage`) | Drives, with their partitions under them: mount and unmount partitions and safely remove drives. Partitions of the running system are marked as part of it. Network shares (Windows/Samba, NFS, SFTP, WebDAV, FTP): add, connect and disconnect. Passwords are not saved. Buttons install and uninstall the network share support (Samba, through gvfs-backends). |

A page whose software is missing offers to install it (Sound installs PipeWire, Bluetooth BlueZ, and so on). When the Settings window is taller than it is wide (a tile, or a monitor turned on its side), the tabs show only their icons.

**Locking in TV mode:** the TVWCS session always locks with TVWCS's lock screen, which says "Locked" and whose password to type (it uses i3lock, or swaylock on sway). With **Power and sleep › Show it when the computer locks** on (i3), locking shows the screen saver; any key or button shows the lock screen, and after a minute without input the screen saver comes back. Once the screen has turned off (**Turn off the screen after**), the screen saver stays away until the next lock, and the lock screen turns the screen off again instead. A desktop session's own lock screen is not changed. `tvwcs lock` locks by hand.

## Update and uninstall

**Update:** **Settings › Software updates › Check for TVWCS updates**, or run the installer again and choose Upgrade. When a new version needs packages that are not installed, Settings lists them and offers to install them first. Your data is never changed.

**Uninstall:** run the installer and choose **Remove** (see above).

## Troubleshooting

- **The hotkey does nothing:** check that `i3-msg -t get_config | grep -i tvwcs` (`swaymsg` on sway) shows TVWCS and that `~/.config/tvwcs/hotkeys.conf` exists. Running `install.sh` again fixes both.
- **Tapping Super does nothing:** another tool (such as xcape) may grab the key. `xev` shows the keycode your key sends; compare it with the line in `hotkeys.conf`.
- **"TVWCS is already running":** delete the stale `$XDG_RUNTIME_DIR/tvwcs.pid`.
- **The edges of TVWCS are cut off on the TV:** raise **Settings › Appearance › Screen edge margin**, or turn off overscan in the TV's picture settings.
- **Wrong monitor (i3):** install `xdotool`.
- **sway says "Invalid tiling_drag command" (or other errors about your i3 config):** sway started on its own reads `~/.config/i3/config` when there is no `~/.config/sway/config`, and i3-only lines stop it. Start TVWCS's sway session with `tvwcs-session sway` instead (from a text console, or **TVWCS (sway)** at the login screen; a login screen made only for X, such as Linux Mint's, may not list it). `install.sh` also offers to create a sway config of its own.
- **Letters instead of icons:** install `adwaita-icon-theme` or `papirus-icon-theme`.
- **Check for updates fails:** TVWCS needs internet access to `api.github.com`.

Developer notes (code layout, tests, releases) are in [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) and [docs/RELEASES.md](docs/RELEASES.md).

## License

MIT. See `LICENSE`. Most of the code was written by AI from a project description and rounds of review. You may copy, reuse or adapt it freely.
