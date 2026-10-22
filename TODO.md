# TVWCS to-do

Work that was researched but not done, so it can be picked up later. Code references are `path:line` as of
version 2.10.4; the last commit with the removed distribution support in it is `9e7ef12`
(`git show 9e7ef12:scripts/install.sh` and so on gives the old files back in full).

TVWCS 5.0 removed i3 (and X11), TVWCS's own login screen, the screen saver, Settings › Apps (Flatpak), Settings ›
Terminal, network shares and setting the time by hand. The last commit with all of them is `10cee1d` (4.2.2), for
bringing any of them back. Notes below that mention i3 date from before then.

---

## 1. Tablet mode (not started)

**Goal:** TVWCS works with touch only: tap, swipe, long-press and an on-screen keyboard. No keyboard, mouse,
remote or gamepad.

**Summary:** feasible, but most of the work is outside TVWCS's own windows. System-wide gestures and the keyboard
are the hard part, and they work much better on sway than on i3. Overall effort about L to XL.

### What can be reused

- Every button already works when tapped: GTK 4 treats a tap as a click, and `ScrolledWindow` already scrolls with
  momentum under a finger.
- The window layout (`model.py:270 compute_layout`), the in-window dialogs, the Settings pages, the PIN pad and the
  on-screen keyboard (`ui_control.py:409`).
- `window_manager.py` already focuses windows, closes them, switches workspaces and toggles fullscreen; gestures can
  call it directly.
- The installer's "Used on" question (`install.sh` `choose_use`) and `apply_use` (`model.py:44`) are where a third
  choice goes. `tvwcs toggle` already exists for outside tools to call.
- The idle, sleep and lid handling in `power.py`, and the battery reading in `control_sysinfo.py:96`.

### Input inside TVWCS

- Add GTK 4 gesture controllers to the main window:
  - `Gtk.GestureSwipe`: swipe left on the Quick Menu to close it; left or right to open or close Applications.
  - `Gtk.GestureDrag`: a panel follows the finger, then snaps open or closed.
  - `Gtk.GestureLongPress`: opens a row's options.
- Long-press replaces right-click and the ← shortcut, which a finger can't do (`ui_window.py:209,357`). The row
  options buttons must always show in tablet mode, whatever `hide_options_buttons` says.
- No hover on touch, and focus behaves differently:
  - Tooltips and Button hints (`ui_window.py:451`) become always-visible labels under icons, or a long-press
    "what is this".
  - After a tap the button stays highlighted, because `button:focus` paints the accent (`theme.py:17`). In tablet
    mode style only `:focus-visible` and `:active`.
- Lists: swipe-to-reveal Close on rows (like the ✕ on open-app rows). A "pull down to refresh" or ⟳ button where the
  remote relies on polling.

### Opening and closing the menus from the screen edge (the hard part)

- i3 and sway don't pass edge swipes to applications, so an outside tool must detect them and run `tvwcs toggle` /
  `tvwcs guide`.
  - sway `bindgesture` (1.8+) and `libinput-gestures` only handle touchpad gestures. libinput does not recognise
    gestures on touchscreens, so neither helps on a tablet screen.
  - `lisgd` reads raw touch events and supports edge swipes, on X11 and Wayland. The user must be in the `input`
    group, which lets any of their programs read all input, keystrokes included. The best fit of the outside tools.
  - `touchegg` (2.x) handles touchscreen gestures, X11 only.
- sway-only alternative: an invisible strip 8–12px wide along the edge, a layer-shell surface in the overlay layer
  (`gtk4-layer-shell`), so it stays above fullscreen apps. No daemon, no `input` group. i3/X11 has no clean
  equivalent: a floating strip stays under fullscreen windows.
- Always add a visible way back (a small floating "home" button or a bottom bar). If gestures fail it is the only way
  out of a fullscreen app.

### Touch target sizes

- Buttons are 44px at Desktop size (`theme.py:15,23`), the bare minimum, and the 4px gaps between row buttons
  (`ui_window.py:186`) invite mis-taps. A tablet size preset (about ×1.25–1.4, in `SCALE_PRESETS`, `model.py:26`):
  56–64px targets, at least 8px gaps.
