#!/bin/sh
# Installs TVWCS into ~/.local/share/tvwcs (the program; your data stays in ~/.config/tvwcs) and sets up the
# window manager. It first asks how TVWCS is to be used:
#   1) "dedicated": this computer is only for TVWCS. It offers to add TVWCS's include line to your i3 and/or sway
#      config (or to create one from the standard template), and, without a login screen, to log you in and start
#      i3 or sway at boot.
#   2) "alongside": next to your other desktops. TVWCS gets a session of its own (its own i3 / sway config in
#      ~/.config/tvwcs, and a "TVWCS" entry at the login screen); automatic login, the login screen's default session
#      and your shell's profile are never touched, and adding TVWCS to your usual i3 / sway config is only an option.
# It also moves an install from the old location (~/.config/i3/tvwcs) over. Every change to a config of yours is
# asked first, and the file is backed up as <config>.tvwcs-backup. Safe to re-run to upgrade; your settings in
# ~/.config/tvwcs are untouched. Supported: Debian and its family (apt), with systemd.
#
# Environment: TVWCS_SETUP=dedicated|alongside answers the first question (default without a terminal: the choice
# made last time, else dedicated). TVWCS_DEST=<folder> installs somewhere else. TVWCS_ASSUME_YES=1 answers yes to
# adding or updating the include line, adding the login screen entry and removing the old copy (for scripted installs).
# TVWCS_MIGRATE=1 answers yes only to moving from the old location: updating the include line and removing the old
# copy (the in-app updater sets it once you have agreed to the move there).
# TVWCS_NO_RESTART=1 skips the offer to restart a running TVWCS. TVWCS_WMS="i3 sway" chooses which window managers
# to set up (default: those installed; with neither installed, it offers to install one). TVWCS_ETC overrides /etc
# (where the standard config templates are), TVWCS_RUN overrides /run (where systemd is detected), and TVWCS_SHARE
# and TVWCS_BINDIR override /usr/share and /usr/local/bin (where the login screen's session entries go).
# TVWCS_INSTALL=full|minimal answers "what to install" (asked on a first install only; default full): a minimal install
# leaves out the software of the optional features (Settings > Features turns them on later).
# Options: --missing only lists the packages this version needs that are not installed, one per line as
# "need<TAB>packages<TAB>what for", and changes nothing (the in-app updater asks about them before updating).
# --help shows this text.
set -eu
CHECK_ONLY=""
case "${1:-}" in
    "") ;;
    --missing) CHECK_ONLY=1 ;;
    -h|--help) sed -n '2,/^set -eu/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
    *) echo "install.sh: unknown option $1 (try --help)" >&2; exit 2 ;;
esac
RUN_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)  # folder holding this script (repo scripts/, or a release root)

# Work out the source layout: repository (script lives in scripts/) vs. release/installed (script at the root).
if [ -d "$RUN_DIR/../package/tvwcs" ]; then
    SRC=$(CDPATH= cd -- "$RUN_DIR/.." && pwd)          # repository root
    PKG=$SRC/package/tvwcs; BIN=$SRC/package/bin/tvwcs; CONF=$SRC/data/tvwcs.conf; DOCS=$SRC; LAUNCHER=$SRC/data/com.tvwcs.ControlPanel.desktop
elif [ -d "$RUN_DIR/tvwcs" ]; then
    SRC=$RUN_DIR                                        # release zip or already-installed folder
    PKG=$SRC/tvwcs; BIN=$SRC/bin/tvwcs; CONF=$SRC/tvwcs.conf; DOCS=$SRC; LAUNCHER=$SRC/com.tvwcs.ControlPanel.desktop
else
    echo "install.sh: cannot find the TVWCS files next to this script (expected package/tvwcs/ or tvwcs/)." >&2
    exit 1
fi
[ -f "$PKG/main.py" ] || { echo "install.sh: $PKG does not look like the tvwcs package." >&2; exit 1; }
[ -f "$CONF" ] || { echo "install.sh: missing window manager config fragment $CONF." >&2; exit 1; }

CONFIG_HOME=${XDG_CONFIG_HOME:-$HOME/.config}
DEST=${TVWCS_DEST:-${XDG_DATA_HOME:-$HOME/.local/share}/tvwcs}
LEGACY=$CONFIG_HOME/i3/tvwcs                          # where TVWCS 2.6 and older were installed
ETC=${TVWCS_ETC:-/etc}
SHARE=${TVWCS_SHARE:-/usr/share}
BINDIR=${TVWCS_BINDIR:-/usr/local/bin}
case "$DEST" in
    *\'*|*\"*|*"
"*) echo "install.sh: the install folder may not contain quotes or line breaks: $DEST" >&2; exit 1 ;;
esac
case "${TVWCS_SETUP:-}" in
    ""|dedicated|alongside) ;;
    *) echo "install.sh: TVWCS_SETUP must be dedicated (this computer is only for TVWCS) or alongside (next to other desktops), not \"$TVWCS_SETUP\"." >&2; exit 1 ;;
esac

# ------------------------------------------------------------------ asking
# ask "question" [migrate] -> yes (0) or no (1). Enter means yes. Without a terminal it is no, unless TVWCS_ASSUME_YES
# is set, or TVWCS_MIGRATE for a question marked "migrate".
ask() {
    if [ -n "${TVWCS_ASSUME_YES:-}" ]; then return 0; fi
    if [ "${2:-}" = migrate ] && [ -n "${TVWCS_MIGRATE:-}" ]; then return 0; fi
    [ -t 0 ] || return 1
    printf "%s [Y/n] " "$1"
    read -r ANSWER || return 1
    case "$ANSWER" in [Nn]*) return 1 ;; *) return 0 ;; esac
}
ask_yes() {   # like ask, but only on a terminal (TVWCS_ASSUME_YES never installs packages). Enter means yes.
    [ -t 0 ] || return 1
    printf "%s [Y/n] " "$1"
    read -r ANSWER || return 1
    case "$ANSWER" in [Nn]*) return 1 ;; *) return 0 ;; esac
}
ask_no() {   # like ask, but only on a terminal, and Enter means no
    [ -t 0 ] || return 1
    printf "%s [y/N] " "$1"
    read -r ANSWER || return 1
    case "$ANSWER" in [Yy]*) return 0 ;; *) return 1 ;; esac
}

