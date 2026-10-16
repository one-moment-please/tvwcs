# Changelog

## 3.6.0 — 2026-10-16

**Quick Menu**
- A row's options (⋯, ← or a right-click) unfold in the Quick Menu itself instead of a dialog: upwards, just above their app or workspace, indented a little on both sides and with a small gap to the row above, so it is clear whose they are. ↑ from the row goes into them; Back, ⋯ again or moving away folds them.
- A workspace's individual apps unfold upwards too, above the workspace (▴ shows them, ▾ folds them).
- ⏻ has moved to the bottom right, beside the status icons. Its menu unfolds above it and now always has **Lock**, as well as Sleep, Reboot, Shut down and (with a login screen) Log out. The "Lock in the power menu" option is gone.
- The network, volume, Bluetooth and battery icons unfold a panel above the status row: the connection in use with its address and signal, and Wi-Fi on or off; mute, − and + for the output and the input; the connected Bluetooth devices with Disconnect, and Bluetooth on or off; the battery's estimated time left, or time until fully charged. Each panel has a button for its Settings page.
- The ⚙ Settings button and its option are gone: Settings is channel 000, and each status panel opens its own page.
- The ⊞ Applications button is now a thin strip along the whole right edge of the Quick Menu, in the gap before Applications, filled with triangles that point away from the Quick Menu when it opens Applications and back towards it when it closes them.

## 3.4.3 — 2026-10-16

- The real cause of "Logging in…" hanging is fixed: greetd's worker locks its memory, and pam_ecryptfs ran out of stack under the default memory-lock limit about one login in three. TVWCS's login screen now lifts greetd's limit (/etc/systemd/system/greetd.service.d/tvwcs-memlock.conf, removed when the login screen is turned off) and no longer rewrites greetd's PAM config: greetd's own comes back on update, so home folders encrypted with eCryptfs unlock as usual.
- The oval under "TV" in TVWCS's icon is filled in.

## 3.4.2 — 2026-10-16

- When the computer's login system stops answering (greetd waits for ever if a PAM module crashes while checking the password, as pam_ecryptfs can), the login screen says so and suggests restarting, instead of showing "Logging in…" until the computer is restarted. Any other failure while logging in is shown too.
- Logging in through TVWCS's login screen no longer goes through pam_ecryptfs when no home folder is encrypted with eCryptfs: TVWCS writes greetd's PAM config (/etc/pam.d/greetd) with that module left out, keeping greetd's own as greetd.tvwcs-backup and putting it back when the login screen is turned off, so pam_ecryptfs no longer needs unticking in pam-auth-update.
- The login screen fits a 1280×800 screen again: the keyboard, the Session row and Sleep / Restart / Shut down no longer overlap, the TV icon no longer crowds the user's tile, and the icon in the Session button is small.

## 3.4.1 — 2026-10-16

- TVWCS's login screen starts the "TVWCS (i3)" session again. Its command reached Debian's Xsession split in two, which showed "Xsession: unsupported number of arguments (2); falling back to default session."
- The login screen's on-screen keyboard is narrower: square letter keys with letters twice as tall, and a matching number pad.
- If greetd stops answering, the login screen says so after a while instead of showing "Logging in…" for ever.

## 3.4.0 — 2026-10-16

**TVWCS's login screen**
- A login screen in TVWCS's look: big tiles for the people who can log in, the password typed on a keyboard or with the remote on an on-screen keyboard (the full one, or a number pad), and a choice of session: TVWCS's own i3 and sway sessions, plain i3 and sway, and any other desktop installed. Sleep, Restart and Shut down are at the bottom. It remembers who logged in last, and each person's session and keyboard. It runs on greetd with cage, and starts X sessions such as i3 through startx and Wayland ones such as sway directly.
- The installer installs it by default where there is no login screen, also when the computer logs in by itself: the automatic login then goes through the login screen, which shows after logging out. Next to another login screen it is offered, and the default is no.
- Setting TVWCS up for sway with a login screen that cannot start sway (such as LightDM) now offers TVWCS's login screen first, then SDDM, then keeping it anyway or leaving sway out.
- Settings › Features turns it on or off. Off goes back to the login screen used before; with none, it asks whether to have no login screen (logging you in by itself) or to install SDDM or LightDM. Going back to one that cannot start sway, while in sway, warns and offers SDDM. Changes show from the next start. It also offers to update the login screen when its copy of TVWCS or its colours are out of date.