- Portrait: `compute_layout` puts the panels side by side and caps the Quick Menu at 45% of the width
  (`model.py:279`). In portrait, stack them, or open one at a time full-screen with a back arrow.

### On-screen keyboard for the whole system

- TVWCS's keyboard only works in its own dialogs. Other apps need a system keyboard that shows by itself:
  - sway / Wayland: `squeekboard` (input-method and text-input protocols, can auto-show; built for Phosh, works on
    sway with rough edges), or `wvkbd` (simpler layer-shell keyboard, shown and hidden with signals, so it needs a
    keyboard button).
  - X11 / i3: `onboard` (auto-shows through AT-SPI; packaged but barely maintained, unreliable with some toolkits),
    or `svkbd` (minimal, no auto-show).
- Plan for both: auto-show where it works, plus a keyboard button in the Quick Menu status row and a
  `tvwcs keyboard` command.
- TVWCS's own keyboard should open the system keyboard instead when one is installed.

### Managing windows by touch

- Closing: ✕ on open-app rows exists. Add swipe-to-close and a long-press menu: Close, Fullscreen, Move to monitor,
  Side by side, Own workspace.
- Switching: the open-apps list is already a switcher. Optionally a three-finger swipe through `lisgd` →
  `i3-msg workspace next/prev`.
- Fullscreen is only a remote hotkey today (`hotkeys.py` `FULLSCREEN_COMMAND`): add it to the row menu and the status
  row.
- Tiled layouts are awkward by finger: default to one app per workspace in tablet mode (already the TV behaviour via
  `apply_use("tv")`).

### Screen rotation

- Manual: a "Rotation" row on the Displays page: `xrandr --rotate` on X11 (`control_display.py`), or
  `swaymsg output <name> transform 90` on sway.
- Touch must rotate too. sway does it once the touchscreen is mapped to the output (`input type:touch
  map_to_output`). On X11 set the touchscreen's `Coordinate Transformation Matrix` with `xinput` on every rotation
  (the usual cause of "touch is off by 90°").
- Auto-rotate: `iio-sensor-proxy` (D-Bus `net.hadess.SensorProxy`) reports orientation; a small watcher in TVWCS, or
  `rot8`, applies it. Add a "Rotation lock" toggle.

### Brightness and battery

- Brightness: a slider in the status row and on Displays, through logind's `SetBrightness` over D-Bus (no root for the
  active session) or `brightnessctl`.
- Battery: icon and percentage in the status row, from `control_sysinfo.battery()` or UPower; a low-battery warning
  tied to the sleep settings in `power.py`.

### Installer and settings

- A third "Used on" choice, "A tablet", in `USES` (`model.py:43`), `apply_use`, `choose_use` (install.sh) and
  Settings > Appearance (`ui_control_pages.py`, `AppearancePage`): tablet size preset, one app per workspace, always-visible options
  buttons, button labels, the gesture daemon.
- Recommend sway for tablets (touch, rotation, Wayland keyboard protocols, layer-shell edge strip). The installer
  calls i3 "recommended"; make that depend on the chosen use.
- Packages to offer: `lisgd` (or `touchegg` on i3), a keyboard (`squeekboard`/`wvkbd` or `onboard`),
  `iio-sensor-proxy`, `brightnessctl`. Adding the user to `input` for `lisgd`, with a clear warning.

### Testing

- Unit tests for the portrait layout maths and `apply_use("tablet")`, like `package/tests/test_model.py`.
- Gestures: simulate touch in the GTK Inspector, or with `weston`/`cage` and a virtual touch device (`uinput`). Edge
  swipes and rotation need real hardware (a cheap Intel tablet or a 2-in-1). Test i3 and sway, both orientations.

### A realistic first version

sway only, a visible home button, `wvkbd` with a keyboard button, and manual rotation. TVWCS-side gestures, target
sizes and the portrait layout are about M on their own.

---

## 2. A dedicated passwordless TV user (not started)

The installer's "This computer is only for TVWCS" option sets TVWCS up for the user who runs it. The idea below was to
create a separate `tv` account instead, which logs in by itself.

### The account