# ------------------------------------------------------------------ copy the program
same_file() {   # cmp comes with diffutils, which a minimal system may lack
    if command -v cmp >/dev/null 2>&1; then cmp -s "$1" "$2"; else [ "$(cksum < "$1")" = "$(cksum < "$2")" ]; fi
}
install_files() {
    # Upgrade in place: replace the program files, but never touch user data (~/.config/tvwcs) and
    # keep any hand-edited tvwcs.conf as a .bak. Old modules removed between versions are cleaned up.
    OLD_LIST=""
    [ -d "$DEST/tvwcs" ] && OLD_LIST=$(cd "$DEST/tvwcs" && ls *.py 2>/dev/null || true)
    mkdir -p "$DEST/tvwcs" "$DEST/bin"
    # The fragment starts TVWCS by its full path: point its exec line at this install.
    NEWCONF=$(mktemp); trap 'rm -f "$NEWCONF"' EXIT
    P="$DEST/bin/tvwcs" awk '/^exec --no-startup-id .*\/bin\/tvwcs\047?$/ { print "exec --no-startup-id \047" ENVIRON["P"] "\047"; next } { print }' "$CONF" > "$NEWCONF"
    if [ -f "$DEST/tvwcs.conf" ] && ! same_file "$NEWCONF" "$DEST/tvwcs.conf"; then
        cp "$DEST/tvwcs.conf" "$DEST/tvwcs.conf.bak"; echo "Existing tvwcs.conf saved as tvwcs.conf.bak"
    fi
    cp "$PKG"/*.py "$DEST/tvwcs/"
    for F in $OLD_LIST; do
        [ -f "$PKG/$F" ] || rm -f "$DEST/tvwcs/$F"      # stale module from an older version
    done
    find "$DEST/tvwcs" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
    cp "$BIN" "$DEST/bin/tvwcs"
    cp "$NEWCONF" "$DEST/tvwcs.conf"; cp "$SRC/VERSION" "$DEST/"
    for MD in README.md CHANGELOG.md PROJECT_OVERVIEW.md TODO.md LICENSE; do [ -f "$DOCS/$MD" ] && cp "$DOCS/$MD" "$DEST/"; done
    chmod +x "$DEST/bin/tvwcs"
    [ -f "$LAUNCHER" ] && cp "$LAUNCHER" "$DEST/"
    if [ -f "$(dirname "$LAUNCHER")/tvwcs-settings.svg" ]; then cp "$(dirname "$LAUNCHER")/tvwcs-settings.svg" "$DEST/"; fi
}

# The Settings app's launcher, so it is listed with the other applications (in the guide's System category). Its
# Exec lines (the panel, and an action for each of its pages) run this install's tvwcs by full path, quoted; a path
# the .desktop format would need escaped is skipped.
install_launcher() {
    [ -f "$LAUNCHER" ] || return 0
    case "$DEST" in *'$'*|*'`'*|*'\'*) echo "Skipped the Settings app's menu entry: $DEST has a character a .desktop file cannot hold. Run: '$DEST/bin/tvwcs' settings" >&2; return 0 ;; esac
    APPS=${XDG_DATA_HOME:-$HOME/.local/share}/applications
    mkdir -p "$APPS"
    # Its icon is TVWCS's own picture (icon themes such as Adwaita 4x no longer have a full-colour preferences-system).
    ICON=""; if [ -f "$DEST/tvwcs-settings.svg" ]; then ICON="$DEST/tvwcs-settings.svg"; fi
    P="$DEST/bin/tvwcs" I="$ICON" awk '/^Exec=tvwcs / { sub(/^Exec=tvwcs/, "Exec=\"" ENVIRON["P"] "\""); } /^Icon=/ && ENVIRON["I"] != "" { $0 = "Icon=" ENVIRON["I"] } { print }' "$LAUNCHER" > "$APPS/com.tvwcs.ControlPanel.desktop"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$APPS" 2>/dev/null || true
}

if [ -n "$CHECK_ONLY" ]; then :   # --missing: nothing is copied or changed
elif [ "$SRC" = "$DEST" ]; then
    echo "TVWCS is already installed in $DEST — nothing to copy. Re-running install.sh from that folder just re-checks your setup."
else
    install_files
fi
VERSION=$(cat "$SRC/VERSION" 2>/dev/null || echo "?")
[ -n "$CHECK_ONLY" ] || { install_launcher; echo "TVWCS $VERSION installed in $DEST"; }
# Run over SSH without a terminal (ssh host install.sh), nothing can be asked: every question is answered no.
if [ -z "$CHECK_ONLY" ] && [ ! -t 0 ] && [ -n "${SSH_CONNECTION:-}${SSH_CLIENT:-}" ] && [ -z "${TVWCS_ASSUME_YES:-}" ]; then
    echo "There is no terminal to ask questions on, so every question is answered no. To be asked, run: ssh -t <computer> <path>/install.sh"
fi

# An install in the old location is moved over: its hand-edited fragment backup comes along, and the hotkeys
# (which run its launcher by full path) are pointed at the new one.
MIGRATING=""
if [ -z "$CHECK_ONLY" ] && [ "$LEGACY" != "$DEST" ] && [ -f "$LEGACY/bin/tvwcs" ]; then
    MIGRATING=1
    echo "Found an older TVWCS in $LEGACY; moving it to $DEST."
    if [ -f "$LEGACY/tvwcs.conf.bak" ] && [ ! -f "$DEST/tvwcs.conf.bak" ]; then cp "$LEGACY/tvwcs.conf.bak" "$DEST/"; fi
fi

# Hotkeys live with your data, not with the program, so upgrades never reset them. TVWCS rewrites this file when
# you change a hotkey in Settings; here we only make sure it exists with the defaults so the include has a target.
HK="$CONFIG_HOME/tvwcs/hotkeys.conf"
if [ -n "$CHECK_ONLY" ]; then :
elif [ ! -f "$HK" ]; then
    mkdir -p "$(dirname "$HK")"
    {
        echo "# Generated by TVWCS Settings. Change hotkeys there; edits made here are overwritten."
        echo "# Keyboard: Quick Menu (Super (tap))"
        echo "bindcode --release 133 exec --no-startup-id '$DEST/bin/tvwcs' toggle"
        echo "# Remote: Quick Menu (F2)"
        echo "bindsym F2 exec --no-startup-id '$DEST/bin/tvwcs' toggle"
    } > "$HK"
    echo "Created default hotkeys in $HK"
elif [ -n "$MIGRATING" ] && grep -qF "$LEGACY/bin/tvwcs" "$HK"; then
    TMP=$(mktemp)
    OLD="$LEGACY/bin/tvwcs" NEW="$DEST/bin/tvwcs" awk '{ while ((i = index($0, ENVIRON["OLD"])) > 0) $0 = substr($0, 1, i-1) ENVIRON["NEW"] substr($0, i+length(ENVIRON["OLD"])); print }' "$HK" > "$TMP"
    cat "$TMP" > "$HK"; rm -f "$TMP"
    echo "Pointed your hotkeys at the new location ($HK)."
fi

# ------------------------------------------------------------------ what else is needed, in this distribution's terms
# TVWCS supports Debian and its family (apt), with systemd. Anything else is "unknown": the
# installer then only lists what to install by hand. TODO.md has the package names and commands other distributions
# had before, and what they would need again.
# distro -> the family whose package manager and names apply, from /etc/os-release (ID, then ID_LIKE)
distro() {
    ( if [ -r "$ETC/os-release" ]; then . "$ETC/os-release"; elif [ "$ETC" = /etc ] && [ -r /usr/lib/os-release ]; then . /usr/lib/os-release; fi; for D in ${ID:-} ${ID_LIKE:-}; do
        case "$D" in
            debian|ubuntu|linuxmint|pop|raspbian) echo debian; exit ;;
        esac
    done; echo unknown )
}
# pkg <need>: that need's package name here (gtk = GTK 4 and PyGObject). On an unknown distribution, the usual name.
pkg() {
    case "$(distro):$1" in
        debian:gtk) echo "python3-gi gir1.2-gtk-4.0" ;;
        *:gtk) echo "PyGObject GTK4" ;;
        # the Settings app's tools (optional): pactl, xrandr, bluetoothctl, nmcli, and VTE for its terminal
        debian:pactl) echo pulseaudio-utils ;;
        *:bluetoothctl) echo bluez ;;
        debian:nmcli) echo network-manager ;;                *:nmcli) echo NetworkManager ;;
        # sound: PipeWire with its PulseAudio layer (the Sound page talks to it with pactl) and its session manager
        debian:pipewire) echo "pipewire pipewire-pulse wireplumber dbus-user-session" ;;   # WirePlumber needs the session bus
        *:pipewire) echo "pipewire pipewire-pulseaudio wireplumber" ;;
        # hides the mouse pointer while it is still (i3; sway does it itself)
        debian:unclutter) echo unclutter-xfixes ;;
        # Power and sleep: the idle time on X11 (libXss), or swayidle on sway
        debian:xss) echo libxss1 ;;   *:xss) echo libXScrnSaver ;;
        debian:xrandr) echo x11-xserver-utils ;;
        debian:vte) echo gir1.2-vte-3.91 ;;
        debian:cairo) echo python3-gi-cairo ;;   *:cairo) echo "PyGObject-cairo" ;;
        *:vte) echo "VTE-for-GTK-4" ;;
        # the look: an icon theme (without one, apps show letter tiles and buttons text symbols), and Open Sans, the
        # first font of TVWCS's Metro theme that distributions package (Segoe UI and Selawik are not packaged)
        *:icons) echo adwaita-icon-theme ;;
        debian:font) echo fonts-open-sans ;;
        *:font) echo "Open-Sans" ;;
        *) echo "$1" ;;
    esac
}
install_hint() {
    case "$(distro)" in
        debian) echo "sudo apt install $1" ;;
        *) echo "install with your package manager: $1 (the usual names; yours may differ)" ;;
    esac
}
UNSUPPORTED_SAID=""
unsupported_note() {   # said once, before the first thing this installer cannot install here
    [ -z "$UNSUPPORTED_SAID" ] || return 0; UNSUPPORTED_SAID=1
    echo "This installer can only install packages on Debian and its family (Debian, Ubuntu, Mint, Pop!_OS, Raspberry Pi OS)."
    echo "Here, install what is listed with your own package manager; TODO.md (in $DEST) has the"
    echo "package names other distributions use."
}
as_root() {   # run a command as root, asking for the password on this terminal
    if [ "$(id -u)" = 0 ]; then "$@"
    elif command -v sudo >/dev/null 2>&1; then sudo "$@"
    elif command -v doas >/dev/null 2>&1; then doas "$@"
    else echo "Neither sudo nor doas is installed; cannot change the system's settings." >&2; return 1; fi
}

# ------------------------------------------------------------------ what this computer has
DISPLAY_MANAGERS="gdm gdm3 sddm lightdm lxdm xdm slim ly greetd emptty nodm entrance lemurs tbsm cdm"
login_manager() {   # the login screen installed here, or ""
    [ -e "$ETC/systemd/system/display-manager.service" ] && { echo display-manager.service; return; }
    for DM in $DISPLAY_MANAGERS; do
        command -v "$DM" >/dev/null 2>&1 && { echo "$DM"; return; }
    done
    echo ""
}
init_system() {   # systemd or other (TVWCS supports systemd only; TODO.md says what others would need)
    if [ -d "${TVWCS_RUN:-/run}/systemd/system" ]; then echo systemd; else echo other; fi
}
desktop_sessions() {   # the login screen's other sessions (GNOME, Plasma...), by file name; i3, sway and TVWCS's own left out
    for F in "$SHARE"/xsessions/*.desktop "$SHARE"/wayland-sessions/*.desktop; do
        [ -f "$F" ] || continue
        N=${F##*/}; N=${N%.desktop}
        case "$N" in tvwcs-*|i3|i3-with-shmlog|sway) continue ;; esac
        printf '%s ' "$N"
    done
}
installed() { if command -v "$1" >/dev/null 2>&1; then echo "$1 installed"; else echo "$1 not installed"; fi; }

# ------------------------------------------------------------------ how TVWCS is used here: the one question
# 1) dedicated: the computer is only for TVWCS (it logs in and starts TVWCS at boot), set up for the user running this.
# 2) alongside: next to other desktops. TVWCS gets its own session, picked at the login screen, and nothing about the
#    other sessions changes. Suggested when a login screen or another desktop is found, as running TVWCS through the
#    normal i3 / sway config would bring its hotkeys and autostart into that session too.
# The answer is kept in ~/.config/tvwcs/setup, so that re-running (or the in-app updater) keeps to it.
SETUP_FILE=$CONFIG_HOME/tvwcs/setup
if [ -z "$CHECK_ONLY" ]; then
SAVED_SETUP=$(cat "$SETUP_FILE" 2>/dev/null || true)
case "$SAVED_SETUP" in dedicated|alongside) ;; *) SAVED_SETUP="" ;; esac
DM=$(login_manager); OTHERS=$(desktop_sessions); OTHERS=${OTHERS% }
echo
echo "Found: $( [ -n "$DM" ] && echo "login screen ($DM)" || echo "no login screen" ), $( [ -n "$OTHERS" ] && echo "desktop sessions ($(echo "$OTHERS" | sed 's/ /, /g'))" || echo "no desktop sessions" ), $(installed i3), $(installed sway)."
if [ "$(distro)" = unknown ]; then unsupported_note; fi
if [ "$(init_system)" != systemd ]; then
    echo "This system does not run systemd. TVWCS supports systemd systems only: Sleep, Reboot and Shut down, the automatic"
    echo "login and the SSH switch in Settings will not work here. TODO.md (in $DEST) says what other systems would need."