**Installer**
- It now asks where TVWCS should start: in your usual i3/sway session (the include line in its config), only in a "TVWCS" session of its own at the login screen, leaving the usual sessions alone, or both. Before, declining the login screen entry next to other desktops left TVWCS in neither. On a computer only for TVWCS it is asked when there is a login screen.
- With neither i3 nor sway installed, it offers to install both as well as either one.
- TVWCS has an icon: the letters TV, underlined with a thin oval. The TVWCS sessions at the login screen and TVWCS's login screen show it.

**Settings › User** (new)
- Change your name and password, see whether you are an administrator and which login screen is in use, and turn the automatic login at start-up on or off (with TVWCS's login screen, LightDM, SDDM or no login screen).

**Settings › Options**
- Open at login says that some applications, such as Steam, can start at login by themselves, and to set it to None when using that.

**On-screen keyboard**
- Password dialogs open with the keyboard a password was last typed on: the full keyboard at first, the number pad once a password was typed on it. Settings › Options › Password keyboard shows and changes it.

## 3.3.1 — 2026-10-16

- The Quick Menu no longer shows a line of key hints (OK Select, Back Close, ...) under its title and buttons.

## 3.3.0 — 2026-10-16

**Quick Menu**
- A new order, built up from the bottom: the status row stays at the bottom, the search field is just above it with the search results above the field (the best match nearest it; ↑ and ↓ move the highlight while you keep typing), then your open applications, then your favorites. The title and buttons stay at the top, with the key hints under them. Open applications and favorites are hidden when there are none; with neither, a note points to the guide (⊞) for the installed applications.
- The status row has a battery button on a computer with a battery: the charge in percent, with a mark while charging or plugged in. It opens Power and sleep.
- At a desk, the Quick Menu is only as tall as its contents, in the bottom-left corner with the same margins, and grows upwards as search results appear. Opening Applications stretches it to the full height, with everything but the title and buttons kept at the bottom.

**Hiding the mouse pointer**
- Only TVWCS's own session hides the pointer. The unclutter TVWCS starts now always ends with TVWCS, so it never outlives the i3 session.
- Installing unclutter-xfixes (by the installer or Settings › Features) no longer brings in unclutter-startup, which started unclutter in every X session, so other desktops hid their pointer too. When that autostart is already on, the installer explains it and offers to turn it off (a "no" is remembered).

**Installer**
- When the login screen cannot reliably start Wayland sessions (LightDM, as on Linux Mint, and other X-only ones), the installer warns before setting TVWCS up for sway and asks whether to go on. Going on suggests a login screen that can, such as SDDM or greetd with tuigreet. Declining leaves sway out; the answer is remembered for that login screen.

## 3.2.3 — 2026-10-16

- Power and sleep: the TVWCS logo's inner oval holds a QR code instead of a barcode, with its square-in-a-square finder pattern on the left.

## 3.2.2 — 2026-10-16

- In the Quick Menu, a workspace with more than one application has a square ▾ button between ⋯ and its name that shows or hides its individual apps. It is always visible, even when the options buttons are hidden, and the option has left the workspace's ⋯ menu. On the name, ← moves onto it; ← again opens the row's menu.
- The ⋯ options buttons on Quick Menu rows are half as wide as they are tall.

## 3.2.1 — 2026-10-16

- The screen saver covers every monitor, each with its own bouncing logo, instead of only the one in use. Any key, click or pointer movement ends it on all of them, and focus goes back to the workspace that had it.
- On a laptop whose battery times leave "Turn off the screen after" to the system, the screen turns off on battery again. TVWCS now keeps the system's own screen times when it takes them over, and gives them back when the setting is left to the system.

## 3.2.0 — 2026-10-16

**Quick Menu and Applications**
- On a TV the search field starts three digits wide with a short hint beside it. Typing a letter or a fourth digit hides the hint and widens the field. At a desk the hint line is gone.
- The search results scroll to keep the selected result in view when moving with the D-pad or arrow keys.
- At a desk, TVWCS no longer fills the screen: Applications is only as wide as its rows and most descriptions need. A description that does not fit scrolls by while its app is selected, and the pointer shows it in full.
- Opening Settings follows the rules for opening apps (full screen in its own workspace on a TV), instead of always opening as a tile.
- The volume and Bluetooth icons are hidden when their features are turned off.

**Settings**
- A new Features page turns sound, Bluetooth, network, storage, the terminal, Flathub apps, the screen saver, the screen saver when locked and hiding the pointer on or off. Turning one on installs what it needs. Turning one off can uninstall its packages, but only when nothing else installed needs them. A feature that is off keeps its tab, which offers to turn it on.
- Options: hide the mouse pointer after a time without moving, with − and + for the seconds. It is on by default on a TV (3 seconds) and now off at a desk. A hidden pointer no longer leaves anything highlighted: on i3 it is moved to the bottom-right corner of the focused window.
- Power and sleep: a laptop gets separate times plugged in and on battery, and a choice of what to do when the battery is nearly empty (shut down at 5% unless changed).
- Power and sleep: the screen saver can show while the computer is locked (i3, with xsecurelock). A key shows the password box; after a minute without one the screen saver comes back. The screen saver no longer runs while the screen is off.
- Power and sleep: the TVWCS logo's oval now holds a smaller oval with a barcode, instead of "TV".
- Date and time: setting the time by hand is one dialog with a box for each of year, month, day, hour and minute, each with ▲ and ▼, and AM/PM with the 12-hour clock. The three ways to set it are gone.
- Storage: partitions are indented under their drive, and say Mounted or Not mounted. Partitions of the running system (such as / and /home) are marked as part of the system and named after what they hold.
- When the Settings window is taller than it is wide, the tabs show only their icons and the "Settings" title is left out.

**Installer**
- A first install asks for everything or a minimal install (the Quick Menu, the applications list and basic Settings). `TVWCS_INSTALL=minimal` chooses it without asking.
- The packages of features that are turned off are no longer asked for.
- xsecurelock is offered for the screen saver when locked (i3).
- With an i3 config but no sway config, running sway on its own reads the i3 config and fails (for example on `tiling_drag modifier titlebar`). The installer now explains this, offers to create a sway config, and shows how to start TVWCS's sway session from a text console (`tvwcs-session sway`), for login screens that do not list it.
- The mouse pointer is no longer hidden by a line in `tvwcs.conf`; TVWCS hides it itself, as Options says.

## 3.1.0 — 2026-10-15

**Quick Menu**
- The search bar is selected when the Quick Menu opens, and it says you can type a channel number.
- Each row has one menu (⋯) with labelled choices: open in a new workspace or this one, the app's own actions, and Close when the app is open. It replaces the sliding options and the second popup.
- Channels run from 000 to 999. Channel 000 opens Settings: on the first start of 3.1, Settings moves to 000 unless another app already has it.
- Setting a channel shows three digit boxes that start empty each time, with a number pad.
- A slow app shows "Starting…" instead of a blank screen, and the Quick Menu can still be opened meanwhile. An app that is already running and only asks for attention when started again is brought to the front.
- With "Keep the Quick Menu open" on, the Quick Menu now comes back when Settings (or the last app on screen) closes, even when apps are open on other workspaces.
- A hidden mouse pointer no longer highlights what it was resting on.
- Search results no longer repeat an app's name when its profile has the same name.
- Password dialogs can show a number pad, with a key to switch to the full keyboard and back.

**Settings**
- Options: light or dark mode (dark by default), passed on to GTK, Flatpak and browser apps that follow the system's choice. A background colour from 18 swatches (dark grey by default), shown when no app is open and behind the Quick Menu. Password dialogs can open with the number pad.
- With the number pad chosen and SSH on, Settings recommends turning off SSH password login.
- Power and sleep: a screen saver (the DVD logo, TVWCS's logo or a picture of your own) with its own idle time and a preview.
- Date and time: set the time by hand in one of three ways: fields with ▲ and ▼, steps, or four digits.
- Network: an Ethernet port the Debian installer set up in `/etc/network/interfaces` showed as "not managed". Settings now says why and can hand it to NetworkManager, keeping a backup of the old file.
- A new Storage page: open, close and safely remove drives, and add, connect and disconnect network shares (Samba, NFS, SFTP, WebDAV, FTP).
- Choosing a hotkey ignores the D-pad, OK and Back, so the Clear button can be reached with a remote.

**Session**
- Apps no longer take up to half a minute to start when TVWCS is started from `startx`: the session's display is now passed to systemd and D-Bus, so the desktop portal that Flatpak apps wait for can start. Run the installer again (or log in again after updating) to get it.
- Updating TVWCS from Settings now checks first whether the new version needs packages that are not installed, lists them with what each is for, and installs them (asking for your password) before updating. This works from 3.1.0 on: the update to 3.1.0 itself still only lists them on the pages that need them.
- `install.sh --help` explains the installer's options, and `install.sh --missing` lists what is missing without installing anything. An unknown option no longer runs a full install.
- The installer offers udisks2, gvfs-backends, libglib2.0-bin, xdg-desktop-portal-gtk, python3-gi-cairo and x11-xserver-utils for the new features.
- The README lists what does not work on systems that are not Debian-based.

## 3.0.3 — 2026-10-15

- The install command in the README and the Debian guide now downloads the latest release instead of the development version on `main`. Every release includes `tvwcs.tar.gz` for it. Installing from `main` is still described, for testing.

## 3.0.2 — 2026-10-15

- openSUSE is no longer supported: TVWCS supports Debian and Debian-based systems (Debian, Ubuntu, Mint, Pop!_OS, Raspberry Pi OS) with systemd. The installer no longer installs packages with zypper, and Settings no longer offers zypper updates. `TODO.md` lists what bringing openSUSE back would take.

## 3.0.1 — 2026-10-15

- Displays: the resolution kept under i3 and the one kept under sway are saved separately, so one never overwrites the other. The first time sway runs, it uses the resolution kept under i3 (X calls the TV's port HDMI-1, sway calls it HDMI-A-1).
- On a 720p TV, TV Mode and 4K TV Mode shrink to fit, so Settings and the Quick Menu are no longer cut off. On a 1080p TV nothing changes.
- Power and sleep no longer mentions X when running under sway.

## 3.0.0 — 2026-10-15

**Supported systems**
- TVWCS now supports Debian and Debian-based systems (Debian, Ubuntu, Mint, Pop!_OS, Raspberry Pi OS) and openSUSE, with systemd. Arch, Fedora, Void, Alpine, Gentoo and systems without systemd are no longer supported; `TODO.md` lists what bringing them back would take.

**Installer**
- It first asks how TVWCS is used: as this computer's only interface (it can log in and start TVWCS at boot, as before), or next to your other desktops. The second adds "TVWCS (i3)" and "TVWCS (sway)" to the login screen, with TVWCS's own session config in `~/.config/tvwcs/`. It never sets up automatic login, and adding TVWCS to your usual i3 or sway config is optional (default no). `TVWCS_SETUP=dedicated` or `alongside` answers the question.
- It starts by saying what it found: a login screen, other desktops, i3 and sway.
- It offers an icon theme and the Open Sans font when they are missing.

**Quick Menu**
- An on-screen keyboard and number keypad: press OK on the empty search field to type with a remote.
- The launch profile editor and an app's list of profiles open inside the TVWCS window and work fully with a remote: each field is a row, with Save, Cancel and Delete. A PIN-protected profile asks for its PIN first.
- A welcome on first start asks whether TVWCS is used on a TV or at a desk.
- Errors, messages and a "Starting <app>…" card show in the window.
- New icons: ⊞ opens Applications, ⋯ opens a row's options, ≡ starts an app with one of its own shortcuts.
- "Guide" is now called Applications, and its channel list Channels.
- On a TV, the key hints at the bottom name the remote's keys (OK, Back).
- Text has more contrast, and fades follow the new Reduce motion option.
- Plain launch profiles keep working when their app is renamed (such as the old "Control Panel").

**Settings app**
- A new **Remote and hotkeys** page (`tvwcs settings hotkeys`). TVWCS's own updates moved to **Software updates**.
- **Where apps open** is one choice: Full screen, one per workspace; Side by side; or As each app's profile says.
- Choosing TV turns on button hints. Interface size applies at once.
- New options: accent colour, screen edge margin (for TVs that cut off the edges), and Reduce motion.
- Pages show key hints at the bottom.
- The launcher is called "TVWCS Settings" and is hidden in GNOME and KDE menus.

**Lock screen**
- An optional TVWCS lock screen (Settings › Power and sleep › Lock screen, off by default). It shows "Locked" and says whose password to type, using i3lock (swaylock on sway). The power menu's Lock, the idle lock and xss-lock (when the i3 config starts it) use it; switching back restores the previous locker. `tvwcs lock` locks by hand.

## 2.11.2 — 2026-10-15

- TV mode: when the Quick Menu is kept open over an empty screen and a window opens from elsewhere (Settings started from a terminal or a hotkey, an app started by its hotkey), the menu now steps aside for it. Before, the new window opened hidden under the menu while taking the keyboard.

## 2.11.1 — 2026-10-15

- Hotkeys set to a remote's media keys (such as Search, Mail or Tools) work: GTK names those keys without the "XF86" that i3 needs, so i3 ignored the bindings ("Could not translate string to key symbol"). They are now written as XF86Search and so on; no need to set them again.
- TV mode: with nothing open, the Quick Menu shows about 2 seconds after TVWCS starts instead of 10 (unless it is set to open an app at login), and the bar hides again within about 4 seconds after i3 reloads its config.
- README: new screenshots of the Quick Menu, with its clock and status icons.

## 2.11.0 — 2026-10-15

**Quick Menu**
- The bottom of the Quick Menu shows the time and date, and icons for the network (wired, Wi-Fi with its signal strength, or offline), the volume, Bluetooth and waiting updates (only when there are some). Each opens its page of Settings; the clock opens Date and time. They are reached with ↑ from the top of the menu, or ↓ past its last row.

**TV mode**
- The i3 (or sway) bar is hidden, since the Quick Menu now shows the time and status. It comes back as it was when TVWCS stops, or when Options › Hide the i3 bar is turned off.
- While no application is open, the Quick Menu stays on screen (Esc does not close it), and it comes back by itself when the last application closes. Options › Keep the Quick Menu open turns this off.

**Settings app**
- A **Date and time** page: the time zone, chosen as a region and then a city; setting the time from the network; and a 12-hour or 24-hour clock for the Quick Menu. Changes go through `timedatectl`, asking for your password when polkit needs one.
- After installing updates, the Quick Menu's updates icon counts them again.

**Installer**
- When an X server is already installed, such as XLibre, `install.sh` offers i3 for it and no longer installs the Xorg server over it.

## 2.10.4 — 2026-10-15

- Updating from Settings restarts TVWCS again. Updating 2.10.2 to 2.10.3 installed it but left the old TVWCS running, with nothing said: Settings imported the new `main.py` to send the restart, and that needed a name the old modules still loaded in Settings did not have. Settings now sends the request itself, and the new start-up code lives in a module of its own, so an update from 2.10.2 or 2.10.3 restarts properly.

## 2.10.3 — 2026-10-15

- Flatpak apps launch from the Quick Menu and the guide, and show their icons, when the session's `XDG_DATA_DIRS` lacks Flatpak's folders (X started with `startx`, or Flatpak installed during this login): TVWCS adds them for itself at start-up, the way Flatpak's profile script does. Before, such an app was listed but nothing happened when it was chosen.
- `install.sh` no longer lists libXss (`libxss1`) as missing when it is installed: it asked `ldconfig`, which is not on an ordinary user's PATH on Debian.
- README: new screenshots of the Quick Menu and the Applications guide, taken on a TV.

## 2.10.2 — 2026-10-15

**Releases**
- Each change merged into TVWCS is now released at once as a prerelease, and marked as the latest release once it has been tested on a TV computer (the Promote workflow).

**Settings app**
- Options: **Include prereleases** makes Check for updates offer prereleases too, and **Roll back to the latest release** installs the release marked latest, even when it is older than the one installed.
- System information: a session started with `startx` from a console shows as X11, not "tty".
- A page's rows drawn again behind a dialog (such as the update dialog) keep their scroll position.
- Power and sleep: where `xss-lock` runs (Debian's and Ubuntu's stock i3 config starts `xss-lock -- i3lock`), turning the screen off also locked the computer, even with "Lock after" set to Never, so a TV woke up to a password prompt. The page now says so, and a **Locks when the screen turns off** row comments the line out of the i3 config (keeping a copy as `config.before-tvwcs`) and stops xss-lock.
- Power and sleep: "Closing the lid" is only shown on a computer that has a lid.
- Sound: when the volume or mute cannot be changed, the reason is shown and the page shows the real values again, instead of looking changed. − from a volume above 100 % (set by another program) goes down 5 % at a time rather than straight to 100 %. After choosing an output, the selection stays on it.
- Network: Wi-Fi names with characters outside ASCII (such as "Taylor’s") show and join correctly: the tools Settings runs now use the C.UTF-8 locale instead of C.
- Network: joining Wi-Fi on a computer that is also on a wired connection NetworkManager does not manage (ifupdown on Debian) no longer moves all traffic to Wi-Fi: its route metric is set above the wired one, so Wi-Fi stays as a backup.
- Displays: "Keep these display settings?" now starts on Go back, so pressing Enter on a screen that shows nothing undoes the change.
- Long choice lists open scrolled to the current choice.

## 2.10.1 — 2026-10-15

**Installer**
- `install.sh` asks whether TVWCS will be used on a TV or a desktop monitor (until it is answered), and sets the interface size and how apps open to match.

**Settings app**
- New **Apps** page, a store for Flatpak apps from Flathub: a grid of tiles with icons, names and summaries; Featured apps that suit a TV first, then categories (Video & music, Games, Internet, Graphics & photos, Office & education, Utilities), a search typed on the on-screen keyboard, and the installed apps. A tile opens the app's description with Install, or Open and Remove. Apps are installed for the user (`flatpak install --user`, no password); one installed system-wide is removed as root. The page offers to install Flatpak with the package manager and to set up Flathub for the user, and reads the catalog flatpak downloads (`flatpak update --appstream`), so it works with the remote alone. `tvwcs settings apps` opens it.
- Options: a new **Used on** row (A TV, or A desktop monitor) sets the interface size and where apps open: on a TV every app opens in a workspace of its own; on a desktop monitor apps open tiled in the current workspace. Each can still be changed on its own. On a TV, a window alone on its workspace also has no border or title bar (i3 and sway's `hide_edge_borders smart`, with thin borders instead of title bars when windows share a workspace).
- Options: **Open at login** is now one choice: None, TVWCS Quick Menu, Last application or Chosen application; choosing the last shows an **Application** row to pick it with. The separate "Open the Quick Menu at login" switch is gone (a config that had it on, with nothing else chosen, opens the Quick Menu).
- The applications guide finds Flatpak apps even when the session's `XDG_DATA_DIRS` does not include Flatpak's folders (as right after installing Flatpak, before logging in again).

## 2.10.0 — 2026-10-14

**Settings app**
- New application, `tvwcs settings` (opened by the Quick Menu's ⚙ and listed under System in the applications guide; `tvwcs control` still works): Options, Sound, Displays, Bluetooth, Software updates, System information, Terminal and Network as vertical tabs on the left, in the TVWCS Metro style and at its interface size, and usable with a D-pad alone.
- Displays: resolution and refresh rate of each display; with several, which are on, how they are arranged and (X11) which is primary, through `xrandr` or `swaymsg`. Changes that can blank a screen go back after 15 seconds unless kept, and kept settings are applied again when TVWCS starts with the same displays.
- Options: TVWCS's own settings, moved here from the applications guide's ⚙ view: the Quick Menu's buttons, interface size, behavior, what opens at login, hotkeys, application hotkeys and TVWCS's own updates. Each change is saved and the running TVWCS reads it again at once. The power buttons are no longer here; they are in the Quick Menu's power menu.
- Sound: volume and mute of the output and the input, and which output and microphone to use (sound already playing follows), through `pactl` (PipeWire or PulseAudio). Outputs of a sound card's other profiles are listed too (often HDMI, which PipeWire only shows once the card is switched to it), and choosing one switches the card over. With no sound card at all, it names the firmware packages to install.
- Power and sleep: turn the screen off, lock and sleep after a chosen time without input (or never), skipped while sound plays or an app holds an idle inhibitor; TVWCS keeps the times (watching the X idle time on i3, running `swayidle` on sway, which calls the new `tvwcs idle …` back). The page also shows X's blanking and DPMS times and logind's idle action and lid switch. `install.sh` lists `libxss1` (i3) or `swayidle` (sway) when missing.
- Bluetooth: on and off, search, pair, connect, disconnect and forget devices, with battery levels, through `bluetoothctl`.
- Software updates: waiting updates from apt, dnf, pacman, zypper, xbps or apk and from Flatpak; installs them with the output on screen, asking for the sudo password in an on-screen dialog when needed; offers a restart when one is needed.
- System information: computer, processor, memory, graphics (named from the kernel driver without `lspci`), displays, every drive in use, battery and versions; and remote access: the SSH server on or off (or installed), passwords or keys only (refused while the user has no key), and the command, user, local name and IP addresses to connect with.
- Terminal: your shell in a full terminal (VTE for GTK 4), or a one-command-at-a-time console without VTE.
- Network: Ethernet and Wi-Fi status, connect and disconnect, Wi-Fi on and off, join (with a password) and forget networks, and IP settings, through NetworkManager's `nmcli`; shown read-only from `ip` without it.
- Text is typed on a keyboard or on an on-screen keyboard driven by the D-pad.
- Terminal: coming in from the tabs lands on the buttons above the terminal, and Esc or Back inside the terminal goes back up to them, so they can always be reached with a remote. New **Tab** and **Esc** buttons type those keys into the shell.
- Network: Wi-Fi networks are searched for only when you choose **Search for networks**; the page no longer makes the adapter scan in the background. Each connection has an **IP settings** row that shows whether it uses DHCP and opens its settings: a fixed IP address, default gateway and DNS servers (filled in from the ones in use), or back to automatic (DHCP).
- Software updates: when downloading the package lists or installing updates finishes, the page says so, with the time and what the check found ("Everything is up to date." or how many updates are available). `apt-get update` prints no "Done" when it is not run in a terminal, so the log used to end at "Reading package lists...".
- `install.sh` installs the Settings app's launcher (with an action for each page) and lists the optional tools its pages use.

**Quick Menu**
- At the top: ⚙ opens Settings and ⏻ opens a power menu with Sleep, Reboot and Shut down, plus Log out when a login screen is installed and Lock when it is switched on in Options. ⚙ and ✕ can be hidden in Options.
- The applications guide no longer has the ⚙ button that switched it to TVWCS's settings.

**Installer**
- New guide, `docs/INSTALL-DEBIAN.md`: Debian's network installer with no desktop, SSH and Avahi, then TVWCS installed over SSH from another computer.
- The mouse pointer hides after 3 seconds without moving and comes back when it moves: sway does it itself, and in i3 the TVWCS config runs `unclutter`, which `install.sh` offers to install.
- `install.sh` lists every missing package with what it is for (including PipeWire, with `pipewire-pulse` and WirePlumber, when no sound server is installed) and offers to install them all with the package manager (on a terminal, on a known distribution). On Debian this adds `dbus-user-session`, which WirePlumber needs on a minimal install, and PipeWire is started for the current user right away; systemd starts it at every log-in after that. Without systemd, the TVWCS i3/sway config starts PipeWire, WirePlumber and `pipewire-pulse` when they are not running.
- With neither i3 nor sway installed, `install.sh` offers to install one with the package manager (i3 with Xorg, `startx`, `xdotool` and `xrandr`, recommended; or sway), then sets it up and offers the automatic login.
- On a computer with no login screen, `install.sh` offers (default no) to log the user in automatically at boot and start i3 (through `startx`) or sway, through systemd's or runit's console login and the login shell's profile. When set up, TVWCS opens its Quick Menu at log-in, and the session starts on the screen as soon as the install is done.
- `install.sh` works over SSH: it reaches the running i3 or sway through its socket (no DISPLAY needed) to reload it and restart TVWCS, never starts TVWCS where there is no display, and says to use `ssh -t` when it has no terminal to ask on.

## 2.7.0 — 2026-10-14

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

**Other distributions, and systems without systemd**
- `install.sh` names missing packages for the distribution it runs on (apt, pacman, dnf, zypper, xbps, apk, emerge), finds the keyboard layout where Arch and Fedora keep it, and no longer needs `cmp` (minimal Fedora and Arch installs lack it).
- Sleep, Reboot and Shut down use systemd when it runs the system, else elogind's `loginctl`, else `zzz` / `reboot` / `poweroff`; a refused command now shows its error instead of failing silently. Lock says so when no screen locker is installed.
- Without `XDG_RUNTIME_DIR`, TVWCS keeps its PID file and hotkey requests in `~/.cache/tvwcs` (it used the shared `/tmp`). *Open at login* now records which login it ran in, so it still runs once per login where nothing empties that folder at logout. A PID file left from before a reboot no longer blocks TVWCS from starting.

**Power actions that need a password**
- When Sleep, Reboot or Shut down needs root (no systemd or elogind, or polkit refuses because no agent can ask), TVWCS tries a no-password `doas` or `sudo` rule, then asks for your sudo password in its own dialog: a hidden field for a keyboard (such as the one on the back of a remote) and a keypad for numeric passwords. The password goes to `sudo -S` through a pipe and is never stored; a wrong one asks again, up to 3 times. A user sudo refuses, or a sudo that demands a terminal, gets a clear message.
- `install.sh` offers (on a terminal, default no) a no-password rule for exactly those commands: `/etc/sudoers.d/zz-tvwcs-power-<user>`, checked with `visudo` first and named to come after the user's other sudo rules (the last match wins), or lines in `/etc/doas.conf`, checked with `doas -C`. It says when such a rule is already in effect.

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