- The installing user (say `graham`) runs the installer, which uses sudo to run `useradd -m -s /bin/bash -c "TV" tv`.
- Lock the password (`passwd -l tv`) rather than emptying it (`passwd -d`): a locked account can't log in on another
  console or over SSH, and autologin still works, because `agetty --autologin` runs `login -f`, which skips the
  password check. Test this on each supported distribution.
- Add `DenyUsers tv` (or `AllowUsers graham`) to sshd in a drop-in, in case password logins are on.
- Groups: what the distribution needs for Bluetooth and Wi-Fi when tv is the active session. With logind most of it
  is automatic; Debian's `netdev` and `bluetooth` groups may still be needed. `input` only for tablet gestures
  (`lisgd`). Never `sudo`, `wheel`, `adm` or `docker`.
- Autologin: reuse `set_console_login` (install.sh), passing `tv`. A display manager is the alternative (greetd with
  `initial_session`, or LightDM `autologin-user=tv`): cleaner on crashes and logout, but another package.
- Starting the session: the existing start block in tv's shell profile (`startx` with `~/.xinitrc` → `exec i3`, or
  `exec sway`). Install TVWCS into `/home/tv/.local/share/tvwcs`, owned by tv, so the in-app updater keeps working
  without root (`selfupdate.py:109` installs into its own folder).

### Admin actions from the TV (updates, installing packages, SSH, network, power)

sudo cannot ask for a different user's password: only the caller's (default), root's (`Defaults:tv rootpw`) or the
target user's (`targetpw`, root again). The options:

1. **pkexec with a polkit rule (recommended).** `/etc/polkit-1/rules.d/50-tvwcs.rules`:

   ```js
   polkit.addAdminRule(function (action, subject) {
       if (subject.user == "tv") return ["unix-user:graham"];
   });
   ```

   Every admin action then asks for graham's password; root commands run through `pkexec`. polkit needs an
   authentication agent in the tv session, and TVWCS has none: either run `pkttyagent` in a pseudo-terminal and type
   the password into it, or implement a `PolkitAgent.Listener` through PyGObject (M–L work). `privilege.py` would get
   a pkexec path next to sudo and doas (`privilege.py:33,36`), reusing the on-screen password dialog
   (`ui_control.py:482`).
2. **The root password:** `tv ALL=(ALL) ALL` with `Defaults:tv rootpw`. Simple, works with the current `sudo -S`
   flow, but many systems have no root password (`docs/INSTALL-DEBIAN.md:26` says to leave it empty), so only an
   option, not the default.
3. **`su - graham -c '…'` in a pseudo-terminal**, typing graham's password for them. No polkit needed, but clumsy:
   su needs a terminal, and if graham's sudo also asks, the password is needed twice.
4. **No admin actions on the TV except power.** Keep the NOPASSWD rule for sleep, reboot and shut down for tv, and
   do updates over SSH as graham. Safest; the default if option 1 slips.

Network (NetworkManager through polkit), Bluetooth and Sound don't need root for an active local session. Check that
per distribution before building anything.

### Security

- Anyone who can touch the TV or plug in a keyboard gets the tv session: its browser logins, streaming accounts, and
  the Terminal page in Settings (`ui_control_pages.py:1081`).
- Acceptable for a living-room TV only if tv can't become root without graham's or root's password: no unlimited
  NOPASSWD rule, no `sudo`/`wheel`/`docker` membership.
- Hide the Terminal tab for tv, or put it behind a PIN (`pinlock.py` exists).
- The power NOPASSWD rule should be tv's only sudo rule.
- Say all this plainly in the installer, as it already warns about automatic login.
- Boot media and GRUB are still a way in. Disk encryption and a BIOS password are out of scope; one line in the docs.

### What it would create

- The `tv` user and its home.
- `/etc/systemd/system/getty@tty1.service.d/autologin.conf`.
- tv's `~/.profile` start block and `~/.xinitrc`.
- `~tv/.config/i3/config` (or sway) with the TVWCS include.
- `~tv/.config/tvwcs/` with `use=tv`.
- `~tv/.local/share/tvwcs/`.
- `/etc/sudoers.d/zz-tvwcs-power-tv`.
- Optionally `/etc/polkit-1/rules.d/50-tvwcs.rules` and an sshd `DenyUsers` drop-in.