fi
if [ -n "$SAVED_SETUP" ]; then SUGGEST=$SAVED_SETUP
elif [ -z "$DM" ] && [ -z "$OTHERS" ]; then SUGGEST=dedicated; else SUGGEST=alongside; fi
if [ -n "${TVWCS_SETUP:-}" ]; then SETUP=$TVWCS_SETUP
elif [ -t 0 ]; then
    if [ "$SUGGEST" = dedicated ]; then N=1; else N=2; fi
    printf "\nHow should TVWCS be set up?\n  1) This computer is only for TVWCS (it logs in and starts TVWCS at boot)\n  2) Next to my other desktops (choose TVWCS at the login screen)\nChoose 1 (only TVWCS) or 2 (next to other desktops) [%s]: " "$N"
    read -r ANSWER || ANSWER=""
    case "$ANSWER" in 1*) SETUP=dedicated ;; 2*) SETUP=alongside ;; *) SETUP=$SUGGEST ;; esac
else
    SETUP=${SAVED_SETUP:-dedicated}   # without a terminal, nothing new is set up: an upgrade keeps to the last choice
fi
mkdir -p "$(dirname "$SETUP_FILE")"; echo "$SETUP" > "$SETUP_FILE"
if [ "$SETUP" = alongside ]; then echo "Setting TVWCS up next to your other desktops."; else echo "Setting this computer up for TVWCS only."; fi
fi

# ------------------------------------------------------------------ everything, or a minimal install
# A minimal install has the Quick Menu, the applications list and the Settings pages that need nothing more. The
# optional features' packages (sound, Bluetooth, network, storage, the terminal, Flathub apps, the screen saver,
# hiding the pointer) are not installed, and the features whose software is missing start turned off; Settings >
# Features turns them on, installing what they need. Asked on a first install only: later runs keep to the features.
MINIMAL=""
case "${TVWCS_INSTALL:-}" in
    minimal) MINIMAL=1 ;; full|"") ;;
    *) echo "install.sh: TVWCS_INSTALL must be full or minimal, not \"$TVWCS_INSTALL\"." >&2; exit 1 ;;
esac
if [ -z "$CHECK_ONLY" ] && [ -z "${TVWCS_INSTALL:-}" ] && [ -t 0 ] && [ ! -f "$CONFIG_HOME/tvwcs/config.json" ]; then
    printf "\nWhat should be installed?\n  1) Everything TVWCS can use (sound, Bluetooth, network, storage, a terminal, Flathub apps, the screen saver)\n  2) A minimal install: the Quick Menu, the applications list and basic Settings (turn the rest on later in Settings > Features)\nChoose 1 or 2 [1]: "
    read -r ANSWER || ANSWER=""
    case "$ANSWER" in 2*|[Mm]*) MINIMAL=1 ;; esac
fi
[ -z "$MINIMAL" ] || echo "A minimal install: optional features are left out."
# The features turned off in Settings > Features (or by a minimal install): their packages are not asked for.
FEATURES_OFF=" $(PYTHONPATH=$(dirname "$PKG") python3 -m tvwcs.features off 2>/dev/null | tr '\n' ' ')"

# ------------------------------------------------------------------ a window manager, when there is none (optional)
# TVWCS runs in i3 or sway. With neither installed, offer to install one with the package manager: i3 (recommended:
# TVWCS places its window best there) together with Xorg (unless an X server, such as XLibre, is already installed),
# startx, xdotool and xrandr, or sway. Afterwards the rest of the installer sets it up. Installing one never makes it
# the login screen's default session. Only offered on a terminal, and not when TVWCS_WMS names the window managers.
wm_packages() {   # wm_packages <i3|sway>: what to install for it here, or "" when this distribution is not supported
    case "$(distro):$1" in
        debian:i3) echo "i3 xserver-xorg xinit xdotool x11-xserver-utils" ;;
        unknown:*) echo "" ;;
        *:sway) echo sway ;;
    esac
}
x_server() {   # the X server already installed: XLibre, Xorg, or "" for none
    if [ -n "${TVWCS_X_SERVER+set}" ]; then echo "$TVWCS_X_SERVER"; return 0; fi   # tests: as if this one (or none) were installed
    for X in Xlibre Xorg X; do
        P=$(command -v "$X" 2>/dev/null) || continue
        if [ "$X" = Xlibre ] || "$P" -version 2>&1 | grep -qi xlibre; then echo XLibre; return 0; fi
    done
    for P in /usr/bin/Xlibre /usr/lib/xorg/Xlibre /usr/libexec/Xlibre; do [ -x "$P" ] && { echo XLibre; return 0; }; done
    for P in /usr/bin/Xorg /usr/lib/xorg/Xorg /usr/libexec/Xorg; do [ -x "$P" ] && { echo Xorg; return 0; }; done
    echo ""
}
without_x_server() {   # the packages given, less the X server's (XLibre replaces Xorg; installing Xorg over it would undo that)
    for P in "$@"; do
        case "$P" in xserver-xorg) ;; *) printf '%s ' "$P" ;; esac
    done
}
pkg_install() {   # pkg_install <packages>: install them with this distribution's package manager, as root
    case "$(distro)" in
        debian) as_root apt-get update -q && as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y "$@" ;;
        *) return 1 ;;
    esac
}
offer_wm_install() {
    if command -v i3 >/dev/null 2>&1 || command -v sway >/dev/null 2>&1; then return 0; fi
    [ -t 0 ] && [ -z "${TVWCS_WMS:-}" ] || return 0
    echo; echo "Neither i3 nor sway is installed, and TVWCS runs in one of them."
    if [ -z "$(wm_packages i3)" ]; then
        unsupported_note; echo "Install i3 (with an X server and startx) or sway yourself, then run install.sh again."; return 0
    fi
    XSERVER=$(x_server)
    if [ -n "$XSERVER" ]; then I3_CHOICE="i3, for the $XSERVER already installed (recommended)"; else I3_CHOICE="i3 with Xorg (recommended)"; fi
    printf "Install one now? 1) %s  2) sway  3) neither [1]: " "$I3_CHOICE"
    read -r ANSWER || ANSWER=3
    case "$ANSWER" in ""|1*|[Ii]*) WM=i3 ;; 2*|[Ss]*) WM=sway ;; *) echo "Nothing was installed."; return 0 ;; esac
    PKGS=$(wm_packages "$WM")
    # shellcheck disable=SC2086   # one word per package
    if [ "$WM" = i3 ] && [ -n "$XSERVER" ]; then PKGS=$(without_x_server $PKGS); PKGS=${PKGS% }; fi
    echo "Installing $WM with: $PKGS (your password may be asked for)"
    # shellcheck disable=SC2086   # one word per package
    if pkg_install $PKGS; then echo "Installed $WM."
    else echo "Could not install $WM. Install it yourself with:  $(install_hint "$PKGS")" >&2; fi
}
[ -n "$CHECK_ONLY" ] || offer_wm_install

# ------------------------------------------------------------------ the other packages TVWCS uses
# Listed with what each is for, and offered for installing (on a terminal, on a supported distribution); else the
# command to install them is printed. A sound server that is already there is never replaced.
NEEDS=""   # one line per need: "packages<TAB>what for"
need() {   # need <packages> <what for> [feature]: a feature's packages are left out of a minimal install, and while it is off
    if [ -n "${3:-}" ]; then
        [ -z "$MINIMAL" ] || return 0
        case "$FEATURES_OFF" in *" $3 "*) return 0 ;; esac
    fi
    NEEDS="$NEEDS$1	$2
"; }
icon_theme_installed() {   # Adwaita or Papirus, system-wide or the user's own (the themes TVWCS's icons are drawn from)
    for D in "$SHARE/icons" "${XDG_DATA_HOME:-$HOME/.local/share}/icons" "$HOME/.icons"; do
        for T in Adwaita Papirus Papirus-Dark; do [ -f "$D/$T/index.theme" ] && return 0; done
    done
    return 1
}
metro_font_installed() {   # a font the Metro theme names before the fallbacks: Segoe UI, Selawik or Open Sans
    for D in "$SHARE/fonts" "${XDG_DATA_HOME:-$HOME/.local/share}/fonts" "$HOME/.fonts"; do
        [ -d "$D" ] || continue
        [ -n "$(find "$D" \( -iname 'OpenSans*' -o -iname 'Open_Sans*' -o -iname 'selawik*' -o -iname 'segoeui*' \) 2>/dev/null | sed -n 1p)" ] && return 0
    done
    return 1
}
python3 -c 'import gi; gi.require_version("Gtk","4.0")' 2>/dev/null || need "$(pkg gtk)" "GTK 4 for Python: TVWCS's windows (required)"
command -v i3 >/dev/null 2>&1 || command -v sway >/dev/null 2>&1 || need "$(pkg i3)" "i3: the window manager TVWCS runs in (required)"
command -v sway >/dev/null 2>&1 || command -v xdotool >/dev/null 2>&1 || need "$(pkg xdotool)" "places TVWCS's window on the right monitor in i3"
command -v pipewire >/dev/null 2>&1 || command -v pulseaudio >/dev/null 2>&1 || need "$(pkg pipewire)" "PipeWire: sound, with its PulseAudio layer (no sound server is installed)" sound
command -v pactl >/dev/null 2>&1 || need "$(pkg pactl)" "Settings: sound" sound
if command -v i3 >/dev/null 2>&1 && ! command -v xprintidle >/dev/null 2>&1 && ! python3 -c 'import ctypes.util, sys; sys.exit(not ctypes.util.find_library("Xss"))' 2>/dev/null; then   # ldconfig is in /sbin, off a user's PATH
    need "$(pkg xss)" "Settings: Power and sleep (how long the computer has been idle, in i3)"; fi
