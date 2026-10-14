# TVWCS

TVWCS (TV Window Channel Switcher) is a remote-friendly, TV-style launcher and window switcher for ordinary Linux desktop applications on i3 or sway. It is not a media center and needs no app-specific plugins. See `PROJECT_OVERVIEW.md` for the goals behind it.

**New in 2.7:** sway support; installs into `~/.local/share/tvwcs` and sets up your i3 / sway config for you (or creates one); a hotkey for any application; a remote key for fullscreen, and fullscreen apps stay fullscreen; Arch, Fedora and systems without systemd; an on-screen password prompt when Reboot or Shut down needs one. See `CHANGELOG.md` for everything.

<table>
  <tr>
    <th width="25%">Quick Menu</th>
    <th width="75%">Quick Menu + Applications</th>
  </tr>
  <tr>
    <td valign="top"><img src="assets/quick-menu.png" alt="The TVWCS Quick Menu" width="100%"></td>
    <td valign="top"><img src="assets/guide-menu.png" alt="The Quick Menu with the Applications guide open beside it" width="100%"></td>
  </tr>
  <tr>
    <td valign="top">The Quick Menu, a full-height column at the left of the screen. The red ✕ closes it and ☰ opens Applications. Below the search field, <b>Open applications</b> lists what is running by workspace: Screenshot has a workspace of its own, while <i>Gnome terminal + Files</i> is one workspace holding 3 apps. <b>Favorites</b> are pinned apps, two of them with channel numbers (003, 011). Pressing ← on a row opens its options. The key hints are at the bottom.</td>
    <td valign="top">The Applications guide open beside the Quick Menu. <b>Channel Guide</b> lists the 4 profiles that have a channel number. <b>All applications</b> lists every installed app by category (Media, Internet, …); Enter folds a category. Each row shows the app's logo, channel, name and description, then a favorite star (★ when it is a favorite) and an edit button. <i>Jellyfin Media Player profile 2</i> is a second launch profile of Jellyfin, indented under it with a ↳. The ⚙ button at the top right switches to Settings.</td>
  </tr>
  <tr>
    <th colspan="2">Settings</th>
  </tr>
  <tr>
    <td colspan="2"><img src="assets/settings.png" alt="The Settings view of the Applications pane" width="100%"></td>
  </tr>
  <tr>
    <td colspan="2" valign="top">Settings, in the same pane (the button at the top right goes back to the guide). The left column holds Display, Behavior, At login and Updates; each row shows its current value on the right, and Enter changes it. The right column holds the three hotkey sets: keyboard (tap Super for the Quick Menu), remote (F2) and gamepad (not set). The System actions sit in a grid underneath. (This screenshot is from 2.6: since 2.7 the right column also has the remote's Fullscreen key and an Application hotkeys section, and Behavior and At login have a setting more each.) This Quick Menu has its options buttons hidden, one of the Behavior settings.</td>
  </tr>
</table>

## Requirements

Linux with i3 (4.20 or newer) or sway, Python 3.9 or newer, GTK 4 and PyGObject. On i3, TVWCS uses `xdotool` to find the monitor under the pointer; sway reports it directly. systemd is not needed (see below). `install.sh` lists anything missing in your distribution's terms; for i3 (swap the window manager for `sway` and drop `xdotool` on sway):

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 i3 xdotool        # Debian, Ubuntu, Linux Mint, Devuan
sudo pacman -S python-gobject gtk4 i3-wm xdotool              # Arch, Manjaro, EndeavourOS, Artix
sudo dnf install python3-gobject gtk4 i3 xdotool              # Fedora
sudo xbps-install python3-gobject gtk4 i3 xdotool             # Void
doas apk add python3 py3-gobject3 gtk4.0 i3wm xdotool          # Alpine
```

**Without systemd** (Artix, Devuan, Gentoo with OpenRC, Void, Alpine): everything works. Sleep, Reboot and Shut down use elogind's `loginctl` when it is installed, otherwise `zzz` / `reboot` / `poweroff`, which need root. Lock uses the first screen locker it finds (or `lock_command` in `config.json`). Without an `XDG_RUNTIME_DIR` (no elogind), TVWCS keeps its running files in `~/.cache/tvwcs`.

**When Sleep, Reboot or Shut down needs your password** (no systemd or elogind, or polkit refuses because another user is logged in): TVWCS asks for your sudo password in its own dialog. Type it on a keyboard, such as the one on the back of a remote, or, if it is all digits, on the on-screen keypad with the arrow keys. It goes straight to `sudo` and is never stored; a wrong one asks again (3 tries). With a no-password `doas` or `sudo` rule, nothing is asked. `install.sh` offers to add one (off unless you say yes): a sudoers file, `/etc/sudoers.d/zz-tvwcs-power-<you>`, or lines in `/etc/doas.conf`, allowing only `systemctl` / `loginctl` `suspend`, `reboot` and `poweroff`, and `reboot`, `poweroff` and `zzz` with no arguments. Delete that file to undo it.

## Install

**Starting from an empty computer?** [Setting up a TV computer with Debian and TVWCS](docs/INSTALL-DEBIAN.md) walks through installing Debian from its network installer with no desktop, turning on SSH and Avahi, and installing TVWCS from another computer on your home network.

Each method below installs TVWCS into `~/.local/share/tvwcs`. Your own data (channels, favorites, settings, hotkeys) is kept apart from the program, in `~/.config/tvwcs/`.

**From a release zip** (from the repository's [Releases](https://github.com/one-moment-please/tvwcs/releases) page). Extract the zip in a temporary folder and run its installer. You can delete the extracted folder afterwards.

```bash
cd "$(mktemp -d)"
unzip ~/Downloads/TVWCS-*.zip
./tvwcs/install.sh
```

**From the repository, without git:** download the latest code as a tarball, extract it in a temporary folder and run its installer. `tar` is on every Linux system, and this works over SSH too (use `ssh -t` so the installer can ask its questions).

With `wget` (installed by default on Debian, where `curl` is not):

```bash
cd "$(mktemp -d)"
wget -qO- https://github.com/one-moment-please/tvwcs/archive/refs/heads/main.tar.gz | tar -xz
./tvwcs-main/scripts/install.sh
```

With `curl`:

```bash
cd "$(mktemp -d)"
curl -fsSL https://github.com/one-moment-please/tvwcs/archive/refs/heads/main.tar.gz | tar -xz
./tvwcs-main/scripts/install.sh
```

**From the repository, with git:**

```bash
git clone https://github.com/one-moment-please/tvwcs && cd tvwcs
./scripts/install.sh
```

The installer then sets up i3 and/or sway (whichever is installed). It asks before changing anything, and backs a config up as `config.tvwcs-backup` before it edits it:

- **Packages are missing:** it lists each one with what it is for (GTK 4 for Python, i3, `xdotool`, PipeWire with its PulseAudio layer when there is no sound server, and the Control Panel's tools) and offers to install them with your package manager; otherwise it prints the command.
- **Neither i3 nor sway is installed:** it offers to install one with your package manager: i3 together with Xorg, `startx`, `xdotool` and `xrandr` (recommended, and the default on Enter), or sway. It then carries on as below, so it can create the config and set the computer to start it at boot.
- **You have a config:** it offers to add one line to it, and reloads the window manager if it is running:
  ```i3
  include ~/.local/share/tvwcs/tvwcs.conf
  ```
- **You have no config yet:** it offers to create one from the standard template (i3's own, as `i3-config-wizard` makes it, or sway's). It asks which key to use as `$mod` (Super or Alt) and whether to keep your current keyboard layout or use another (such as `de` or `us dvorak`).
- **The computer has no login screen yet** (no display manager such as GDM, LightDM or SDDM) **and i3 or sway is installed:** it offers to log you in automatically when the computer starts and start i3 (through `startx`, writing `~/.xinitrc` if there is none) or sway, so it boots straight to TVWCS like a TV. This is asked with a default of no, since anyone who switches the computer on then gets your session. It sets up the first console's login through systemd (`/etc/systemd/system/getty@tty1.service.d/autologin.conf`) or runit (`/etc/sv/agetty-tty1/conf`, backed up first), using sudo or doas, and adds a few marked lines to your shell's login file (`~/.profile`, `~/.bash_profile`, `~/.zprofile`, or a fish `conf.d` file) that start the window manager on that console only (an SSH login is never affected). It also sets TVWCS to open its Quick Menu at log-in, and once the install is done it starts the session on the computer's screen right away, unless someone is logged in on that console. To undo it, delete that file (or restore the backup) and the marked lines.
- **TVWCS was installed in `~/.config/i3/tvwcs` before (2.6 and older):** it moves it to `~/.local/share/tvwcs`, offers to change your config's include line to the new place, points your hotkeys there, and offers to delete the old copy once nothing uses it.

Without a terminal to ask in, it changes no config and prints the line to add.

**Over SSH:** run it as `ssh -t <computer> ~/tvwcs/install.sh` (with `-t`, so it can ask its questions and sudo can ask for your password). It finds the i3 or sway running on the computer's screen through its socket in `/run/user/<uid>` to reload it and restart TVWCS, and an automatic login set up this way starts on the computer's own screen, not in the SSH session. `tvwcs.conf` starts TVWCS, loads your hotkeys and sets up its window rules. To install somewhere else, run `TVWCS_DEST=/some/path install.sh`; the installer points `tvwcs.conf` at that folder. `TVWCS_WMS=sway install.sh` sets up only sway (or only i3).

**Upgrading:** use **Settings › Check for updates**, or run the installer again from a newer zip or a fresh `git pull`. The installer replaces the program files but never changes your data. An install still in `~/.config/i3/tvwcs` is moved by either, the in-app update after it asks you. If TVWCS is running, it asks whether to restart it on the new version. If you edited `tvwcs.conf` by hand, your copy is saved as `tvwcs.conf.bak`.

## Using it

| Key | Action |
|---|---|
| **Super** tapped on its own (keyboard), **F2** (remote) | Show or hide the Quick Menu |
| *not set by default* | Open or close the Applications pane beside the Quick Menu |
| *not set by default* (remote) | Toggle fullscreen on the app you are using |
| **↑ ↓ ← →** | Move around. Pressing **→** past the end of the Quick Menu opens Applications |
| **Enter** | Launch, switch to, or activate the selected item |
| **Esc** / remote **Back** | Go back one step: close a dialog, then Settings, then Applications, then the Quick Menu |
| *any letter or digit* | Start a search. A channel number followed by Enter launches that channel; so do three digits (`007`) left alone for a second |
| **←** or right-click on a Quick Menu row | Open the row's options; they close again when you move away from them |

With **Settings › Button hints** on (it is off by default), an icon-only button that stays selected for 3 seconds shows its tooltip for 6 seconds, so a remote gets the same hints a mouse would.

Hotkeys come in three sets, one each for the keyboard, the remote and a gamepad, each with a key for the Quick Menu and one for Applications; the remote also has a key that toggles fullscreen on the focused app. Change them under **Settings › Hotkeys**; only the keyboard's Quick Menu key (tap Super) and the remote's (F2) are set to start with. A gamepad needs a mapper such as AntiMicroX to turn its buttons into keys first.

Any launch profile can also have a hotkey that launches it, set in its editor. **Settings › Application hotkeys** counts them and lists them to change or remove. A key does one thing: choosing one that is already in use warns you and asks before moving it.

From a terminal you can run `~/.local/share/tvwcs/bin/tvwcs` with `toggle`, `guide`, `stop`, `launch <profile id>` or `control [page]`.

**Quick Menu:** search, then your open applications grouped by workspace, then your favorites. A row's options can open an app the other way (tiled here, or in its own workspace), run its `.desktop` actions, move a workspace to another monitor, expand a workspace into its apps, or close it.

**Applications:** the pane always opens on the applications guide. Categories fold with Enter. **Channel Guide** at the top lists every profile with a channel number. ☆ adds an app to your favorites, and ✎ (edit) manages its launch profiles. A profile can have a channel number, a launch mode (tiled or in its own workspace), a custom command or `.desktop` action, a description, a hotkey, and an optional PIN. Clicking the TVWCS window while an editor is open closes the editor without saving. The PIN is a convenience lock for a shared TV, not real security. The button at the top right switches between the guide and **Settings**.

**Settings** (two columns, with the system actions in a grid below): interface size (Desktop, TV Mode, and 4K TV Mode when a 4K display is connected), closing when you click outside, always opening apps in a new workspace, how running apps open, hiding the options buttons, button hints, keyboard / remote / gamepad hotkeys, an app to open at login, opening the Quick Menu at login, **Check for updates**, and system actions (Lock, Sleep, Log out, Reboot, Shut down). Log out, Reboot and Shut down ask you to confirm first.

## Control Panel

The Control Panel is a separate application in the same Metro style, sized by TVWCS's **Interface size**. `install.sh` adds it to your applications, so it is in the guide under **System**, where it can have a channel number or be a favorite like any other app; its `.desktop` actions open a single page (a "Wi-Fi" channel, for instance, is a profile using the *Network* action). From a terminal: `tvwcs control`, or `tvwcs control sound|displays|bluetooth|updates|system|terminal|network`.

Its pages are tabs down the left: **↑ ↓** on the tabs changes page, **→** goes into the page, **←** from a page's left edge or **Esc** / **Back** comes back to the tabs, and **Esc** on the tabs closes it. Text (a Wi-Fi password, an IP address) is typed on a keyboard or picked on the on-screen keyboard with the D-pad.

| Page | What it does | It uses |
|---|---|---|
| **Sound** | Volume and mute for the output and the input; choose the output (speakers, HDMI, headphones…) and the microphone, and a device's connector. Sound already playing moves to the new output. | `pactl` (PipeWire or PulseAudio) |
| **Displays** | Resolution and refresh rate of each display. With several: which are on, where each one is (right of, left of, above, below, or the same picture as another; the others move along when one changes size) and, on X11, the primary display. A new resolution, refresh rate or display switched on or off goes back after 15 seconds unless you keep it. What you keep is applied again when TVWCS starts with the same displays connected (saved in `~/.config/tvwcs/displays.json`). | `xrandr` (i3 and other X11 sessions), `swaymsg` (sway) |
| **Bluetooth** | Switch Bluetooth on or off, search, pair (devices that need no code: headphones, speakers, game controllers, remotes), connect, disconnect and forget. Shows battery levels. | `bluetoothctl` (BlueZ) |
| **Software updates** | Lists waiting updates from the system's package manager and Flatpak, installs them all (asking for your sudo password, like the power actions) with their output on screen, and offers a restart when one is needed. | apt, dnf, pacman (`checkupdates` when installed), zypper, xbps or apk; `flatpak` |
| **System information** | This computer, its processor, memory, graphics, displays, every drive in use, battery, and the TVWCS, Python and GTK versions. **Remote access (SSH):** turn the SSH server on or off (or install it), allow passwords or keys only (refused while your user has no key, so you cannot lock yourself out), and see the command to connect with, the user, the local name and the IP addresses. | `/proc`, `/sys`, `lspci`; `systemctl` and OpenSSH's `sshd` |
| **Terminal** | A full terminal running your shell. Every key goes to it; **Back** (or **Shift+Esc**) leaves it. Without VTE, a console that runs one command at a time. | VTE for GTK 4 |
| **Network** | Ethernet and Wi-Fi: status and addresses, connect and disconnect, Wi-Fi on or off, join a network (with its password), forget one, and IP settings (automatic or manual address, gateway and DNS). | `nmcli` (NetworkManager); read-only from `ip` without it |

A page whose tool is missing says what to install; `install.sh` lists every missing package with what it is for and offers to install them (`pulseaudio-utils`, `x11-xserver-utils`, `bluez`, `network-manager` and `gir1.2-vte-3.91` on Debian and Ubuntu).

## Troubleshooting

- **The hotkey does nothing:** start TVWCS once with `~/.local/share/tvwcs/bin/tvwcs`, then check `i3-msg -t get_config | grep -i tvwcs` (`swaymsg` on sway). If you see nothing, check your i3 version (4.20 or newer) and that `~/.config/tvwcs/hotkeys.conf` exists. Running `install.sh` creates it.
- **Tapping Super does nothing:** TVWCS binds it as `bindcode --release <keycode>` using your keyboard's keycode for the left Super key (usually 133). Check the line in `~/.config/tvwcs/hotkeys.conf`, and `xev` shows the keycode your key really sends. Some desktop tools (such as xcape, or a launcher bound to Super) can grab the key first.
- **"TVWCS is already running":** a stale `${XDG_RUNTIME_DIR:-/tmp}/tvwcs.pid` is left over. Stop that process or delete the file.
- **Wrong monitor or the menu covers your bar:** install `xdotool`, or raise `settings.margin` in `~/.config/tvwcs/config.json`. Stop TVWCS before editing that file.
- **Missing icons:** install an icon theme such as `adwaita-icon-theme`. Until then TVWCS shows text glyphs instead.
- **Check for updates fails:** TVWCS needs internet access to `api.github.com` and a published (non-beta) release on GitHub.

## Development

```
package/tvwcs/   application modules        package/tests/   unit tests (no display needed)
package/bin/     the tvwcs launcher         data/tvwcs.conf  the i3 config fragment
                                            data/com.tvwcs.ControlPanel.desktop  the Control Panel's launcher
scripts/         install, tests, release    docs/RELEASES.md the beta → publish workflow
```

```sh
./scripts/run-tests.sh            # unit tests
./scripts/make-release.sh --beta  # build a test zip into resources/
```

Pushing to the `beta` branch builds a pre-release zip on GitHub. Pushing a `v*` tag publishes a release, which **Check for updates** then offers to installed copies.

## License and notes

MIT. See `LICENSE`. Most of this project's code was written by AI from a project description and rounds of revisions. You're free to copy, reuse or adapt it in any way.