List all of these at the end of the install, with an `uninstall.sh` (or `install.sh --remove-tv-user`) that removes
them.

### Risks

- Two copies of TVWCS (graham's and tv's) if graham also runs it; Settings updates only update tv's. Say so, or
  install system-wide under `/opt` and accept that updates need root.
- Groups and polkit defaults differ per distribution (netdev, bluetooth, NetworkManager rules); each needs testing.
- Upgrading from today's setup (include line in the main config, autologin for the user's own account) needs a clear
  "convert" path that doesn't break it.

---

## 3. Supporting other distributions (removed)

TVWCS now supports Debian and its family (Ubuntu, Mint, Pop!_OS, Raspberry Pi OS) through apt, with systemd, plus Flatpak. Everything below was removed in the commit after
`9e7ef12`, except openSUSE, which was removed in 3.0.2 (its last commit is `a6a81ca`; see 3.10). To bring a distribution back, restore its rows in each place listed, add its tests back, and test the
installer end to end on it.

### 3.1 What a distribution needs, place by place

| Place | What it holds |
|---|---|
| `scripts/install.sh` `distro()` | maps `/etc/os-release` `ID`/`ID_LIKE` to a family |
| `scripts/install.sh` `pkg()` | the package name for each need |
| `scripts/install.sh` `wm_packages()` | what installs i3 with X, or sway |
| `scripts/install.sh` `without_x_server()` | the Xorg server package's name, left out when XLibre is installed |
| `scripts/install.sh` `install_hint()` / `pkg_install()` | the install command, shown and run |
| `scripts/install.sh` autologin | `init_system`, `console_login_set`, `set_console_login`, `start_console_session` |
| `scripts/install.sh` `login_manager()` | how an enabled display manager service is found |
| `scripts/install.sh` `power_commands()` | the power commands the optional sudo/doas rule allows |
| `package/tvwcs/control_updates.py` | a `Manager` (list command, parser, upgrade command), `_TOOL`, `_LISTS` |
| `package/tvwcs/control_ssh.py` `INSTALL` | how to install the SSH server |
| `package/tvwcs/control_flatpak.py` `INSTALL_FLATPAK` | how to install Flatpak |
| `package/tvwcs/system_actions.py` | power commands without systemd |
| `package/tvwcs/privilege.py` `PLAIN_ROOT_COMMANDS` | plain power commands that always need root |
| `data/tvwcs.conf` | starting PipeWire without systemd |
| hint strings | `control_sound.py`, `control_display.py`, `control_bluetooth.py`, `ui_control_pages.py` |

### 3.2 Distribution detection (install.sh `distro()`)

```sh
arch|artix|manjaro|endeavouros) echo arch; exit ;;
devuan) echo debian; exit ;;   # Debian without systemd: apt and Debian's names, but no systemd
fedora|rhel|centos|rocky|almalinux|nobara) echo fedora; exit ;;
void) echo void; exit ;;
alpine) echo alpine; exit ;;
gentoo) echo gentoo; exit ;;
```

### 3.3 Package names per need (install.sh `pkg()`)

Rows that were not distribution-specific fell through to the need's own name (`xdotool`, `swayidle`, `unclutter`,
`xrandr`, `bluez`, `NetworkManager`, `libXScrnSaver`).