if command -v sway >/dev/null 2>&1 && ! command -v swayidle >/dev/null 2>&1; then need swayidle "Settings: Power and sleep (in sway)"; fi
if command -v i3 >/dev/null 2>&1 && ! command -v unclutter >/dev/null 2>&1; then need "$(pkg unclutter)" "hides the mouse pointer after 3 seconds without moving (i3)" cursor; fi
if command -v i3 >/dev/null 2>&1 && ! command -v xsecurelock >/dev/null 2>&1; then need xsecurelock "the screen saver while the computer is locked (i3)" lock_saver; fi
if command -v i3 >/dev/null 2>&1 && ! command -v xrandr >/dev/null 2>&1; then need "$(pkg xrandr)" "Settings: displays (sway has its own)"; fi
if command -v i3 >/dev/null 2>&1 && ! command -v xsetroot >/dev/null 2>&1; then need "$(pkg xrandr)" "the background colour (xsetroot, in i3)"; fi
command -v udisksctl >/dev/null 2>&1 || need udisks2 "Settings: storage (opening and closing drives)" storage
# Helper programs that are not on PATH (TVWCS_LIBEXEC lets the tests point elsewhere).
libexec_has() { for d in ${TVWCS_LIBEXEC:-/usr/libexec /usr/lib/gvfs /usr/lib}; do [ -e "$d/$1" ] && return 0; done; return 1; }
command -v gio >/dev/null 2>&1 && command -v gsettings >/dev/null 2>&1 || need libglib2.0-bin "Settings: network shares (gio), and light or dark mode for GTK apps (gsettings)"
libexec_has gvfsd-smb || need gvfs-backends "Settings: storage (network shares)" storage
libexec_has xdg-desktop-portal-gtk || need "xdg-desktop-portal xdg-desktop-portal-gtk" "light or dark mode for Flatpak apps and browsers"
command -v bluetoothctl >/dev/null 2>&1 || need "$(pkg bluetoothctl)" "Settings: Bluetooth" bluetooth
command -v nmcli >/dev/null 2>&1 || need "$(pkg nmcli)" "Settings: network (Ethernet and Wi-Fi)" network
python3 -c 'import gi; gi.require_version("Vte","3.91")' 2>/dev/null || need "$(pkg vte)" "Settings: the terminal page" terminal
python3 -c 'import gi; gi.require_foreign("cairo")' 2>/dev/null || need "$(pkg cairo)" "the screen saver (drawing with cairo)" screensaver
icon_theme_installed || need "$(pkg icons)" "icons for apps and buttons (Papirus, papirus-icon-theme, has more app icons)"
metro_font_installed || need "$(pkg font)" "Open Sans: the font of TVWCS's Metro look"
start_pipewire() {   # PipeWire just installed: start it in a session that runs now (systemd starts it by itself from the next log-in)
    command -v pipewire >/dev/null 2>&1 && command -v systemctl >/dev/null 2>&1 || return 0
    if systemctl --user enable --now pipewire.socket pipewire-pulse.socket wireplumber.service >/dev/null 2>&1; then
        echo "Started PipeWire for $(id -un)."
    fi
}
if [ -n "$CHECK_ONLY" ]; then
    [ "$(distro)" = unknown ] || printf '%s' "$NEEDS" | while IFS='	' read -r P W; do printf 'need\t%s\t%s\n' "$P" "$W"; done
    exit 0
fi
if [ -n "$NEEDS" ]; then
    echo; echo "Missing packages:"
    printf '%s' "$NEEDS" | while IFS='	' read -r P W; do printf '  %-36s %s\n' "$P" "$W"; done
    ALL=$(printf '%s' "$NEEDS" | cut -f1 | tr '\n' ' '); ALL=${ALL% }
    if [ "$(distro)" = unknown ]; then
        unsupported_note; echo "To install them:  $(install_hint "$ALL")"
    elif ask_yes "Install them now?"; then
        # shellcheck disable=SC2086   # one word per package
        if pkg_install $ALL; then echo "Installed them."; start_pipewire
        else echo "Not everything could be installed. Install what is missing with:  $(install_hint "$ALL")" >&2; fi
    else
        echo "To install them:  $(install_hint "$ALL")"
    fi
fi
# A minimal install: the features whose software is missing start turned off (Settings > Features turns them on).
if [ -n "$MINIMAL" ] && [ -z "$CHECK_ONLY" ]; then
    PYTHONPATH="$DEST" python3 -m tvwcs.features minimal || echo "Could not turn the optional features off; do it in Settings > Features." >&2
fi