| Need | Arch | Fedora | Void | Alpine | Gentoo |
|---|---|---|---|---|---|
| gtk (GTK 4 + PyGObject) | `python-gobject gtk4` | `python3-gobject gtk4` | `python3-gobject gtk4` | `py3-gobject3 gtk4.0` | `dev-python/pygobject gui-libs/gtk` |
| i3 | `i3-wm` | `i3` | `i3` | `i3wm` | `x11-wm/i3` |
| xdotool | `xdotool` | `xdotool` | `xdotool` | `xdotool` | `x11-misc/xdotool` |
| xinit (startx) | `xorg-xinit` | `xorg-x11-xinit` | `xinit` | `xinit` | `x11-apps/xinit` |
| pactl | `libpulse` | `pulseaudio-utils` | `pulseaudio-utils` | `pulseaudio-utils` | `media-libs/libpulse` |
| bluetoothctl | `bluez-utils` | `bluez` | `bluez` | `bluez` | `net-wireless/bluez` |
| nmcli | `networkmanager` | `NetworkManager` | `NetworkManager` | `networkmanager-cli` | `net-misc/networkmanager` |
| pipewire | `pipewire pipewire-pulse wireplumber` | `pipewire pipewire-pulseaudio wireplumber` | `pipewire wireplumber` | `pipewire pipewire-pulse wireplumber` | `media-video/pipewire media-video/wireplumber` |
| unclutter | `unclutter` | `unclutter` | `unclutter` | `unclutter-xfixes` | `x11-misc/unclutter-xfixes` |
| xss (libXss) | `libxss` | `libXScrnSaver` | `libXScrnSaver` | `libxscrnsaver` | `x11-libs/libXScrnSaver` |
| xrandr | `xorg-xrandr` | `xrandr` | `xrandr` | `xrandr` | `x11-apps/xrandr` |
| vte (GTK 4) | `vte4` | `vte291-gtk4` | (unknown: `VTE-for-GTK-4`) | (unknown) | (unknown) |

Not yet checked: the icon theme (`adwaita-icon-theme` on Arch, Fedora, Void, Alpine; `x11-themes/adwaita-icon-theme`
on Gentoo; `papirus-icon-theme` on most) and the Open Sans font (`ttf-opensans` on Arch, `open-sans-fonts` on
Fedora, `font-open-sans` on Alpine, `media-fonts/open-sans` on Gentoo). Check the names before adding them.

### 3.4 Window manager packages (install.sh `wm_packages()`)

```sh
arch:i3) echo "i3-wm xorg-server xorg-xinit xdotool xorg-xrandr" ;;
fedora:i3) echo "i3 xorg-x11-server-Xorg xorg-x11-xinit xdotool xrandr" ;;
void:i3) echo "i3 xorg-minimal xinit xdotool xrandr" ;;
alpine:i3) echo "i3wm xorg-server xinit xdotool xrandr xf86-input-libinput" ;;
gentoo:i3) echo "x11-wm/i3 x11-base/xorg-server x11-apps/xinit x11-misc/xdotool x11-apps/xrandr" ;;
gentoo:sway) echo gui-wm/sway ;;
*:sway) echo sway ;;   # Arch, Fedora, Void, Alpine
```

`without_x_server()` also left out `xorg-server`, `xorg-x11-server-Xorg`, `xorg-minimal` and
`x11-base/xorg-server`.

### 3.5 Package manager commands (install.sh)

| Family | Shown to the user (`install_hint`) | Run by the installer (`pkg_install`) |
|---|---|---|
| Arch | `sudo pacman -S <pkgs>` | `pacman -S --needed --noconfirm <pkgs>` |
| Fedora | `sudo dnf install <pkgs>` | `dnf install -y <pkgs>` |
| Void | `sudo xbps-install <pkgs>` | `xbps-install -Sy <pkgs>` |
| Alpine | `doas apk add <pkgs>` | `apk add <pkgs>` |
| Gentoo | `sudo emerge <pkgs>` | `emerge --noreplace <pkgs>` |

### 3.6 Software updates (control_updates.py)

Managers, in detection order (`apt`, then these, with `zypper` between pacman and xbps):

```python
Manager("dnf","DNF",("dnf","-q","check-update"),parse_dnf,("dnf","-y","upgrade","--refresh"),ok_codes=(0,100)),
Manager("pacman","pacman",("checkupdates",),parse_pacman,("pacman","-Syu","--noconfirm"),ok_codes=(0,2),
        fallback=("pacman","-Qu"),fallback_ok=(0,1)),   # checkupdates is in pacman-contrib
Manager("xbps","XBPS",("xbps-install","-Mun"),parse_xbps,("xbps-install","-Syu","-y")),
Manager("apk","apk",("apk","version","-l","<"),parse_apk,("sh","-c","apk update && apk upgrade"),refresh_argv=("apk","update")),
```

`_TOOL` (the program that marks the manager as installed): `dnf`, `pacman`, `xbps-install`, `apk`.
`_LISTS` (how old the package lists are): `/var/cache/dnf`, `/var/lib/pacman/sync`, `/var/db/xbps`,
`/var/cache/apk`. The `Manager.fallback` / `fallback_ok` fields and the fallback branch in `_list()` only existed
for pacman.

The parsers:

```python
def parse_dnf(text):
    """`dnf -q check-update`: 'firefox.x86_64   128.0-1.fc40   updates'. Stops at 'Obsoleting Packages'."""
    found=[]
    for line in text.splitlines():
        if line.lower().startswith(("obsoleting","security:","last metadata")): break
        parts=line.split()
        if len(parts)==3 and "." in parts[0] and not line.startswith(" "):
            found.append(Update(parts[0].rsplit(".",1)[0],parts[1],"",parts[2]))
    return found

_PACMAN=re.compile(r"^(\S+)\s+(\S+)\s+->\s+(\S+)")
def parse_pacman(text):
    """`checkupdates` or `pacman -Qu`: 'linux 6.9.7.arch1-1 -> 6.9.8.arch1-1' (an '[ignored]' one is left out)."""
    found=[]
    for line in text.splitlines():
        m=_PACMAN.match(line.strip())
        if m and "[ignored]" not in line: found.append(Update(m.group(1),m.group(3),m.group(2)))
    return found

def parse_xbps(text):
    """`xbps-install -Mun`: 'firefox-128.0_1 update x86_64 https://repo-default.voidlinux.org/current …'."""
    found=[]
    for line in text.splitlines():
        parts=line.split()
        if len(parts)>=2 and parts[1] in ("update","install") and "-" in parts[0]:
            name,version=parts[0].rsplit("-",1); found.append(Update(name,version))
    return found

_APK=re.compile(r"^(\S+?)-(\d\S*-r\d+)\s+<\s+(\S+)")
def parse_apk(text):
    """`apk version -l '<'`: 'busybox-1.36.1-r28   < 1.36.1-r29' (the first line is a header)."""
    found=[]
    for line in text.splitlines():
        m=_APK.match(line.strip())
        if m: found.append(Update(m.group(1),m.group(3),m.group(2)))
    return found
```

Their tests (package/tests/test_control.py):

```python
text="\nfirefox.x86_64                 128.0-1.fc40               updates\nkernel.x86_64   6.9.7-200.fc40   updates\nObsoleting Packages\ngrub2.x86_64  1:2.06-1  updates\n"
self.assertEqual([u.name for u in upd.parse_dnf(text)],["firefox","kernel"])
self.assertEqual(upd.parse_pacman("linux 6.9.7.arch1-1 -> 6.9.8.arch1-1\nmesa 1 -> 2 [ignored]\n"),[upd.Update("linux","6.9.8.arch1-1","6.9.7.arch1-1")])
self.assertEqual(upd.parse_xbps("firefox-128.0_1 update x86_64 https://repo-default.voidlinux.org/current 1234 5678\n"),[upd.Update("firefox","128.0_1")])
self.assertEqual(upd.parse_apk("Installed:                                Available:\nbusybox-1.36.1-r28  < 1.36.1-r29\nlibcrypto3-3.3.1-r0 < 3.3.1-r3\n"),
                 [upd.Update("busybox","1.36.1-r29","1.36.1-r28"),upd.Update("libcrypto3","3.3.1-r3","3.3.1-r0")])
self.assertEqual(upd.detect(which=lambda c:"/usr/bin/"+c if c in ("pacman","flatpak") else None).id,"pacman")
```

### 3.7 SSH server and Flatpak installs (control_ssh.py, control_flatpak.py)

| Family | SSH server | Flatpak |
|---|---|---|
| Fedora | `dnf install -y openssh-server` | `dnf install -y flatpak` |
| Arch | `pacman -S --needed --noconfirm openssh` | `pacman -S --needed --noconfirm flatpak` |
| Void | `xbps-install -y openssh` | `xbps-install -y flatpak` |
| Alpine | `apk add openssh-server` | `apk add flatpak` |

The SSH page's service switch only works with systemd (`service_argv` returns None without it); the sshd unit is
`sshd` on Fedora and Arch. Void (`ln -s /etc/sv/sshd /var/service/`) and Alpine (`rc-update add sshd`) would need
their own commands.

### 3.8 Systems without systemd (Void/runit, Alpine/OpenRC, Gentoo/OpenRC, Artix, Devuan without systemd)