# ------------------------------------------------------------------ window manager configs
# The include line, written with ~ when the install is in your home folder (i3 and sway both expand it).
case "$DEST" in
    "$HOME"/*) INCLUDE_PATH="~/${DEST#"$HOME"/}/tvwcs.conf" ;;
    *) INCLUDE_PATH="$DEST/tvwcs.conf" ;;
esac
case "$INCLUDE_PATH" in *" "*) INCLUDE_LINE="include \"$INCLUDE_PATH\"" ;; *) INCLUDE_LINE="include $INCLUDE_PATH" ;; esac

wm_config() {   # the config file i3 / sway reads (the first that exists), or "" when there is none
    if [ "$1" = i3 ]; then set -- "$CONFIG_HOME/i3/config" "$HOME/.i3/config"
    else set -- "$CONFIG_HOME/sway/config" "$HOME/.sway/config"; fi
    for C in "$@"; do [ -f "$C" ] && { echo "$C"; return; }; done
    echo ""
}

# include_state <config> -> "current" (includes this install), "other" (includes a tvwcs.conf elsewhere) or "none"
include_state() {
    WANT="$DEST/tvwcs.conf" awk '
        /^[ \t]*include[ \t]/ && /tvwcs\.conf/ {
            p = $0; sub(/^[ \t]*include[ \t]+/, "", p); sub(/[ \t]+$/, "", p); gsub(/^["\047]|["\047]$/, "", p)
            if (substr(p, 1, 2) == "~/") p = ENVIRON["HOME"] substr(p, 2)
            gsub(/\$HOME/, ENVIRON["HOME"], p)
            if (p == ENVIRON["WANT"]) found = "current"; else if (found == "") found = "other"
        }
        END { print (found == "" ? "none" : found) }' "$1"
}

backup() { cp "$1" "$1.tvwcs-backup"; }
replace_include() {   # replace_include <config>: point its (first) TVWCS include line at this install
    TMP=$(mktemp)
    LINE="$INCLUDE_LINE" awk '/^[ \t]*include[ \t]/ && /tvwcs\.conf/ { if (!done) print ENVIRON["LINE"]; done = 1; next } { print }' "$1" > "$TMP"
    cat "$TMP" > "$1"; rm -f "$TMP"
}

CHANGED_WMS=""
# include_in <wm> <config> [optional]: add or update the include line (after asking). "optional" is the alongside
# setup's question about your usual config: TVWCS's own session does not need it there, so Enter means no.
include_in() {
    WM=$1; CFG=$2; OPTIONAL=${3:-}
    case $(include_state "$CFG") in
        current)
            if [ -n "$OPTIONAL" ]; then
                echo "Your usual $WM config ($CFG) also includes TVWCS, so TVWCS starts in that session too. The TVWCS session does not need it; remove the include line to keep TVWCS out of your usual $WM."
            else echo "Your $WM config ($CFG) already includes TVWCS."; fi ;;
        other)
            if ask "Your $WM config ($CFG) includes TVWCS from its old location. Update it to $INCLUDE_PATH?" migrate; then
                backup "$CFG"; replace_include "$CFG"
                echo "Updated the include line in $CFG (backup: $CFG.tvwcs-backup)."; CHANGED_WMS="$CHANGED_WMS $WM"
            else
                echo "Left $CFG unchanged. Change its TVWCS include line to:"; echo "    $INCLUDE_LINE"
            fi ;;
        none)
            if [ -n "$OPTIONAL" ]; then
                ask_no "Also add TVWCS to your usual $WM config ($CFG)? Its hotkeys, autostart and window rules then apply in that session too (the TVWCS session does not need this)." || return 0
            elif ! ask "Add TVWCS to your $WM config ($CFG)? This appends one include line."; then
                echo "Left $CFG unchanged. To use TVWCS, add this line to it and reload $WM:"; echo "    $INCLUDE_LINE"; return 0
            fi
            backup "$CFG"
            { echo; echo "# TVWCS: its window rules, hotkeys and autostart. Added by TVWCS's install.sh."; echo "$INCLUDE_LINE"; } >> "$CFG"
            echo "Added the include line to $CFG (backup: $CFG.tvwcs-backup)."; CHANGED_WMS="$CHANGED_WMS $WM" ;;
    esac
}

# ---- creating a config when there is none
current_layout() {   # "layout variant" of the keyboard in use now, best guess; "us" when nothing says otherwise
    L=""; V=""
    if command -v setxkbmap >/dev/null 2>&1 && [ -n "${DISPLAY:-}" ]; then
        Q=$(setxkbmap -query 2>/dev/null || true)
        L=$(echo "$Q" | awk '/^layout:/ {print $2}'); V=$(echo "$Q" | awk '/^variant:/ {print $2}')
    fi
    if [ -z "$L" ] && command -v localectl >/dev/null 2>&1; then
        Q=$(localectl status 2>/dev/null || true)
        L=$(echo "$Q" | awk -F': *' '/X11 Layout/ {print $2}'); V=$(echo "$Q" | awk -F': *' '/X11 Variant/ {print $2}')
    fi
    if [ -z "$L" ] && [ -f "$ETC/default/keyboard" ]; then   # Debian and its family
        L=$(sed -n 's/^XKBLAYOUT="\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' "$ETC/default/keyboard"); V=$(sed -n 's/^XKBVARIANT="\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' "$ETC/default/keyboard")
    fi
    echo "${L:-us} $V"
}

known_layout() {   # every comma-separated layout must be in XKB's list (when the list is installed)
    LST=/usr/share/X11/xkb/rules/evdev.lst
    [ -f "$LST" ] || return 0
    for X in $(echo "$1" | tr ',' ' '); do
        awk -v want="$X" '/^! layout/ {on=1; next} /^!/ {on=0} on && $1 == want {found=1} END {exit !found}' "$LST" || return 1
    done
}

MOD=""; LAYOUT=""; VARIANT=""; LAYOUT_IS_CURRENT=""
choose_keys() {   # asked once, shared by i3 and sway. Without a terminal: Super, and the current layout.
    [ -n "$MOD" ] && return
    if [ ! -t 0 ]; then MOD=Mod4; set -- $(current_layout); LAYOUT=$1; VARIANT=${2:-}; LAYOUT_IS_CURRENT=1; return; fi
    printf "Which key should be your window manager's modifier (\$mod)?\n  1) Super (the Windows key)\n  2) Alt\nChoose 1 or 2 [1]: "
    read -r ANSWER || ANSWER=1
    case "$ANSWER" in 2*) MOD=Mod1 ;; *) MOD=Mod4 ;; esac
    set -- $(current_layout); CUR_L=$1; CUR_V=${2:-}
    if ask "Use your current keyboard layout ($CUR_L${CUR_V:+, variant $CUR_V})?"; then
        LAYOUT=$CUR_L; VARIANT=$CUR_V; LAYOUT_IS_CURRENT=1
    else
        while :; do
            printf "Keyboard layout code (for example us, gb, de, fr, es; add a variant after a space, such as \"us dvorak\"): "
            read -r ANSWER || ANSWER=""
            set -- $ANSWER
            if [ $# -eq 0 ]; then LAYOUT=$CUR_L; VARIANT=$CUR_V; LAYOUT_IS_CURRENT=1; echo "Keeping $CUR_L."; break; fi
            if known_layout "$1"; then LAYOUT=$1; VARIANT=${2:-}; break; fi
            echo "\"$1\" is not a keyboard layout XKB knows. See /usr/share/X11/xkb/rules/evdev.lst for the list."
        done
    fi
}

# keycode_config <template> <mod>: the i3 keycode template with its bindings kept as keycodes, which are physical
# keys and so stay in the same place on any layout (what i3-config-wizard translates into key names).
keycode_config() {
    M="$2" awk '/^# WARNING/ {next} /^set \$mod / {print "set $mod " ENVIRON["M"]; next} {print}' "$1"
}

create_i3_config() {   # create_i3_config [file]: your i3 config (the default), or TVWCS's own session config
    CFG=${1:-$CONFIG_HOME/i3/config}; mkdir -p "$(dirname "$CFG")"
    WIZ_MOD=win; [ "$MOD" = Mod1 ] && WIZ_MOD=alt
    # The standard way: i3-config-wizard writes the default config with key names from the current keyboard
    # layout. It reads the live keymap, so it is only used for the current layout and with a display. It can only
    # write the usual config, so TVWCS's session config always comes from the keycode template.
    if [ -z "${1:-}" ] && [ -n "$LAYOUT_IS_CURRENT" ] && [ -n "${DISPLAY:-}" ] && command -v i3-config-wizard >/dev/null 2>&1; then
        XDG_CONFIG_HOME="$CONFIG_HOME" i3-config-wizard -m "$WIZ_MOD" >/dev/null 2>&1 || true   # fails afterwards when i3 is not running
    fi
    if [ ! -s "$CFG" ]; then
        if [ -f "$ETC/i3/config.keycodes" ]; then keycode_config "$ETC/i3/config.keycodes" "$MOD" > "$CFG"
        elif [ -f "$ETC/i3/config" ]; then M="$MOD" awk '{gsub(/Mod1/, ENVIRON["M"]); print}' "$ETC/i3/config" > "$CFG"
        else rm -f "$CFG"; echo "No i3 template found in $ETC/i3 (is i3 installed?); no config created." >&2; return 1; fi
    fi
    if [ -z "$LAYOUT_IS_CURRENT" ]; then
        { echo; echo "# Keyboard layout, chosen when TVWCS's install.sh created this file"
          echo "exec_always --no-startup-id setxkbmap -layout $LAYOUT${VARIANT:+ -variant $VARIANT}"; } >> "$CFG"
    fi
    echo "Created $CFG from the standard i3 template (\$mod = $( [ "$MOD" = Mod4 ] && echo Super || echo Alt ))."
}

create_sway_config() {   # create_sway_config [file]: your sway config (the default), or TVWCS's own session config
    CFG=${1:-$CONFIG_HOME/sway/config}; mkdir -p "$(dirname "$CFG")"
    [ -f "$ETC/sway/config" ] || { echo "No sway template found at $ETC/sway/config (is sway installed?); no config created." >&2; return 1; }
    M="$MOD" awk '/^set \$mod / {print "set $mod " ENVIRON["M"]; next} {print}' "$ETC/sway/config" > "$CFG"
    # sway does not take the layout from X: it uses "us" unless told otherwise, so any other layout is written down.
    if [ "$LAYOUT" != us ] || [ -n "$VARIANT" ]; then
        { echo; echo "# Keyboard layout, chosen when TVWCS's install.sh created this file"
          echo "input type:keyboard {"; echo "    xkb_layout $LAYOUT"; [ -n "$VARIANT" ] && echo "    xkb_variant $VARIANT"; echo "}"; } >> "$CFG"
    fi
    echo "Created $CFG from the standard sway template (\$mod = $( [ "$MOD" = Mod4 ] && echo Super || echo Alt ))."
}

setup_wm() {   # setup_wm <i3|sway>: the dedicated setup's usual config
    WM=$1; CFG=$(wm_config "$WM")
    if [ -n "$CFG" ]; then include_in "$WM" "$CFG"; return; fi
    if [ -t 0 ] && ask "There is no $WM config yet. Create one from the standard template?"; then
        choose_keys
        if create_${WM}_config; then include_in "$WM" "$(wm_config "$WM")"; return; fi
    fi
    echo "No $WM config found. Once you have one, add this line to it and reload $WM:"; echo "    $INCLUDE_LINE"
}

# ---- the alongside setup: TVWCS's own session
# TVWCS's session runs i3 or sway with a config of its own, ~/.config/tvwcs/<wm>-session.conf: the standard template
# plus the include line, so TVWCS's hotkeys, autostart and window rules stay out of your usual i3 / sway. It is
# TVWCS's file, so it is created and kept pointing at this install without asking (edit it as you like otherwise).
# The session is started by tvwcs-session, a small wrapper that exports TVWCS_SESSION (and the config's path in
# TVWCS_SESSION_CONFIG), so TVWCS knows which config is its own (Settings' xss-lock fix changes that one).
session_config() { echo "$CONFIG_HOME/tvwcs/$1-session.conf"; }
SESSION_WMS=""
setup_session_config() {   # setup_session_config <i3|sway>
    WM=$1; SCFG=$(session_config "$WM")
    if [ ! -f "$SCFG" ]; then
        command -v "$WM" >/dev/null 2>&1 || [ -n "${TVWCS_WMS:-}" ] || return 0
        choose_keys
        create_${WM}_config "$SCFG" || { echo "Install $WM, then run install.sh again to create TVWCS's $WM session."; return 0; }
        TMP=$(mktemp)
        { echo "# TVWCS's own $WM session (\"TVWCS ($WM)\" at the login screen), not your usual $WM config. Written by TVWCS's"
          echo "# install.sh from the standard template; edit it as you like. Your usual $WM config is not used in this session."
          cat "$SCFG"; echo; echo "# TVWCS: its window rules, hotkeys and autostart."; echo "$INCLUDE_LINE"; } > "$TMP"
        cat "$TMP" > "$SCFG"; rm -f "$TMP"
    else
        case $(include_state "$SCFG") in
            current) ;;
            other) replace_include "$SCFG"; echo "Pointed $SCFG at this install." ;;
            none) { echo; echo "# TVWCS: its window rules, hotkeys and autostart."; echo "$INCLUDE_LINE"; } >> "$SCFG"; echo "Added TVWCS back to $SCFG." ;;
        esac
        echo "TVWCS's $WM session uses $SCFG."
    fi
    SESSION_WMS="$SESSION_WMS $WM"
}
session_wrapper() {   # the tvwcs-session script: nothing in it is about one user, so one copy serves everyone
    cat <<'WRAPPER'
#!/bin/sh
# TVWCS's own session: i3 or sway with TVWCS's session config (~/.config/tvwcs/<wm>-session.conf), not your usual one.
# Written by TVWCS's install.sh. Run by the login screen's "TVWCS" entries, or from a text console:
#     startx <path to this file> i3        or        <path to this file> sway
WM=${1:-i3}
CFG=${XDG_CONFIG_HOME:-$HOME/.config}/tvwcs/$WM-session.conf
case "$WM" in i3|sway) ;; *) echo "tvwcs-session: use i3 or sway, not $WM" >&2; exit 2 ;; esac
if [ ! -f "$CFG" ]; then
    echo "tvwcs-session: $CFG is missing. Run TVWCS's install.sh and choose \"Next to my other desktops\"." >&2; exit 1
fi
# TVWCS reads these to know that this session's config is its own one.
TVWCS_SESSION=$WM; TVWCS_SESSION_CONFIG=$CFG; export TVWCS_SESSION TVWCS_SESSION_CONFIG
exec "$WM" -c "$CFG"
WRAPPER
}
session_entry() {   # session_entry <i3|sway>: the login screen's entry for it
    printf '%s\n' "[Desktop Entry]" "Type=Application" "Name=TVWCS ($1)" \
        "Comment=TVWCS in a $1 session of its own, made for a TV and a remote (added by TVWCS's install.sh)" \
        "Exec=$BINDIR/tvwcs-session $1" "TryExec=$1" "DesktopNames=$1"
}
entry_path() { if [ "$1" = i3 ]; then echo "$SHARE/xsessions/tvwcs-i3.desktop"; else echo "$SHARE/wayland-sessions/tvwcs-sway.desktop"; fi; }
sway_console_hint() {   # a login screen made for X only (such as Linux Mint's) does not list a sway session
    case " $SESSION_WMS " in *" sway "*)
        echo "If the login screen does not list \"TVWCS (sway)\", start it from a text console with:  '$BINDIR/tvwcs-session' sway" ;; esac
}
setup_login_entries() {
    # A copy of the wrapper in TVWCS's own folder, for startx and for computers without a login screen.
    session_wrapper > "$DEST/bin/tvwcs-session"; chmod +x "$DEST/bin/tvwcs-session"
    [ -n "$SESSION_WMS" ] || return 0
    if [ -z "$DM" ]; then
        echo; echo "There is no login screen here. To start TVWCS's session from a text console, log in and run:"
        for WM in $SESSION_WMS; do
            if [ "$WM" = i3 ]; then echo "    startx '$DEST/bin/tvwcs-session' i3"; else echo "    '$DEST/bin/tvwcs-session' sway"; fi
        done
        return 0
    fi
    # The entries and the wrapper they run go into the system's folders, which needs root once. Unchanged ones are
    # not written again.
    STAGE=$(mktemp -d); session_wrapper > "$STAGE/tvwcs-session"; set -- "$BINDIR/tvwcs-session" "$STAGE/tvwcs-session"; ALL_SAME=1
    same_file "$STAGE/tvwcs-session" "$BINDIR/tvwcs-session" 2>/dev/null || ALL_SAME=""
    for WM in $SESSION_WMS; do
        session_entry "$WM" > "$STAGE/$WM.desktop"; set -- "$@" "$(entry_path "$WM")" "$STAGE/$WM.desktop"
        same_file "$STAGE/$WM.desktop" "$(entry_path "$WM")" 2>/dev/null || ALL_SAME=""
    done
    echo
    if [ -n "$ALL_SAME" ]; then echo "The login screen already lists TVWCS's session."; rm -rf "$STAGE"; LOGIN_ENTRY=1; sway_console_hint; return 0; fi
    if ! ask "Add a \"TVWCS\" session to the login screen? This adds$(for WM in $SESSION_WMS; do printf ' %s' "$(entry_path "$WM")"; done) and $BINDIR/tvwcs-session, and asks for your password once."; then
        echo "No login screen entry was added. Run install.sh again to add it, or start the session from a text console with:"
        echo "    startx '$DEST/bin/tvwcs-session' i3"; rm -rf "$STAGE"; return 0
    fi
    if as_root sh -c 'set -e; mkdir -p "$(dirname "$1")"; cp "$2" "$1"; chmod 0755 "$1"; shift 2
                      while [ $# -gt 0 ]; do mkdir -p "$(dirname "$1")"; cp "$2" "$1"; chmod 0644 "$1"; shift 2; done' sh "$@"; then
        echo "Added TVWCS's session to the login screen (delete$(for WM in $SESSION_WMS; do printf ' %s' "$(entry_path "$WM")"; done) and $BINDIR/tvwcs-session to undo it)."
        LOGIN_ENTRY=1; sway_console_hint
    else echo "Could not add the login screen entry; nothing was changed." >&2; fi
    rm -rf "$STAGE"
}

# sway started by hand (`sway` on a text console) reads ~/.config/sway/config, and without one it reads your i3 config,
# which sway cannot run (lines such as "tiling_drag modifier titlebar" are i3's only). TVWCS's own sway session never
# does that, so it is started with tvwcs-session; your plain sway gets a config of its own here if you like.
sway_fallback_check() {
    command -v sway >/dev/null 2>&1 || return 0
    [ -z "$(wm_config sway)" ] && [ -n "$(wm_config i3)" ] || return 0
    echo
    echo "You have an i3 config but no sway config. sway started on its own (typing \"sway\" on a text console) then reads"
    echo "your i3 config, and stops at lines only i3 understands. TVWCS's sway session is not affected: start it with"
    echo "    '$DEST/bin/tvwcs-session' sway"
    if ask "Create a sway config of its own for plain sway too ($CONFIG_HOME/sway/config, from the standard template)?"; then
        choose_keys; create_sway_config || true
    fi
}

echo
WMS=${TVWCS_WMS:-}
if [ -z "$WMS" ]; then
    command -v i3 >/dev/null 2>&1 && WMS="i3"
    command -v sway >/dev/null 2>&1 && WMS="$WMS sway"
    [ -n "$WMS" ] || WMS="i3"   # nothing installed yet: still say what to add once it is
fi
LOGIN_ENTRY=""
if [ "$SETUP" = alongside ]; then
    for WM in $WMS; do setup_session_config "$WM"; done
    setup_login_entries
    case " $SESSION_WMS " in *" sway "*) sway_fallback_check ;; esac
    for WM in $WMS; do   # your usual config: only on request
        CFG=$(wm_config "$WM"); [ -n "$CFG" ] && include_in "$WM" "$CFG" optional
    done
else
    for WM in $WMS; do setup_wm "$WM"; done
fi

# ---- reaching the running i3 / sway, also from an SSH login (which has no DISPLAY, SWAYSOCK or I3SOCK)
user_runtime() {   # this user's runtime folder: XDG_RUNTIME_DIR, else /run/user/<uid> when it exists, else ""
    if [ -n "${XDG_RUNTIME_DIR:-}" ]; then echo "$XDG_RUNTIME_DIR"
    elif [ -d "/run/user/$(id -u)" ]; then echo "/run/user/$(id -u)"; fi
}
wm_tool() { if [ "$1" = i3 ]; then echo i3-msg; else echo swaymsg; fi; }
wm_socket() {   # wm_socket <i3|sway>: the IPC socket of this user's running i3 / sway that answers, or ""
    WS_TOOL=$(wm_tool "$1"); command -v "$WS_TOOL" >/dev/null 2>&1 || return 0
    WS_R=$(user_runtime)
    if [ "$1" = sway ]; then set -- "${SWAYSOCK:-}" "${WS_R:-/nonexistent}"/sway-ipc."$(id -u)".*.sock
    else
        WS_P=""; [ -n "${DISPLAY:-}" ] && [ -z "${SWAYSOCK:-}" ] && WS_P=$(i3 --get-socketpath 2>/dev/null || true)
        [ -n "${SWAYSOCK:-}" ] || WS_P="${I3SOCK:-} $WS_P"   # under sway, I3SOCK is sway's own socket
        set -- $WS_P "${WS_R:-/nonexistent}"/i3/ipc-socket.* /tmp/i3-"$(id -un)".*/ipc-socket.*
    fi
    for WS in "$@"; do   # sockets left behind by an earlier session do not answer
        [ -n "$WS" ] && [ -S "$WS" ] && "$WS_TOOL" -s "$WS" -t get_version >/dev/null 2>&1 && { echo "$WS"; return 0; }
    done
    return 0
}
wm_msg() {   # wm_msg <i3|sway> <arguments>: send a command to the running one; fails when none is running
    WS=$(wm_socket "$1"); [ -n "$WS" ] || return 1
    WS_TOOL=$(wm_tool "$1"); shift; "$WS_TOOL" -s "$WS" "$@"
}

# A window manager that is running reloads its changed config, so TVWCS's hotkeys work straight away. (In the
# alongside setup this is only your usual config, and only when you chose to add TVWCS to it.)
for WM in $CHANGED_WMS; do
    if wm_msg "$WM" -q reload >/dev/null 2>&1; then echo "Reloaded $WM."; fi
done

# ------------------------------------------------------------------ power actions without a password (optional)
# Sleep, Reboot and Shut down need root when polkit cannot allow them (another user is logged in, say). TVWCS then
# asks for your sudo password on screen; this optional rule lets your user run exactly those commands, with exactly
# those arguments, without one. Only offered on a terminal, and only on a clear yes.
program_paths() {   # every installed path of a program (sudo and doas rules match the path TVWCS runs it by)
    for DIR in /usr/bin /bin /usr/sbin /sbin /usr/local/bin /usr/local/sbin; do [ -x "$DIR/$1" ] && echo "$DIR/$1"; done; return 0
}
power_commands() {   # "path arguments" for each power command here, one per line
    for P in $(program_paths systemctl); do for V in suspend reboot poweroff; do echo "$P $V"; done; done
}
sudo_rule() {   # sudo_rule <user>: the sudoers drop-in. Its alias is named after the user, so every user can have one.
    ALIAS=TVWCS_POWER_$(echo "$1" | tr 'a-z.-' 'A-Z__')
    echo "# Written by TVWCS's install.sh: lets $1 sleep, reboot and shut down from TVWCS without a password."
    echo "# Delete this file to undo it."
    LIST=$(power_commands | awk '{ if (NF == 1) $0 = $0 " \"\""; printf "%s%s", (NR > 1 ? ", " : ""), $0 }')
    echo "Cmnd_Alias $ALIAS = $LIST"
    echo "$1 ALL=(root) NOPASSWD: $ALIAS"
}
sudo_nopasswd_for() {   # sudo already lets this user run "$1" without a password
    # sudo -l <command> cannot tell: once any NOPASSWD rule exists it also reports commands that need a password.
    # So read the full listing, in sudo's order: the last rule that matches the command decides, as it does in sudo.
    sudo -n -l 2>/dev/null | awk -v want="$1" '
        /^[ \t]*\(/ { line = $0; sub(/^[ \t]*\([^)]*\)[ \t]*/, "", line); nopw = 0
            while (match(line, /^[A-Z_]+:[ \t]*/)) { if (substr(line, 1, RLENGTH) ~ /^NOPASSWD:/) nopw = 1; line = substr(line, RLENGTH + 1) }
            n = split(line, c, /, */)
            for (i = 1; i <= n; i++) if (c[i] == "ALL" || c[i] == want || index(c[i], want " ") == 1) last = nopw }
        END { exit !last }'
}
doas_rule() {   # doas_rule <user>: lines for doas.conf ("args" alone = no arguments)
    echo "# TVWCS: lets $1 sleep, reboot and shut down without a password (added by install.sh)"
    power_commands | while read -r P V; do echo "permit nopass $1 as root cmd $P args${V:+ $V}"; done
}
setup_power_rule() {
    [ -t 0 ] || return 0
    ME=$(id -un); [ "$(id -u)" = 0 ] && return 0   # root needs no rule
    case "$ME" in [a-z_]*) ;; *) return 0 ;; esac
    case "$ME" in *[!a-zA-Z0-9_.-]*) return 0 ;; esac
    FIRST=$(power_commands | sed -n 1p); [ -n "$FIRST" ] || return 0   # (head would close the pipe early)
    if command -v sudo >/dev/null 2>&1; then
        # sudo reads drop-ins in name order and the last matching rule wins: "zz-" puts this after a user's general
        # "may do anything, with a password" rule. sudo skips drop-ins whose names contain a dot.
        RULE="$ETC/sudoers.d/zz-tvwcs-power-$(echo "$ME" | tr '.' '_')"
        if sudo_nopasswd_for "$FIRST"; then echo "Sleep, Reboot and Shut down already work without a password (sudo)."; return 0; fi
        echo
        ask_no "Let TVWCS sleep, reboot and shut down without asking for your password? This adds a sudo rule ($RULE) that allows only those commands; sudo asks for your password once now." || return 0
        TMP=$(mktemp); sudo_rule "$ME" > "$TMP"
        # sudo asks for the password on the terminal itself, so only its messages are captured here
        if ! OUT=$(sudo visudo -cf "$TMP" 2>&1); then echo "Could not add the rule, nothing was changed: $(echo "$OUT" | tail -n 1)" >&2; rm -f "$TMP"; return 0; fi
        if sudo sh -c 'mkdir -p "$(dirname "$1")" && cat > "$1" && chmod 0440 "$1"' sh "$RULE" < "$TMP"; then
            echo "Added $RULE (delete it to undo this)."
            sudo -k; sudo_nopasswd_for "$FIRST" || echo "Note: sudo does not seem to read $ETC/sudoers.d (check for an includedir line in $ETC/sudoers)."
        fi
        rm -f "$TMP"
    elif command -v doas >/dev/null 2>&1; then
        echo
        ask_no "Let TVWCS sleep, reboot and shut down without asking for your password? This adds rules to $ETC/doas.conf that allow only those commands; doas asks for your password once now." || return 0
        TMP=$(mktemp); doas_rule "$ME" > "$TMP"
        # check the whole file as it would be, then append
        if doas sh -c 'cat "$1" "$2" > "$2.all" && doas -C "$2.all" && cat "$2" >> "$1"; R=$?; rm -f "$2.all"; exit $R' sh "$ETC/doas.conf" "$TMP"; then
            echo "Added the rules to $ETC/doas.conf."
        else echo "The rules did not pass doas's check; nothing was changed." >&2; fi
        rm -f "$TMP"
    fi
}
setup_power_rule