Removed:

- **Power actions** (`system_actions.py`): without systemd running, Sleep, Reboot and Shut down used elogind's
  `loginctl suspend|reboot|poweroff`, else the plain commands: `zzz` (Void), `pm-suspend`, or `loginctl suspend` for
  sleep; `reboot`; `poweroff`. Those plain commands need root, so `privilege.PLAIN_ROOT_COMMANDS`
  (`reboot poweroff halt shutdown zzz ZZZ pm-suspend`) sent them straight to doas/sudo. The message when nothing
  worked was "TVWCS needs systemd, elogind (loginctl), or the reboot/poweroff/zzz commands." Tests:
  `command_for(a, which=<loginctl, reboot, poweroff>, systemd=False)` → `["loginctl", verb]`; with
  `zzz, reboot, poweroff` → `["zzz"], ["reboot"], ["poweroff"]`.
- **The power sudo rule** (install.sh `power_commands`): also allowed `loginctl suspend|reboot|poweroff` and
  `reboot`, `poweroff`, `zzz` with no arguments (written as `"<path> \"\""` in sudoers and `args` alone in doas).
- **Automatic login on runit** (install.sh): `init_system` answered `runit` when `/etc/sv/agetty-tty1` existed and
  `sv` was installed (and `/run/systemd/system` did not). Setting it up:

  ```sh
  CONF=$ETC/sv/agetty-tty1/conf
  as_root sh -c 'cp "$1" "$1.tvwcs-backup" && sed "s/^\([[:space:]]*\)GETTY_ARGS=\"*\([^\"]*\)\"*/\1GETTY_ARGS=\"--autologin $2 \2\"/" "$1.tvwcs-backup" > "$1"' sh "$CONF" "$1"
  grep -q -- '--autologin' "$CONF" || echo "GETTY_ARGS=\"--autologin $1 --noclear\"" | as_root tee -a "$CONF" >/dev/null
  ```

  Detecting it was already set: `grep -q -- '--autologin' "$ETC/sv/agetty-tty1/conf"`. Starting it now:
  `as_root sv restart /var/service/agetty-tty1` (`TVWCS_VAR` overrode `/var` for tests). Test: `test_runit_console_login`
  turned `GETTY_ARGS="--noclear"` into `GETTY_ARGS="--autologin tv --noclear"` and kept `conf.tvwcs-backup`.
- **Display managers on runit** (install.sh `login_manager`): a DM counted as installed when `$ETC/sv/<dm>` and
  `/var/service/<dm>` both existed.
- **PipeWire autostart** (`data/tvwcs.conf`): without systemd nothing starts PipeWire, so the fragment ran

  ```
  exec --no-startup-id sh -c '[ -d /run/systemd/system ] || ! command -v pipewire >/dev/null || pgrep -u "$(id -u)" -x pipewire >/dev/null || (pipewire & sleep 1 && (wireplumber & pipewire-pulse &))'
  ```

Still needed to support them properly (never done):

- Autologin on OpenRC (Alpine: `agetty` options in `/etc/conf.d/agetty.tty1`, or `/etc/inittab` with
  `agetty --autologin`; Gentoo: `/etc/inittab`), and on s6 (Artix).