# ------------------------------------------------------------------ log in and start i3 / sway at boot (dedicated only)
# On a computer with no login screen (display manager) yet, offer to log this user in on the first console at boot
# and start i3 (through startx) or sway there, so it boots straight into TVWCS like a TV. Only offered on a terminal,
# and only on a clear yes. The console login is set up through systemd (getty@tty1); the window manager is started
# from the login shell's profile, only on tty1 and only when no session is running there. The alongside setup never
# offers this, and never changes the login screen's default session or the shell's profile.
GETTY_OVERRIDE=$ETC/systemd/system/getty@tty1.service.d/autologin.conf
console_login_set() {   # the first console already logs someone in by itself
    [ "$(init_system)" = systemd ] && [ -f "$GETTY_OVERRIDE" ] && grep -q -- '--autologin' "$GETTY_OVERRIDE"
}
set_console_login() {   # set_console_login <user>
    [ "$(init_system)" = systemd ] || return 1
    AGETTY=$(command -v agetty 2>/dev/null || echo /sbin/agetty)
    TMP=$(mktemp)
    printf '%s\n' "# Written by TVWCS's install.sh: logs $1 in on the first console at boot. Delete this file to undo it." \
        "[Service]" "ExecStart=" "ExecStart=-$AGETTY -o '-p -f -- \\\\u' --noclear --autologin $1 %I \$TERM" > "$TMP"
    as_root sh -c 'mkdir -p "$(dirname "$1")" && cat > "$1" && chmod 0644 "$1"' sh "$GETTY_OVERRIDE" < "$TMP"; R=$?; rm -f "$TMP"
    [ $R = 0 ] || return 1
    echo "Added $GETTY_OVERRIDE (delete it to undo the automatic login)."
}
# The start lines for the login shell, between markers so that running install.sh again replaces them.
START_BEGIN="# >>> TVWCS: start the window manager after the automatic login (added by install.sh; delete to undo) >>>"
START_END="# <<< TVWCS <<<"
start_block() {   # start_block <i3|sway> <sh|fish>
    if [ "$1" = i3 ]; then RUN="startx"; NEED=startx; else RUN="sway"; NEED=sway; fi
    echo "$START_BEGIN"
    if [ "$2" = fish ]; then
        echo "if status is-login; and test -z \"\$DISPLAY\$WAYLAND_DISPLAY\"; and test (tty) = /dev/tty1; and command -q $NEED"
        echo "    exec $RUN"; echo "end"
    else
        echo "if [ -z \"\${DISPLAY:-}\${WAYLAND_DISPLAY:-}\" ] && [ \"\$(tty)\" = /dev/tty1 ] && command -v $NEED >/dev/null 2>&1; then"
        echo "    exec $RUN"; echo "fi"
    fi
    echo "$START_END"
}
profile_file() {   # "kind file": the file this user's login shell reads at log-in, and its kind (sh or fish)
    LOGIN_SHELL=$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f7); LOGIN_SHELL=${LOGIN_SHELL:-${SHELL:-/bin/sh}}
    case ${LOGIN_SHELL##*/} in
        fish) echo "fish $CONFIG_HOME/fish/conf.d/tvwcs-autostart.fish" ;;
        zsh) echo "sh ${ZDOTDIR:-$HOME}/.zprofile" ;;
        bash) for F in "$HOME/.bash_profile" "$HOME/.bash_login"; do [ -f "$F" ] && { echo "sh $F"; return; }; done
              echo "sh $HOME/.profile" ;;
        *) echo "sh $HOME/.profile" ;;
    esac
}
write_start() {   # write_start <i3|sway>: add (or replace) the start lines in the login shell's profile
    WM=$1; PF=$(profile_file); KIND=${PF%% *}; FILE=${PF#* }
    mkdir -p "$(dirname "$FILE")"; TMP=$(mktemp)
    if [ -f "$FILE" ]; then
        backup "$FILE"
        B="$START_BEGIN" E="$START_END" awk '$0 == ENVIRON["B"] { skip = 1 } !skip { print } $0 == ENVIRON["E"] { skip = 0 }' "$FILE" > "$TMP"
    fi
    { [ -s "$TMP" ] && echo; start_block "$WM" "$KIND"; } >> "$TMP"
    cat "$TMP" > "$FILE"; rm -f "$TMP"
    echo "Added the lines that start $WM on the first console to $FILE$( [ -f "$FILE.tvwcs-backup" ] && echo " (backup: $FILE.tvwcs-backup)")."
    if [ "$WM" = i3 ]; then   # startx runs ~/.xinitrc
        if [ ! -f "$HOME/.xinitrc" ]; then
            # Debian's /etc/X11/Xsession.d would pass DISPLAY to the user's systemd and D-Bus services; a .xinitrc of its own skips it,
            # so the desktop portal (which Flatpak apps wait for at start) and notifications cannot reach the screen. tvwcs.conf does it too.
            printf '#!/bin/sh\n# Written by TVWCS'"'"'s install.sh: startx starts i3.\nexport XDG_CURRENT_DESKTOP="${XDG_CURRENT_DESKTOP:-i3}"\n''command -v dbus-update-activation-environment >/dev/null 2>&1 && dbus-update-activation-environment --systemd DISPLAY XAUTHORITY XDG_CURRENT_DESKTOP\nexec i3\n' > "$HOME/.xinitrc"; echo "Created $HOME/.xinitrc, which starts i3."
        elif ! grep -q 'i3' "$HOME/.xinitrc"; then
            echo "Note: your ~/.xinitrc does not start i3; startx runs it as it is. Make its last line: exec i3"
        fi
    fi
}
setup_autologin() {
    [ -t 0 ] || return 0
    ME=$(id -un); [ "$(id -u)" = 0 ] && return 0   # never log root in by itself
    case "$ME" in [a-z_]*) ;; *) return 0 ;; esac
    case "$ME" in *[!a-zA-Z0-9_.-]*) return 0 ;; esac
    [ -z "$(login_manager)" ] || return 0
    if [ "$(init_system)" != systemd ]; then
        echo; echo "Logging in and starting TVWCS at boot needs systemd, so it was not offered (TODO.md has what other systems need)."; return 0
    fi
    CHOICES=""
    for WM in $WMS; do
        command -v "$WM" >/dev/null 2>&1 || continue
        if [ "$WM" = i3 ] && ! command -v startx >/dev/null 2>&1; then
            echo; echo "To start i3 automatically at boot, TVWCS needs startx:  $(install_hint "$(pkg xinit)")  and then run install.sh again."; continue
        fi
        CHOICES="$CHOICES $WM"
    done
    CHOICES=${CHOICES# }; [ -n "$CHOICES" ] || return 0
    echo
    if console_login_set; then
        echo "This computer already logs someone in by itself at start-up, so the automatic login was not offered."; return 0
    fi
    case "$CHOICES" in
        *" "*) ask_no "There is no login screen on this computer. Log in as $ME automatically when it starts, and start i3 or sway?" || return 0
               printf "Start which one? 1) i3  2) sway [1]: "; read -r ANSWER || ANSWER=1
               case "$ANSWER" in 2*|s*|S*) WM=sway ;; *) WM=i3 ;; esac ;;
        *) WM=$CHOICES
           ask_no "There is no login screen on this computer. Log in as $ME automatically when it starts, and start $WM?" || return 0 ;;
    esac
    echo "Anyone who switches the computer on gets your session without a password. Changing the system's login asks for your password now."
    set_console_login "$ME" || { echo "Could not set up the automatic login; nothing was changed." >&2; return 0; }
    write_start "$WM"; open_at_login
    CFG=$(wm_config "$WM")
    if [ -z "$CFG" ] || [ "$(include_state "$CFG")" != current ]; then
        echo "Note: your $WM config does not include TVWCS, so TVWCS will not start with $WM. Add this line to it:"; echo "    $INCLUDE_LINE"
    fi
    echo "From now on, the computer logs in as $ME and starts $WM when it starts."
    AUTOLOGIN_WM=$WM
}
open_at_login() {   # TVWCS opens its Quick Menu when the session starts (Settings > Options > Open at login), as a TV would
    if XDG_CONFIG_HOME="$CONFIG_HOME" PYTHONPATH="$DEST" python3 -c 'from tvwcs.model import ConfigStore
s = ConfigStore(); s.settings["startup"]["mode"] = "menu"; s.save()' 2>/dev/null; then
        echo "TVWCS now opens its Quick Menu at log-in (Settings > Options > Open at login changes that)."
    else echo "Could not set TVWCS to open at log-in; turn it on in its Settings > At login." >&2; fi
}
# Once the install is done, the session the automatic login starts is started now rather than at the next boot.
start_console_session() {
    WM=$AUTOLOGIN_WM; echo
    if [ -n "$(wm_socket "$WM")" ]; then echo "$WM is already running; the automatic login takes over at the next start."; return 0; fi
    if [ "$(tty 2>/dev/null || true)" = /dev/tty1 ] && [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
        echo "Starting $WM..."   # this is the first console itself: start it in this login, as the automatic one would
        if [ "$WM" = i3 ]; then exec startx; else exec sway; fi
    fi
    # Over SSH, or from another console: restart the first console's login, which logs in and starts it there.
    # Someone logged in there (at a text prompt, say) would lose their session, so then it waits for the next start.
    if command -v who >/dev/null 2>&1 && who 2>/dev/null | awk '$2 == "tty1" { found = 1 } END { exit !found }'; then
        echo "Someone is logged in on the computer's first console, so $WM was not started now; it starts there at the next start."; return 0
    fi
    as_root systemctl restart getty@tty1.service || { echo "Could not start the console login now; $WM starts when the computer next starts." >&2; return 0; }
    if command -v chvt >/dev/null 2>&1; then as_root chvt 1 >/dev/null 2>&1 || true; fi   # put the first console on the screen
    echo "Started $WM: the computer's screen logs in as $(id -un) and shows it now."
}
AUTOLOGIN_WM=""
if [ "$SETUP" = dedicated ]; then setup_autologin
elif console_login_set; then   # left from an earlier dedicated setup: say so, but leave it alone
    echo; echo "This computer still logs someone in by itself at start-up (from an earlier install). To stop that, delete $GETTY_OVERRIDE and the TVWCS lines in your shell's login file."
fi

# ------------------------------------------------------------------ restart a running TVWCS
# A running TVWCS keeps using the old program until it is restarted. Offer to do that now. The in-app updater sets
# TVWCS_NO_RESTART because it restarts TVWCS itself; without a terminal to ask in, only say what to do.
running() { [ -n "$1" ] && kill -0 "$1" 2>/dev/null && { [ ! -r "/proc/$1/cmdline" ] || grep -q tvwcs "/proc/$1/cmdline"; }; }
# The same rule as tvwcs/session.py: XDG_RUNTIME_DIR, else ~/.cache/tvwcs. Over SSH this login may have no
# XDG_RUNTIME_DIR while the graphical one does, so /run/user/<uid> is tried too: the first that holds a running TVWCS.
RUNTIME=""; PIDFILE=""; PID=""
for D in "$(user_runtime)" "${XDG_CACHE_HOME:-$HOME/.cache}/tvwcs"; do
    [ -n "$D" ] || continue
    [ -n "$PIDFILE" ] || { RUNTIME=$D; PIDFILE=$D/tvwcs.pid; }
    P=$(cat "$D/tvwcs.pid" 2>/dev/null || true)
    if running "$P"; then RUNTIME=$D; PIDFILE=$D/tvwcs.pid; PID=$P; break; fi
done
start_tvwcs() {
    # Start it the way the window manager does (so it gets the session's environment), or detached from this
    # terminal in a graphical one. Over SSH there is no display to start it on except through the window manager.
    if wm_msg sway -q "exec '$DEST/bin/tvwcs'" 2>/dev/null; then :
    elif wm_msg i3 -q "exec --no-startup-id '$DEST/bin/tvwcs'" 2>/dev/null; then :
    elif [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then setsid nohup "$DEST/bin/tvwcs" >/dev/null 2>&1 < /dev/null &
    else return 1; fi
}
restart_tvwcs() {
    XDG_RUNTIME_DIR="$RUNTIME" "$DEST/bin/tvwcs" stop >/dev/null 2>&1 || kill "$PID" 2>/dev/null || true
    n=0; while running "$PID" && [ $n -lt 50 ]; do sleep 0.1; n=$((n+1)); done
    if running "$PID"; then echo "TVWCS did not stop; restart it yourself (or log in again) to load the new version." >&2; return; fi
    if ! start_tvwcs; then echo "TVWCS was stopped, but i3 or sway could not be reached to start it again; it starts at the next log-in." >&2; return; fi
    n=0; while [ $n -lt 50 ]; do
        NEW=$(cat "$PIDFILE" 2>/dev/null || true)
        if [ "$NEW" != "$PID" ] && running "$NEW"; then echo "TVWCS restarted with version $VERSION."; return; fi
        sleep 0.1; n=$((n+1))
    done
    echo "TVWCS was stopped but did not come back; start it with: $DEST/bin/tvwcs" >&2
}

# ------------------------------------------------------------------ on a TV, or on a desktop monitor
# Asked until it is answered (Settings > Options > Used on changes it later): sets TVWCS's interface size and
# where apps open. A running TVWCS is told to read its options again, so it never saves over the choice.
config_py() { XDG_CONFIG_HOME="$CONFIG_HOME" PYTHONPATH="$DEST" python3 -c "$@" 2>/dev/null; }
choose_use() {
    USE=$(config_py 'from tvwcs.model import ConfigStore; print(ConfigStore().settings["use"])') || return 0
    [ -z "$USE" ] && [ -t 0 ] || return 0
    echo
    printf "Will TVWCS be used on a TV or on a desktop monitor?\n  1) A TV: TV Mode size, and each app opens in a workspace of its own\n  2) A desktop monitor: Desktop size, and apps open tiled in the current workspace\nChoose 1 (TV) or 2 (desktop) [1]: "
    read -r ANSWER || ANSWER=n
    case "$ANSWER" in ""|1*|[Tt]*) USE=tv; ON="a TV" ;; 2*|[Dd]*) USE=desktop; ON="a desktop monitor" ;;
        *) echo "Left as it is; choose it later in Settings > Options > Used on."; return 0 ;; esac
    if config_py 'import sys; from tvwcs.model import ConfigStore, apply_use