- Starting and stopping sshd: `sv`/`ln -s /etc/sv/sshd /var/service` on Void, `rc-service`/`rc-update` on OpenRC.
- Starting PipeWire for the session (the fragment line above, or each distribution's way).
- `XDG_RUNTIME_DIR` may be unset without elogind; `session.py` already falls back to `~/.cache/tvwcs`.
- Network time on the Date & time page assumes `timedatectl`.
- Test every Settings page there: Bluetooth and NetworkManager polkit rules differ, and logind settings (lid, idle
  action) don't exist.

### 3.9 Hint strings that named other distributions

- `control_sound.py`: "the pulseaudio-utils, libpulse or pipewire-pulse package" (`libpulse` is Arch's).
- `control_display.py`: "x11-xserver-utils, or xorg-xrandr" (`xorg-xrandr` is Arch's).
- `control_ssh.py` docstring: sshd_config reads its drop-ins at its top "on Debian, Ubuntu, Fedora and Arch".
- `system_actions.py` and `privilege.py` docstrings about elogind, Artix, Gentoo, Void and Devuan.

### 3.10 openSUSE (removed in 3.0.2)

openSUSE was supported in 3.0.0 and 3.0.1, but never run on a real openSUSE system. Its code is in `a6a81ca`:

- `install.sh` `distro()`: `opensuse*|suse|sles) echo suse`.
- `install.sh` `pkg()`: gtk `python3-gobject gtk4`, pactl `pulseaudio-utils`, xss `libXss1`, vte `typelib-1_0-Vte-3_91`,
  font `google-opensans-fonts`; the rest used the generic names (`NetworkManager`, `bluez`, `pipewire
  pipewire-pulseaudio wireplumber`, `unclutter`, `xrandr`, `adwaita-icon-theme`).
- `install.sh` `wm_packages()`: `i3 xorg-x11-server xinit xdotool xrandr`; `without_x_server()` left out `xorg-x11-server`.
- `install.sh` `install_hint()` / `pkg_install()`: `sudo zypper install`, `zypper --non-interactive install`.
- `install.sh` `current_layout()`: read `XkbLayout`/`XkbVariant` from `/etc/X11/xorg.conf.d/*keyboard*.conf`.
- `control_updates.py`: `parse_zypper` (`zypper -q list-updates`: 'v | Repo | name | current | available | arch'),
  upgrade `zypper --non-interactive update`, refresh `zypper --non-interactive refresh`, lists `/var/cache/zypp/raw`.
- `control_ssh.py`: the `sshd` unit (Debian's is `ssh`); `INSTALL` and `control_flatpak.py` `INSTALL_FLATPAK` used
  `zypper --non-interactive install`.
- Hint strings in `control_sound.py`, `control_display.py` and `ui_control_pages.py` named openSUSE's packages.

What it still lacked, found by reading the code (none of it was tested):
- Tumbleweed upgrades with `zypper dup`, not `zypper update` (that only fits Leap); `list-updates` misses dup changes.
- Reboot detection: openSUSE keeps old kernels, so the "running kernel's modules folder is gone" check never fires;
  use `zypper needs-rebooting`.
- sudo asks for the root password by default (`Defaults targetpw`), but TVWCS's dialog asks for the user's own.
- Installing a package does not enable its service: `bluetooth`, `sshd` and `NetworkManager` (Leap may run wicked,
  which leaves the Network page read-only) need `systemctl enable --now`.
- firewalld is on by default: turning SSH on must also open the `ssh` service in the firewall.
- PackageKit can hold the zypp lock ("System management is locked").
- Unverified package names: `gtk4` (PyGObject needs `typelib-1_0-Gtk-4_0`), `unclutter`, `xinit`.
- Leap 15.6's python3 is 3.6 (TVWCS needs 3.9+): only Tumbleweed and Leap 16 can work.
- Test it end to end in a Tumbleweed VM (the HTPC has libvirt).

---

## 4. eCryptfs home folders with TVWCS's login screen (done in 3.4.3)

pam_ecryptfs crashed greetd because greetd's worker locks its memory and pam_ecryptfs, running as the user, needs more
stack than the default 8 MB memlock limit leaves. Since 3.4.3 TVWCS lifts greetd's limit with a systemd drop-in
(`GREETD_DROPIN` in `package/tvwcs/loginscreen.py`) and leaves PAM as it is, so eCryptfs homes unlock as usual.
Still to check once: a real login into an eCryptfs-encrypted home through the login screen (the home mounts, and
logging out unmounts it).

---

## 5. The screen saver while locked, on sway (not started)

The idle screen saver works on sway since 4.1.0: a gtk4-layer-shell overlay, one per output, with the library
preloaded (`screensaver.launch_env`). What is left is showing it while the computer is locked.

**Screen saver while locked:** swaylock only shows a still picture, and xsecurelock is X11 only. Options: a TVWCS
locker on ext-session-lock (gtk4-layer-shell 1.1+ has it; the compositor keeps the screen locked if the locker
crashes) that draws the saver and a password box checked through PAM (security-sensitive, effort L), or
swaylock-plugin (not packaged for Debian, so against the apt/Flatpak-only rule).