s = ConfigStore(); apply_use(s.settings, sys.argv[1]); s.save()' "$USE"; then
        echo "TVWCS is set up for $ON (Settings > Options > Used on changes it)."
        if running "$PID"; then XDG_RUNTIME_DIR="$RUNTIME" "$DEST/bin/tvwcs" reload >/dev/null 2>&1 || true; fi
    else echo "Could not save that; choose it in Settings > Options > Used on." >&2; fi
}
choose_use
if [ "$SRC" != "$DEST" ] && [ -z "${TVWCS_NO_RESTART:-}" ] && running "$PID"; then
    echo
    if [ -t 0 ]; then
        printf "TVWCS is running. Restart it now to load the version just installed (%s)? [Y/n] " "$VERSION"
        read -r ANSWER || ANSWER=n
        case "$ANSWER" in
            [Nn]*) echo "Left it running. Restart TVWCS later (or log in again) to load the new version." ;;
            *) restart_tvwcs ;;
        esac
    else
        echo "TVWCS is running. To load the version just installed, run: '$DEST/bin/tvwcs' stop && '$DEST/bin/tvwcs' &"
    fi
fi

# ------------------------------------------------------------------ the old copy
# Removed only once nothing uses it any more: no window manager config still includes it.
if [ -n "$MIGRATING" ]; then
    STILL=""
    for WM in i3 sway; do
        CFG=$(wm_config "$WM")
        [ -n "$CFG" ] && [ "$(include_state "$CFG")" = other ] && STILL="$STILL $CFG"
    done
    echo
    if [ -n "$STILL" ]; then
        echo "Kept the old copy in $LEGACY: still included by$STILL."
    elif [ "$SRC" = "$LEGACY" ]; then
        echo "The old copy in $LEGACY (where this script ran from) is no longer used; you can delete that folder."
    elif ask "Delete the old copy in $LEGACY? Nothing uses it any more." migrate; then
        rm -rf "$LEGACY"; echo "Deleted $LEGACY."
    else
        echo "Kept $LEGACY; you can delete it whenever you like."
    fi
fi

# ------------------------------------------------------------------ what next
if [ "$SETUP" = alongside ] && [ -n "$LOGIN_ENTRY" ]; then
    echo; echo "Done. To use TVWCS, log out and choose$(for WM in $SESSION_WMS; do printf ' "TVWCS (%s)"' "$WM"; done | sed 's/" "/" or "/g') at the login screen."
fi
# The dedicated setup: start the session set up above, now.
[ -z "$AUTOLOGIN_WM" ] || start_console_session
