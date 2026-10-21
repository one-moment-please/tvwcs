#!/bin/sh
# TVWCS's installer. It installs, upgrades or removes TVWCS for the user running it. Run it on its own:
#
#     wget -qO- https://raw.githubusercontent.com/one-moment-please/tvwcs/main/install.sh | bash
#
# (it then downloads the release you choose), or from an unpacked release (./install.sh; it then offers to install
# that release, or to download another). It asks every question first and changes nothing until you agree to the
# list of what it will do:
#   - with TVWCS installed: upgrade, install a different version (the prerelease, or one of the two releases before
#     the latest) or remove TVWCS;
#   - i3, sway or both (sway is suggested on a new computer: it plays video more smoothly; i3 can suit games and
#     older applications better);
#   - the login screen: TVWCS's own is installed when there is none, and offered when there is another;
#   - TVWCS always gets a "TVWCS" session of its own at the login screen, which runs it in TV mode. It can also be
#     added to your usual i3 / sway session (one include line in its config), where it runs in desktop mode;
#   - the packages it needs, grouped by what they are for.
# If anything fails, the changes made so far are undone. Every change to a file of yours is backed up as
# <file>.tvwcs-backup. Your settings in ~/.config/tvwcs are kept on an upgrade. Supported: Debian and its family
# (apt), with systemd.
#
# Without a terminal (the in-app updater) it only upgrades the program in place, keeping every choice made before.
#
# Options: --missing only lists the packages this version needs that are not installed, one per line as
# "need<TAB>packages<TAB>what for", and changes nothing. --help shows this text.
# Environment: TVWCS_DEST=<folder> installs somewhere else than ~/.local/share/tvwcs. TVWCS_NO_RESTART=1 leaves a
# running TVWCS alone. TVWCS_WMS="i3 sway" answers which window managers (default: asked, or those set up before).
# TVWCS_VERSION=package|latest|<x.y.z> answers which version (default: this package, else the latest release).
# The tests use TVWCS_ETC, TVWCS_RUN, TVWCS_SHARE, TVWCS_BINDIR, TVWCS_LIBEXEC, TVWCS_X_SERVER, TVWCS_GITHUB and
# TVWCS_PACKAGES (the packages to treat as installed) to stand in for the system.
set -eu

REPO=one-moment-please/tvwcs
GITHUB=${TVWCS_GITHUB:-https://github.com}
API=${TVWCS_API:-https://api.github.com}
CONFIG_HOME=${XDG_CONFIG_HOME:-$HOME/.config}
DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
DEST=${TVWCS_DEST:-$DATA_HOME/tvwcs}
ETC=${TVWCS_ETC:-/etc}
SHARE=${TVWCS_SHARE:-/usr/share}
BINDIR=${TVWCS_BINDIR:-/usr/local/bin}
TVCONF=$CONFIG_HOME/tvwcs
RECORD=$TVCONF/installed-packages   # the packages this installer installed, for removing TVWCS later

# ====================================================================== talking to the person installing
# Questions are read from the terminal. Run as `wget ... | bash`, the script itself comes in on standard input, so
# they are read from /dev/tty instead. Without either (the in-app updater, or ssh without -t) nothing is asked.
TTY=""
find_tty() {
    if [ -n "${TVWCS_NONINTERACTIVE:-}" ]; then TTY=""; return; fi
    if [ -t 0 ]; then TTY=/dev/stdin; return; fi
    if [ -p /dev/stdin ] && [ -r /dev/tty ] && ( : </dev/tty ) 2>/dev/null; then TTY=/dev/tty; fi
}
say() { printf '%s\n' "$*"; }
heading() { printf '\n== %s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }
read_answer() {   # read_answer -> ANSWER (empty without a terminal)
    ANSWER=""
    [ -n "$TTY" ] || return 1
    IFS= read -r ANSWER < "$TTY" || { ANSWER=""; return 1; }
    return 0
}
ask_yes() {   # ask_yes "question" -> yes (Enter) or no
    [ -n "$TTY" ] || return 1
    printf '%s [Y/n] ' "$1"; read_answer || return 1
    case "$ANSWER" in [Nn]*) return 1 ;; *) return 0 ;; esac
}
ask_no() {   # ask_no "question" -> no (Enter) or yes
    [ -n "$TTY" ] || return 1
    printf '%s [y/N] ' "$1"; read_answer || return 1
    case "$ANSWER" in [Yy]*) return 0 ;; *) return 1 ;; esac
}
# choose <default number> <choice 1> <choice 2> ... -> CHOICE (the number chosen). Asked again until it is one of them.
choose() {
    DEFAULT=$1; shift; N=0
    for C in "$@"; do N=$((N+1)); printf '  %s) %s\n' "$N" "$C"; done
    CHOICE=$DEFAULT
    [ -n "$TTY" ] || return 0
    while :; do
        printf 'Choose 1-%s [%s]: ' "$N" "$DEFAULT"; read_answer || { CHOICE=$DEFAULT; return 0; }
        case "$ANSWER" in "") CHOICE=$DEFAULT; return 0 ;; *[!0-9]*) ;; *) [ "$ANSWER" -ge 1 ] && [ "$ANSWER" -le "$N" ] && { CHOICE=$ANSWER; return 0; } ;; esac
        say "Type a number from 1 to $N."
    done
}

# ====================================================================== this computer
distro() {   # debian (Debian and its family) or unknown
    ( if [ -r "$ETC/os-release" ]; then . "$ETC/os-release"; elif [ "$ETC" = /etc ] && [ -r /usr/lib/os-release ]; then . /usr/lib/os-release; fi
      for D in ${ID:-} ${ID_LIKE:-}; do case "$D" in debian|ubuntu|linuxmint|pop|raspbian) echo debian; exit ;; esac; done; echo unknown )
}
init_system() { if [ -d "${TVWCS_RUN:-/run}/systemd/system" ]; then echo systemd; else echo other; fi; }
have() { command -v "$1" >/dev/null 2>&1; }
# Run as root, asking for the password on the terminal (sudo reads it from the terminal itself, never from the script's
# input, which may be the script itself).
as_root() {
    if [ "$(id -u)" = 0 ]; then "$@"
    elif have sudo; then sudo "$@" </dev/null
    elif have doas; then doas "$@" </dev/null
    else warn "Neither sudo nor doas is installed, so the system cannot be changed."; return 1; fi
}
root() { as_root "$@"; }
pkg_installed() {   # pkg_installed <package>
    if [ -n "${TVWCS_PACKAGES+set}" ]; then case " $TVWCS_PACKAGES " in *" $1 "*) return 0 ;; *) return 1 ;; esac; fi
    dpkg-query -W -f='${db:Status-Abbrev}' "$1" 2>/dev/null | grep -q '^ii'
}
x_server() {   # the X server already installed: XLibre, Xorg, or "" for none
    if [ -n "${TVWCS_X_SERVER+set}" ]; then echo "$TVWCS_X_SERVER"; return 0; fi
    for X in Xlibre Xorg; do P=$(command -v "$X" 2>/dev/null) || continue
        if [ "$X" = Xlibre ] || "$P" -version 2>&1 | grep -qi xlibre; then echo XLibre; return 0; fi; done
    for P in /usr/bin/Xlibre /usr/lib/xorg/Xlibre; do [ -x "$P" ] && { echo XLibre; return 0; }; done
    for P in /usr/bin/Xorg /usr/lib/xorg/Xorg; do [ -x "$P" ] && { echo Xorg; return 0; }; done
    echo ""
}
libexec_has() { for d in ${TVWCS_LIBEXEC:-/usr/libexec /usr/lib/gvfs /usr/lib}; do [ -e "$d/$1" ] && return 0; done; return 1; }

# ---- login screens
DISPLAY_MANAGERS="gdm3 gdm sddm lightdm lxdm xdm slim ly greetd emptty nodm entrance lemurs"
WAYLAND_LOGIN_SCREENS="gdm gdm3 sddm greetd ly emptty lemurs tvwcs"
login_screen() {   # the login screen that runs at start-up (lightdm, gdm3, tvwcs...), or "" for none
    N=""
    if [ -L "$ETC/systemd/system/display-manager.service" ]; then N=$(readlink "$ETC/systemd/system/display-manager.service"); N=${N##*/}; N=${N%.service}
    elif [ -s "$ETC/X11/default-display-manager" ]; then N=$(sed -n 1p "$ETC/X11/default-display-manager"); N=${N##*/}
    else for DM in $DISPLAY_MANAGERS; do have "$DM" && { N=$DM; break; }; done; fi
    if [ "$N" = greetd ] && grep -q 'tvwcs-greeter/greeter' "$ETC/greetd/config.toml" 2>/dev/null; then N=tvwcs; fi
    echo "$N"
}
login_screen_name() {
    case "$1" in
        tvwcs) echo "TVWCS's login screen" ;; gdm|gdm3) echo "GNOME's login screen (GDM)" ;; sddm) echo SDDM ;;
        lightdm) echo LightDM ;; "") echo "no login screen" ;; *) echo "$1" ;;
    esac
}
wayland_login_screen() { case " $WAYLAND_LOGIN_SCREENS " in *" $1 "*) return 0 ;; esac; [ -z "$1" ]; }
other_login_screens() {   # the login screens installed besides TVWCS's (by unit), for switching to before removing
    for U in $DISPLAY_MANAGERS; do
        [ "$U" = greetd ] && continue
        for D in "$ETC/systemd/system" "${TVWCS_UNITS:-/usr/lib/systemd/system}" /lib/systemd/system; do
            [ -f "$D/$U.service" ] && { printf '%s ' "$U"; break; }
        done
    done | sed 's/gdm3 gdm /gdm3 /'
}
GETTY_OVERRIDE=$ETC/systemd/system/getty@tty1.service.d/autologin.conf
START_BEGIN="# >>> TVWCS: start the window manager after the automatic login (added by install.sh; delete to undo) >>>"
START_END="# <<< TVWCS <<<"
profile_file() {   # the file this user's login shell reads at log-in
    LOGIN_SHELL=$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f7); LOGIN_SHELL=${LOGIN_SHELL:-${SHELL:-/bin/sh}}
    case ${LOGIN_SHELL##*/} in
        fish) echo "$CONFIG_HOME/fish/conf.d/tvwcs-autostart.fish" ;;
        zsh) echo "${ZDOTDIR:-$HOME}/.zprofile" ;;
        bash) for F in "$HOME/.bash_profile" "$HOME/.bash_login"; do [ -f "$F" ] && { echo "$F"; return; }; done; echo "$HOME/.profile" ;;
        *) echo "$HOME/.profile" ;;
    esac
}
start_lines_wm() {   # the window manager the shell's start lines (an older install's automatic login) start, or ""
    F=$(profile_file); grep -qxF "$START_BEGIN" "$F" 2>/dev/null || return 0
    if grep -q 'exec startx' "$F"; then echo i3; elif grep -q 'exec sway' "$F"; then echo sway; fi
}

# ---- i3 and sway configs
wm_config() {   # the config file plain i3 / sway reads, or "" when there is none
    if [ "$1" = i3 ]; then set -- "$CONFIG_HOME/i3/config" "$HOME/.i3/config"; else set -- "$CONFIG_HOME/sway/config" "$HOME/.sway/config"; fi
    for C in "$@"; do [ -f "$C" ] && { echo "$C"; return; }; done; echo ""
}
session_config() { echo "$TVCONF/$1-session.conf"; }
include_path() { case "$DEST" in "$HOME"/*) echo "~/${DEST#"$HOME"/}/tvwcs.conf" ;; *) echo "$DEST/tvwcs.conf" ;; esac; }
include_line() { P=$(include_path); case "$P" in *" "*) echo "include \"$P\"" ;; *) echo "include $P" ;; esac; }
include_state() {   # include_state <config> -> current, other (a tvwcs.conf elsewhere) or none
    WANT="$DEST/tvwcs.conf" awk '
        /^[ \t]*include[ \t]/ && /tvwcs\.conf/ {
            p = $0; sub(/^[ \t]*include[ \t]+/, "", p); sub(/[ \t]+$/, "", p); gsub(/^["\047]|["\047]$/, "", p)
            if (substr(p, 1, 2) == "~/") p = ENVIRON["HOME"] substr(p, 2)
            gsub(/\$HOME/, ENVIRON["HOME"], p)
            if (p == ENVIRON["WANT"]) found = "current"; else if (found == "") found = "other"
        }
        END { print (found == "" ? "none" : found) }' "$1"
}
current_layout() {   # "layout variant" of the keyboard in use, best guess
    L=""; V=""
    if have setxkbmap && [ -n "${DISPLAY:-}" ]; then Q=$(setxkbmap -query 2>/dev/null || true)
        L=$(echo "$Q" | awk '/^layout:/ {print $2}'); V=$(echo "$Q" | awk '/^variant:/ {print $2}'); fi
    if [ -z "$L" ] && have localectl; then Q=$(localectl status 2>/dev/null || true)
        L=$(echo "$Q" | awk -F': *' '/X11 Layout/ {print $2}'); V=$(echo "$Q" | awk -F': *' '/X11 Variant/ {print $2}'); fi
    if [ -z "$L" ] && [ -f "$ETC/default/keyboard" ]; then
        L=$(sed -n 's/^XKBLAYOUT="\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' "$ETC/default/keyboard"); V=$(sed -n 's/^XKBVARIANT="\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' "$ETC/default/keyboard"); fi
    echo "${L:-us} $V"
}
known_layout() {
    LST=/usr/share/X11/xkb/rules/evdev.lst; [ -f "$LST" ] || return 0
    for X in $(echo "$1" | tr ',' ' '); do
        awk -v want="$X" '/^! layout/ {on=1; next} /^!/ {on=0} on && $1 == want {found=1} END {exit !found}' "$LST" || return 1
    done
}

# ====================================================================== releases
fetch() {   # fetch <url> <file>
    if have wget; then wget -qO "$2" "$1"
    elif have curl; then curl -fsSL -o "$2" "$1"
    else warn "Neither wget nor curl is installed, so nothing can be downloaded."; return 1; fi
}
# The release list, one line per release: "<version> <latest|prerelease|release>", newest first. GitHub's answer is
# read with grep and awk (python is not always there yet): each release's tag_name comes before its draft and
# prerelease fields; quotes inside text are escaped, so a release's notes cannot be mistaken for them.
RELEASES=""; LATEST=""
read_releases() {
    [ -z "$RELEASES" ] || return 0
    T=$WORK/releases.json; L=$WORK/latest.json
    fetch "$API/repos/$REPO/releases?per_page=30" "$T" 2>/dev/null || return 1
    fetch "$API/repos/$REPO/releases/latest" "$L" 2>/dev/null || :
    LATEST=$(grep -o '"tag_name": *"[^"]*"' "$L" 2>/dev/null | sed -n '1s/.*"v\{0,1\}\([^"]*\)"$/\1/p')
    RELEASES=$(grep -o '"tag_name": *"[^"]*"\|"draft": *[a-z]*\|"prerelease": *[a-z]*' "$T" | awk -v latest="$LATEST" '
        /"tag_name"/ { if (tag != "" && draft != "true") out(); tag = $0; sub(/.*: *"v?/, "", tag); sub(/"$/, "", tag); draft = ""; pre = "" }
        /"draft"/ { draft = $0; sub(/.*: */, "", draft) }
        /"prerelease"/ { pre = $0; sub(/.*: */, "", pre) }
        function out() { if (tag ~ /^[0-9]+(\.[0-9]+)*$/) print tag, (tag == latest ? "latest" : pre == "true" ? "prerelease" : "release") }
        END { if (tag != "" && draft != "true") out() }' | sort -t. -k1,1nr -k2,2nr -k3,3nr)
    [ -n "$LATEST" ] || LATEST=$(echo "$RELEASES" | awk '$2 == "release" { print $1; exit }')
    [ -n "$RELEASES" ]
}
version_lt() {   # version_lt a b: a is older than b
    [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -t. -k1,1n -k2,2n -k3,3n | sed -n 1p)" = "$1" ]
}
other_versions() {   # the prerelease newer than the latest (when there is one), then the two releases before the latest
    echo "$RELEASES" | awk -v latest="$LATEST" '
        function lt(a, b,   x, y, i, n) { n = split(a, x, "."); split(b, y, "."); for (i = 1; i <= 3; i++) if (x[i] + 0 != y[i] + 0) return x[i] + 0 < y[i] + 0; return 0 }
        $2 == "prerelease" && pre == "" && lt(latest, $1) { pre = $1; print $1, "prerelease" }
        $2 == "release" && lt($1, latest) && n < 2 { n++; print $1, "release" }'
}
download_release() {   # download_release <version>: unpack its tvwcs.tar.gz (else its zip) into $WORK/download -> SRC
    D=$WORK/download; rm -rf "$D"; mkdir -p "$D"
    say "Downloading TVWCS $1..."
    if fetch "$GITHUB/$REPO/releases/download/v$1/tvwcs.tar.gz" "$WORK/tvwcs.tar.gz" 2>/dev/null && tar -xzf "$WORK/tvwcs.tar.gz" -C "$D"; then :
    elif fetch "$GITHUB/$REPO/releases/download/v$1/TVWCS-$1.zip" "$WORK/tvwcs.zip" 2>/dev/null &&
         { if have unzip; then unzip -q "$WORK/tvwcs.zip" -d "$D"; else python3 -m zipfile -e "$WORK/tvwcs.zip" "$D"; fi; }; then :
    else warn "Could not download TVWCS $1 from GitHub."; return 1; fi
    [ -f "$D/tvwcs/tvwcs/main.py" ] || { warn "The download of TVWCS $1 does not hold TVWCS."; return 1; }
    set_source "$D/tvwcs"
}

# ====================================================================== where TVWCS comes from
# A release (or an installed copy) has the package in tvwcs/ next to this script; the repository has it in package/.
PACKAGED=""; SRC=""; PKG_VERSION=""
set_source() {
    if [ -d "$1/package/tvwcs" ]; then SRC=$1; PKG=$1/package/tvwcs; BIN=$1/package/bin/tvwcs; DATA=$1/data
    else SRC=$1; PKG=$1/tvwcs; BIN=$1/bin/tvwcs; DATA=$1; fi
    SRC_VERSION=$(cat "$SRC/VERSION" 2>/dev/null || echo "?")
}
find_package() {
    case "$0" in */*) D=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd) || return 0 ;; *) return 0 ;; esac   # piped to bash: $0 is "bash"
    [ -f "$D/install.sh" ] || return 0
    for P in "$D" "$D/.."; do
        if [ -f "$P/tvwcs/main.py" ] || [ -f "$P/package/tvwcs/main.py" ]; then
            P=$(CDPATH= cd -- "$P" && pwd); set_source "$P"; PACKAGED=$P; PKG_VERSION=$SRC_VERSION; return 0
        fi
    done
}

# ====================================================================== the packages, grouped by what they are for
# need <group label> <packages...>: the ones not installed are added to that group
NEEDS=""   # lines "label<TAB>packages"
need() {
    LABEL=$1; shift; MISSING=""
    for P in "$@"; do pkg_installed "$P" || MISSING="$MISSING $P"; done
    [ -z "$MISSING" ] || NEEDS="$NEEDS$LABEL	${MISSING# }
"
}
work_out_packages() {
    NEEDS=""
    need "TVWCS's windows: GTK 4 for Python, and cairo for the screen saver" python3 python3-gi gir1.2-gtk-4.0 python3-gi-cairo
    case " $WMS " in *" sway "*)
        need "sway, its idle timer (Power and sleep) and its lock screen" sway swayidle swaylock ;; esac
    case " $WMS " in *" i3 "*)
        X="xserver-xorg"; [ -z "$(x_server)" ] || X=""   # XLibre replaces Xorg: installing Xorg over it would undo that
        # shellcheck disable=SC2086
        need "i3 with $( [ -n "$X" ] && echo "Xorg and " )startx" i3 $X xinit
        need "i3 helpers: window placement (xdotool), displays and background (xrandr, xsetroot), app scaling (xsettingsd)" xdotool x11-xserver-utils xsettingsd
        need "i3's idle timer (Power and sleep), lock screen and screen saver while locked" libxss1 i3lock xsecurelock
        need "hiding the mouse pointer in TV mode (i3)" unclutter-xfixes ;; esac
    case "$GREETER" in
        tvwcs) need "TVWCS's login screen" greetd cage ;;
        sddm) need "SDDM, a standard login screen" sddm ;;
    esac
    if ! have pipewire && ! have pulseaudio; then need "sound: PipeWire, with its PulseAudio layer" pipewire pipewire-pulse wireplumber dbus-user-session; fi
    need "Settings > Sound" pulseaudio-utils
    need "Settings > Network (Ethernet and Wi-Fi)" network-manager
    need "Settings > Bluetooth" bluez
    need "Settings > Terminal" gir1.2-vte-3.91
    need "Settings > Storage (drives)" udisks2
    need "light or dark mode for GTK and Flatpak apps and browsers, network shares" libglib2.0-bin xdg-desktop-portal xdg-desktop-portal-gtk
    need "the look: icons and the Open Sans font" adwaita-icon-theme fonts-open-sans
}
all_needed() { printf '%s' "$NEEDS" | cut -f2 | tr '\n' ' ' | sed 's/ *$//'; }
show_needs() {
    printf '%s' "$NEEDS" | while IFS='	' read -r LABEL PKGS; do printf '  %s\n      %s\n' "$LABEL" "$PKGS"; done
}

# ====================================================================== undoing a failed install
# Each change is written down in $WORK/undo as it is made; if a later step fails, they are undone newest first.
UNDO=""
undo_note() { printf '%s\n' "$*" >> "$UNDO"; }
keep_file() {   # keep_file <file>: a copy to put back (or, when it does not exist yet, a note to delete it)
    if [ -e "$1" ]; then N=$WORK/keep.$(wc -l < "$UNDO" | tr -d ' '); cp -p "$1" "$N"; undo_note "restore	$1	$N"
    else undo_note "delete	$1"; fi
}
keep_root_file() {
    if [ -e "$1" ]; then N=$WORK/keep.$(wc -l < "$UNDO" | tr -d ' '); cp -p "$1" "$N" 2>/dev/null || as_root cp -p "$1" "$N"; undo_note "rootrestore	$1	$N"
    else undo_note "rootdelete	$1"; fi
}
revert() {
    [ -s "$UNDO" ] || return 0
    warn ""; warn "Undoing the changes made so far..."
    awk '{ l[NR] = $0 } END { for (i = NR; i >= 1; i--) print l[i] }' "$UNDO" | while IFS='	' read -r KIND A B; do
        case "$KIND" in
            restore) cp -p "$B" "$A" ;;
            delete) rm -rf "$A" ;;
            rootrestore) as_root cp -p "$B" "$A" ;;
            rootdelete) as_root rm -f "$A" ;;
            program) rm -rf "$A"; [ ! -d "$B" ] || mv "$B" "$A" ;;
            packages) # shellcheck disable=SC2086
                as_root env DEBIAN_FRONTEND=noninteractive apt-get remove -y $A >/dev/null 2>&1 || warn "Could not uninstall: $A" ;;
            loginscreen) as_root env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$B" python3 -m tvwcs.loginscreen disable --to "$A" >/dev/null 2>&1 ||
                             warn "Could not turn TVWCS's login screen off again." ;;
            switch) [ -z "$A" ] || as_root env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$B" python3 -m tvwcs.loginscreen switch "$A" >/dev/null 2>&1 || : ;;
        esac
    done || true
    : > "$UNDO"; warn "Undone."
}
fail() { warn ""; warn "The installation failed: $*"; revert; exit 1; }

# ====================================================================== the questions
ACTION=install   # install or remove
choose_version() {
    INSTALLED=$(cat "$DEST/VERSION" 2>/dev/null || true); [ -f "$DEST/tvwcs/main.py" ] || INSTALLED=""
    if [ -n "${TVWCS_VERSION:-}" ]; then pick_version "$TVWCS_VERSION"; return; fi
    if [ -z "$TTY" ]; then   # the in-app updater, or no terminal: this package, else the latest release
        if [ -n "$PACKAGED" ]; then pick_version package; else pick_version latest; fi; return
    fi
    read_releases || say "(GitHub's list of releases could not be read, so only $( [ -n "$PACKAGED" ] && echo "this package" || echo "nothing") can be installed.)"
    if [ -z "$PACKAGED" ] && [ -z "$LATEST" ]; then fail "TVWCS's releases could not be found on GitHub. Check the network connection."; fi
    heading "TVWCS"
    if [ -n "$INSTALLED" ]; then say "TVWCS $INSTALLED is installed in $DEST."; fi
    set --; KEYS=""
    if [ -n "$PACKAGED" ]; then
        if [ -z "$INSTALLED" ]; then W="Install TVWCS $PKG_VERSION from this package"
        elif [ "$INSTALLED" = "$PKG_VERSION" ]; then W="Reinstall TVWCS $PKG_VERSION from this package"
        elif version_lt "$INSTALLED" "$PKG_VERSION"; then W="Upgrade to TVWCS $PKG_VERSION from this package"
        else W="Go back to TVWCS $PKG_VERSION from this package"; fi
        set -- "$W"; KEYS="package"
    fi
    if [ -n "$LATEST" ] && [ "$LATEST" != "$PKG_VERSION" ]; then
        if [ -z "$INSTALLED" ]; then W="Install TVWCS $LATEST, the latest release"
        elif [ "$INSTALLED" = "$LATEST" ]; then W="Reinstall TVWCS $LATEST, the latest release"
        else W="Upgrade to TVWCS $LATEST, the latest release"; fi
        set -- "$@" "$W$( [ -n "$PACKAGED" ] && echo " (downloaded)")"; KEYS="$KEYS latest"
    fi
    [ -z "$RELEASES" ] || { set -- "$@" "Install a different version"; KEYS="$KEYS other"; }
    [ -z "$INSTALLED" ] || { set -- "$@" "Remove TVWCS"; KEYS="$KEYS remove"; }
    set -- "$@" "Cancel"; KEYS="$KEYS cancel"
    choose 1 "$@"
    K=$(echo $KEYS | cut -d' ' -f"$CHOICE")
    case "$K" in
        cancel) say "Nothing was changed."; exit 0 ;;
        remove) ACTION=remove ;;
        other)
            OTHERS=$(other_versions)
            [ -n "$OTHERS" ] || { say "There is no other version to choose."; exit 0; }
            say; say "Which version?"
            set --; for V in $(echo "$OTHERS" | awk '{ print $1 }'); do
                if echo "$OTHERS" | grep -q "^$V prerelease"; then set -- "$@" "$V, the prerelease (not tested as much as the latest)"
                else set -- "$@" "$V, an earlier release"; fi
            done
            set -- "$@" "Cancel"; choose 1 "$@"
            V=$(echo "$OTHERS" | sed -n "${CHOICE}p" | awk '{ print $1 }')
            [ -n "$V" ] || { say "Nothing was changed."; exit 0; }
            pick_version "$V" ;;
        *) pick_version "$K" ;;
    esac
}
pick_version() {   # package, latest or a version number -> WANT ("" for this package)
    case "$1" in
        package) [ -n "$PACKAGED" ] || fail "There is no package next to install.sh to install from."; WANT="" ;;
        latest) read_releases || fail "TVWCS's releases could not be found on GitHub. Check the network connection."; WANT=$LATEST ;;
        *) WANT=${1#v} ;;
    esac
    if [ -n "$WANT" ] && [ "$WANT" = "$PKG_VERSION" ]; then WANT=""; fi
    TARGET=${WANT:-$PKG_VERSION}
}

choose_wms() {
    HAVE=""; have i3 && HAVE="i3"; have sway && HAVE="$HAVE sway"; HAVE=${HAVE# }
    SET_UP=""; for WM in i3 sway; do [ -f "$(session_config "$WM")" ] && SET_UP="$SET_UP $WM"; done; SET_UP=${SET_UP# }
    if [ -n "${TVWCS_WMS:-}" ]; then WMS=$TVWCS_WMS; return; fi
    if [ -z "$TTY" ]; then WMS=${SET_UP:-${HAVE:-}}; return; fi
    heading "Window manager"
    case "$HAVE" in
        "i3 sway") say "i3 and sway are both installed."; D=3 ;;
        i3) say "i3 is installed."; D=2 ;;
        sway) say "sway is installed."; D=1 ;;
        *) say "Neither i3 nor sway is installed. sway is recommended: it plays video more smoothly. i3 may work better"
           say "with games and older applications."; D=1 ;;
    esac
    case "$SET_UP" in "i3 sway") D=3 ;; i3) D=2 ;; sway) D=1 ;; esac
    say "Which should TVWCS use?"
    choose "$D" "sway$( [ -z "$HAVE" ] && echo " (recommended)")" "i3" "Both"
    case "$CHOICE" in 1) WMS=sway ;; 2) WMS=i3 ;; 3) WMS="i3 sway" ;; esac
}

GREETER=""   # what to do with the login screen: tvwcs (install / keep TVWCS's), sddm, keep
choose_login_screen() {
    LS=$(login_screen)
    if [ "$LS" = tvwcs ]; then GREETER=tvwcs; return; fi
    if [ "$(distro)" != debian ] || [ "$(init_system)" != systemd ]; then GREETER=keep; return; fi
    if [ -z "$TTY" ]; then GREETER=keep; return; fi
    heading "Login screen"
    if [ -z "$LS" ]; then
        say "There is no login screen here, so TVWCS's own is installed: it lists the sessions (TVWCS's first), and takes"
        say "the password from the remote on its on-screen keyboard, or from a keyboard."
        GREETER=tvwcs; return
    fi
    NAME=$(login_screen_name "$LS")
    case " $WMS " in *" sway "*) if ! wayland_login_screen "$LS"; then
        say "Warning: this computer's login screen, $NAME, cannot start sway reliably: sway may not start, or start"
        say "without a working keyboard and mouse. What should be done?"
        choose 1 "Install TVWCS's login screen (recommended: it starts i3 and sway, and works with the remote)" \
                 "Use i3 instead of sway" "Install SDDM, a standard login screen that starts i3 and sway" \
                 "Keep $NAME and install sway anyway" "Cancel the installation"
        case "$CHOICE" in
            1) GREETER=tvwcs ;; 2) WMS=i3; GREETER=keep ;; 3) GREETER=sddm ;; 4) GREETER=keep ;;
            5) say "Nothing was changed."; exit 0 ;;
        esac
        return
    fi ;; esac
    say "This computer uses $NAME. TVWCS has its own login screen: it lists TVWCS's sessions first and works with the"
    say "remote. $NAME stays installed, and Settings > User switches back."
    if ask_no "Use TVWCS's login screen instead?"; then GREETER=tvwcs; else GREETER=keep; fi
}

# What each window manager's usual config gets: add (the include line), create (a config with it), plain (a config
# without it), "" (left alone)
USUAL=""   # "i3:add sway:create"...
usual_of() { echo " $USUAL " | sed -n "s/.* $1:\([a-z]*\) .*/\1/p"; }
choose_usual() {
    USUAL=""
    for WM in $WMS; do
        CFG=$(wm_config "$WM")
        if [ -n "$CFG" ]; then
            case $(include_state "$CFG") in
                current) USUAL="$USUAL $WM:keep"; continue ;;
                other) USUAL="$USUAL $WM:move"; continue ;;   # an older install's include line: pointed at this one
            esac
            [ -n "$TTY" ] || continue
            heading "Your usual $WM session"
            say "TVWCS gets a \"TVWCS ($WM)\" session of its own at the login screen, which runs it in TV mode."
            if ask_no "Also add TVWCS to your usual $WM session ($CFG), where it runs in desktop mode?"; then USUAL="$USUAL $WM:add"; fi
        else
            [ -n "$TTY" ] || continue
            heading "Your usual $WM session"
            say "TVWCS gets a \"TVWCS ($WM)\" session of its own at the login screen, which runs it in TV mode. There is no"
            say "config for the usual $WM session yet. Set one up?"
            choose 3 "Yes, with TVWCS in it (desktop mode)" "Yes, without TVWCS" "Not now"
            case "$CHOICE" in 1) USUAL="$USUAL $WM:create" ;; 2) USUAL="$USUAL $WM:plain" ;; esac
        fi
    done
}
MOD=""; LAYOUT=""; VARIANT=""
choose_keys() {   # the modifier and the keyboard layout, for the configs to be created
    NEW=""
    for WM in $WMS; do
        [ -f "$(session_config "$WM")" ] || NEW=1
        case "$(usual_of "$WM")" in create|plain) NEW=1 ;; esac
    done
    [ -n "$NEW" ] || return 0
    set -- $(current_layout); CUR_L=$1; CUR_V=${2:-}
    MOD=Mod4; LAYOUT=$CUR_L; VARIANT=$CUR_V
    [ -n "$TTY" ] || return 0
    heading "Keys"
    say "Which key should be the window manager's modifier (\$mod)?"
    choose 1 "Super (the Windows key)" "Alt"
    [ "$CHOICE" = 2 ] && MOD=Mod1
    if ! ask_yes "Use the keyboard layout $CUR_L${CUR_V:+ ($CUR_V)}?"; then
        while :; do
            printf 'Keyboard layout (such as us, gb, de, fr; add a variant after a space, such as "us dvorak"): '
            read_answer || break
            set -- $ANSWER
            if [ $# -eq 0 ]; then break; fi
            if known_layout "$1"; then LAYOUT=$1; VARIANT=${2:-}; break; fi
            say "\"$1\" is not a keyboard layout XKB knows."
        done
    fi
}
choose_extras() {
    POWER_RULE=""; UNCLUTTER_OFF=""; AUTOLOGIN_MOVE=""
    [ -n "$TTY" ] || return 0
    ME=$(id -un)
    # an older install logged in on the first console by itself: TVWCS's login screen does it now, into TV mode
    if [ "$GREETER" = tvwcs ] && [ "$(login_screen)" != tvwcs ] && grep -q -- '--autologin' "$GETTY_OVERRIDE" 2>/dev/null; then
        WHO=$(sed -n 's/.*--autologin \([^ ]*\) .*/\1/p' "$GETTY_OVERRIDE" | sed -n 1p)
        SWM=$(start_lines_wm); case " $WMS " in *" ${SWM:-none} "*) ;; *) SWM=$(set -- $WMS; echo "$1") ;; esac
        AUTOLOGIN_MOVE="$WHO tvwcs-$SWM"
        say; say "$WHO is logged in by itself at start-up. From now on TVWCS's login screen does that, into TVWCS ($SWM)."
    fi
    if [ "$GREETER" = tvwcs ] && [ "$(login_screen)" = tvwcs ]; then
        AUTO=$(sed -n '/^\[initial_session\]/,/^\[/p' "$ETC/greetd/config.toml" 2>/dev/null | sed -n 's/^user *= *"\(.*\)"$/\1/p')
        if [ -n "$AUTO" ] && sed -n '/^\[initial_session\]/,/^\[/p' "$ETC/greetd/config.toml" | grep -q 'start-session x11 i3 \|start-session wayland sway '; then
            SWM=i3; sed -n '/^\[initial_session\]/,/^\[/p' "$ETC/greetd/config.toml" | grep -q 'start-session wayland sway ' && SWM=sway
            say; say "The login screen logs $AUTO in by itself to the usual $SWM session, which runs TVWCS in desktop mode from 4.0."
            if ask_yes "Log $AUTO in to TVWCS ($SWM) instead, in TV mode?"; then AUTOLOGIN_MOVE="$AUTO tvwcs-$SWM"; fi
        fi
    fi
    # Sleep, Reboot and Shut down without a password, when polkit cannot allow them
    if [ "$(id -u)" != 0 ] && have sudo && ! [ -f "$ETC/sudoers.d/zz-tvwcs-power-$(echo "$ME" | tr '.' '_')" ]; then
        heading "Power"
        if ask_no "Let TVWCS sleep, reboot and shut down without asking for your password? (A sudo rule allowing only those.)"; then POWER_RULE=1; fi
    fi
    if [ -f "$ETC/X11/Xsession.d/90unclutter" ] && grep -Eq '^[[:space:]]*START_UNCLUTTER="?true"?' "$ETC/default/unclutter" 2>/dev/null && [ ! -f "$TVCONF/unclutter-autostart-kept" ]; then
        say; say "unclutter is set to hide the mouse pointer in every X session, other desktops too. TVWCS's session hides it by itself."
        if ask_yes "Turn that off, so the pointer only hides in TVWCS's session?"; then UNCLUTTER_OFF=1; else mkdir -p "$TVCONF"; echo "Kept on by choice." > "$TVCONF/unclutter-autostart-kept"; fi
    fi
}

# ====================================================================== installing
copy_program() {
    OLD=""
    if [ -d "$DEST" ] && [ "$SRC" != "$DEST" ]; then OLD=$WORK/previous-program; cp -a "$DEST" "$OLD"; fi
    undo_note "program	$DEST	$OLD"
    [ "$SRC" = "$DEST" ] && return 0
    mkdir -p "$DEST/tvwcs" "$DEST/bin" || return 1
    rm -f "$DEST"/tvwcs/*.py; find "$DEST/tvwcs" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
    cp "$PKG"/*.py "$DEST/tvwcs/" || return 1
    cp "$BIN" "$DEST/bin/tvwcs" && chmod +x "$DEST/bin/tvwcs" || return 1
    P="$DEST/bin/tvwcs" awk '/^exec --no-startup-id .*\/bin\/tvwcs\047?$/ { print "exec --no-startup-id \047" ENVIRON["P"] "\047"; next } { print }' \
        "$DATA/tvwcs.conf" > "$DEST/tvwcs.conf" || return 1
    cp "$SRC/VERSION" "$DEST/" || return 1
    for F in README.md CHANGELOG.md TODO.md LICENSE install.sh; do [ ! -f "$SRC/$F" ] || cp "$SRC/$F" "$DEST/"; done
    for F in com.tvwcs.ControlPanel.desktop tvwcs-settings.svg tvwcs.svg; do [ ! -f "$DATA/$F" ] || cp "$DATA/$F" "$DEST/"; done
    session_wrapper > "$DEST/bin/tvwcs-session" && chmod +x "$DEST/bin/tvwcs-session"
}
add_launcher() {   # the Settings app in the applications list
    [ -f "$DEST/com.tvwcs.ControlPanel.desktop" ] || return 0
    case "$DEST" in *'$'*|*'`'*|*'\'*|*\"*) return 0 ;; esac
    A=$DATA_HOME/applications; mkdir -p "$A"; keep_file "$A/com.tvwcs.ControlPanel.desktop"
    P="$DEST/bin/tvwcs" I="$DEST/tvwcs-settings.svg" awk '/^Exec=tvwcs / { sub(/^Exec=tvwcs/, "Exec=\"" ENVIRON["P"] "\"") } /^Icon=/ { $0 = "Icon=" ENVIRON["I"] } { print }' \
        "$DEST/com.tvwcs.ControlPanel.desktop" > "$A/com.tvwcs.ControlPanel.desktop"
    have update-desktop-database && update-desktop-database -q "$A" 2>/dev/null || true
}
default_hotkeys() {
    HK=$TVCONF/hotkeys.conf; [ ! -f "$HK" ] || return 0
    mkdir -p "$TVCONF"; undo_note "delete	$HK"
    { echo "# Generated by TVWCS Settings. Change hotkeys there; edits made here are overwritten."
      echo "# Keyboard: Quick Menu (Super (tap))"; echo "bindcode --release 133 exec --no-startup-id '$DEST/bin/tvwcs' toggle"
      echo "# Remote: Quick Menu (F2)"; echo "bindsym F2 exec --no-startup-id '$DEST/bin/tvwcs' toggle"; } > "$HK"
}
template_config() {   # template_config <i3|sway> <file>: the standard config with the chosen $mod and layout
    if [ "$1" = i3 ]; then
        if [ -f "$ETC/i3/config.keycodes" ]; then M="$MOD" awk '/^# WARNING/ {next} /^set \$mod / {print "set $mod " ENVIRON["M"]; next} {print}' "$ETC/i3/config.keycodes" > "$2"
        elif [ -f "$ETC/i3/config" ]; then M="$MOD" awk '/^set \$mod / {print "set $mod " ENVIRON["M"]; next} {print}' "$ETC/i3/config" > "$2"
        else warn "There is no i3 template in $ETC/i3 (is i3 installed?)."; return 1; fi
        if [ "$LAYOUT" != "$(current_layout | cut -d' ' -f1)" ] || [ -n "$VARIANT" ]; then
            { echo; echo "# Keyboard layout, chosen in TVWCS's install.sh"; echo "exec_always --no-startup-id setxkbmap -layout $LAYOUT${VARIANT:+ -variant $VARIANT}"; } >> "$2"; fi
    else
        [ -f "$ETC/sway/config" ] || { warn "There is no sway template at $ETC/sway/config (is sway installed?)."; return 1; }
        M="$MOD" awk '/^set \$mod / {print "set $mod " ENVIRON["M"]; next} {print}' "$ETC/sway/config" > "$2"
        if [ "$LAYOUT" != us ] || [ -n "$VARIANT" ]; then
            { echo; echo "# Keyboard layout, chosen in TVWCS's install.sh"; echo "input type:keyboard {"; echo "    xkb_layout $LAYOUT"
              [ -z "$VARIANT" ] || echo "    xkb_variant $VARIANT"; echo "}"; } >> "$2"; fi
    fi
}
replace_include() {
    T=$WORK/cfg; LINE=$(include_line) awk '/^[ \t]*include[ \t]/ && /tvwcs\.conf/ { if (!done) print ENVIRON["LINE"]; done = 1; next } { print }' "$1" > "$T" && cat "$T" > "$1"
}
append_include() { { echo; echo "# TVWCS (desktop mode): its hotkeys, window rules and autostart. Added by TVWCS's install.sh."; include_line; } >> "$1"; }
set_up_session_config() {   # TVWCS's own session config: the standard template plus the include line (TV mode)
    S=$(session_config "$1")
    if [ -f "$S" ]; then
        [ "$(include_state "$S")" = current ] && return 0
        keep_file "$S"
        if [ "$(include_state "$S")" = other ]; then replace_include "$S"; else { echo; include_line; } >> "$S"; fi; return 0
    fi
    mkdir -p "$TVCONF"; undo_note "delete	$S"
    T=$WORK/session.conf; template_config "$1" "$T" || return 1
    { echo "# TVWCS's own $1 session (\"TVWCS ($1)\" at the login screen): TVWCS runs here in TV mode. Written by TVWCS's"
      echo "# install.sh from the standard template; edit it as you like. Your usual $1 config is not used in this session."
      cat "$T"; echo; echo "# TVWCS: its hotkeys, window rules and autostart."; include_line; } > "$S"
    say "Created TVWCS's $1 session config, $S."
}
set_up_usual() {   # set_up_usual <wm>: the usual session, as chosen
    WM=$1; CFG=$(wm_config "$WM")
    case "$(usual_of "$WM")" in
        add) keep_file "$CFG"; cp "$CFG" "$CFG.tvwcs-backup"; append_include "$CFG"; say "Added TVWCS (desktop mode) to $CFG (backup: $CFG.tvwcs-backup)." ;;
        move) keep_file "$CFG"; cp "$CFG" "$CFG.tvwcs-backup"; replace_include "$CFG"; say "Pointed TVWCS's include line in $CFG at this install." ;;
        create|plain)
            CFG=$CONFIG_HOME/$WM/config; mkdir -p "$(dirname "$CFG")"; undo_note "delete	$CFG"
            template_config "$WM" "$CFG" || return 1
            [ "$(usual_of "$WM")" = plain ] || append_include "$CFG"
            say "Created $CFG$( [ "$(usual_of "$WM")" = create ] && echo ", with TVWCS in it (desktop mode)")." ;;
    esac
}
session_wrapper() {
    cat <<'WRAPPER'
#!/bin/sh
# TVWCS's own session: i3 or sway with TVWCS's session config (~/.config/tvwcs/<wm>-session.conf), in which TVWCS runs
# in TV mode. Written by TVWCS's install.sh. Run by the login screen's "TVWCS" entries, or from a text console:
#     startx <path to this file> i3        or        <path to this file> sway
WM=${1:-sway}
CFG=${XDG_CONFIG_HOME:-$HOME/.config}/tvwcs/$WM-session.conf
case "$WM" in i3|sway) ;; *) echo "tvwcs-session: use i3 or sway, not $WM" >&2; exit 2 ;; esac
if [ ! -f "$CFG" ]; then echo "tvwcs-session: $CFG is missing. Run TVWCS's install.sh to set up TVWCS's $WM session." >&2; exit 1; fi
TVWCS_SESSION=$WM; TVWCS_SESSION_CONFIG=$CFG; export TVWCS_SESSION TVWCS_SESSION_CONFIG
exec "$WM" -c "$CFG"
WRAPPER
}
session_entry() {
    printf '%s\n' "[Desktop Entry]" "Type=Application" "Name=TVWCS ($1)" \
        "Comment=TVWCS in TV mode: a $1 session made for a TV and a remote (added by TVWCS's install.sh)" \
        "Exec=$BINDIR/tvwcs-session $1" "TryExec=$1" "DesktopNames=$1" "Icon=$SHARE/pixmaps/tvwcs.svg"
}
entry_path() { if [ "$1" = i3 ]; then echo "$SHARE/xsessions/tvwcs-i3.desktop"; else echo "$SHARE/wayland-sessions/tvwcs-sway.desktop"; fi; }
add_login_entries() {   # the "TVWCS (i3)" / "TVWCS (sway)" sessions at the login screen, and the wrapper they run
    STAGE=$WORK/entries; mkdir -p "$STAGE"; session_wrapper > "$STAGE/tvwcs-session"
    set -- "$BINDIR/tvwcs-session" "$STAGE/tvwcs-session"
    for WM in $WMS; do session_entry "$WM" > "$STAGE/$WM.desktop"; set -- "$@" "$(entry_path "$WM")" "$STAGE/$WM.desktop"; done
    [ ! -f "$DEST/tvwcs.svg" ] || set -- "$@" "$SHARE/pixmaps/tvwcs.svg" "$DEST/tvwcs.svg"
    I=1; for A in "$@"; do [ $((I % 2)) = 1 ] && keep_root_file "$A"; I=$((I+1)); done
    as_root sh -c 'set -e; while [ $# -gt 0 ]; do mkdir -p "$(dirname "$1")"; cp "$2" "$1"; chmod 0644 "$1"; shift 2; done' sh "$@" &&
        as_root chmod 0755 "$BINDIR/tvwcs-session"
}
power_rule() {
    ME=$(id -un); RULE="$ETC/sudoers.d/zz-tvwcs-power-$(echo "$ME" | tr '.' '_')"; ALIAS=TVWCS_POWER_$(echo "$ME" | tr 'a-z.-' 'A-Z__')
    LIST=""; for P in /usr/bin/systemctl /bin/systemctl; do [ -x "$P" ] || continue; for V in suspend reboot poweroff; do LIST="$LIST${LIST:+, }$P $V"; done; done
    [ -n "$LIST" ] || return 0
    T=$WORK/sudo-rule
    printf '%s\n' "# Written by TVWCS's install.sh: lets $ME sleep, reboot and shut down from TVWCS without a password." \
        "# Delete this file to undo it." "Cmnd_Alias $ALIAS = $LIST" "$ME ALL=(root) NOPASSWD: $ALIAS" > "$T"
    as_root visudo -cf "$T" >/dev/null || { warn "The sudo rule did not pass visudo's check; it was not added."; return 0; }
    keep_root_file "$RULE"
    as_root sh -c 'mkdir -p "$(dirname "$1")" && cp "$2" "$1" && chmod 0440 "$1"' sh "$RULE" "$T" && say "Added $RULE."
}
loginscreen_root() { as_root env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$DEST" python3 -m tvwcs.loginscreen "$@"; }
default_session_id() { case " $WMS " in *" sway "*) echo tvwcs-sway ;; *) echo tvwcs-i3 ;; esac; }
set_up_login_screen() {
    LS=$(login_screen)
    case "$GREETER" in
        tvwcs)
            if [ "$LS" = tvwcs ]; then
                loginscreen_root update --config "$TVCONF/config.json" || return 1
            else
                set -- enable --config "$TVCONF/config.json" --previous "$LS" --session "$(id -un)" "$(default_session_id)"
                [ -z "$AUTOLOGIN_MOVE" ] || set -- "$@" --autologin $AUTOLOGIN_MOVE
                undo_note "loginscreen	$LS	$DEST"
                loginscreen_root "$@" || return 1
                [ -z "$AUTOLOGIN_MOVE" ] || remove_start_lines
                say "TVWCS's login screen shows from the next start, with TVWCS ($(default_session_id | cut -d- -f2)) chosen."
                LS_NEW=1; return 0
            fi
            [ -z "$AUTOLOGIN_MOVE" ] || loginscreen_root autologin $AUTOLOGIN_MOVE ;;
        sddm)
            undo_note "switch	$LS	$DEST"
            loginscreen_root switch sddm || return 1; say "SDDM is the login screen from the next start ($(login_screen_name "$LS") stays installed)."; LS_NEW=1 ;;
    esac
}
remove_start_lines() {
    F=$(profile_file); grep -qxF "$START_BEGIN" "$F" 2>/dev/null || return 0
    keep_file "$F"; cp "$F" "$F.tvwcs-backup"; T=$WORK/profile
    B="$START_BEGIN" E="$START_END" awk '$0 == ENVIRON["B"] { skip = 1 } !skip { print } $0 == ENVIRON["E"] { skip = 0 }' "$F" > "$T" && cat "$T" > "$F"
    say "Removed the lines that started the window manager on the first console from $F."
}
install_packages() {
    ALL=$(all_needed); [ -n "$ALL" ] || return 0
    if [ "$(distro)" != debian ]; then
        say "This installer can only install packages on Debian and its family. Install these yourself: $ALL"; return 0
    fi
    say "Installing:$ALL (your password may be asked for)"
    undo_note "packages	$ALL"
    root apt-get update -q || return 1
    # apt would also bring in unclutter-startup, which hides the pointer in every X session: left out ("name-")
    EXTRA=""; case " $ALL " in *" unclutter-xfixes "*) pkg_installed unclutter-startup || EXTRA=unclutter-startup- ;; esac
    # shellcheck disable=SC2086
    root env DEBIAN_FRONTEND=noninteractive apt-get install -y $ALL $EXTRA || return 1
    mkdir -p "$TVCONF"; { cat "$RECORD" 2>/dev/null; echo "$ALL" | tr ' ' '\n'; } | sort -u | sed '/^$/d' > "$RECORD.new" && mv "$RECORD.new" "$RECORD"
    case " $ALL " in *" pipewire "*) have systemctl && systemctl --user enable --now pipewire.socket pipewire-pulse.socket wireplumber.service >/dev/null 2>&1 || true ;; esac
}

# ---- upgrading from before 4.0
UPGRADE_NOTES=""
note() { UPGRADE_NOTES="$UPGRADE_NOTES$*
"; }
clean_up_old_setup() {
    [ -n "$INSTALLED" ] || return 0
    version_lt "$INSTALLED" 4.0.0 || return 0
    for F in setup where sway-login-screen; do [ ! -f "$TVCONF/$F" ] || { keep_file "$TVCONF/$F"; rm -f "$TVCONF/$F"; }; done
    # 3.x's own lock screen option rewrote xss-lock's locker in the usual i3 config: a desktop session keeps its own locker now
    CFG=$(wm_config i3)
    if [ -n "$CFG" ] && grep -q "TVWCS lock screen (Settings > Power and sleep)" "$CFG"; then
        keep_file "$CFG"
        XDG_CONFIG_HOME="$CONFIG_HOME" PYTHONPATH="$DEST" python3 -c 'import sys; from tvwcs.power import use_tvwcs_locker; sys.exit(1 if use_tvwcs_locker(sys.argv[1],"") else 0)' "$CFG" 2>/dev/null &&
            say "Put xss-lock's own locker back in $CFG."
    fi
    note "TVWCS's TV mode is now the \"TVWCS\" session at the login screen. In your usual i3 or sway session TVWCS runs in"
    note "desktop mode; to turn TVWCS off there, remove its include line from that session's config."
    for WM in i3 sway; do
        CFG=$(wm_config "$WM"); [ -n "$CFG" ] && [ "$(include_state "$CFG")" != none ] || continue
        note "  - $CFG includes TVWCS ($(include_line))."
        if [ -f "$CFG.tvwcs-backup" ]; then note "    To go back to your $WM config from before TVWCS: cp '$CFG.tvwcs-backup' '$CFG'"
        else note "    To reset it to $WM's default: cp '$ETC/$WM/config' '$CFG'"; fi
    done
    case "${TVWCS_SESSION:-}" in "") if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}${SWAYSOCK:-}${I3SOCK:-}" ]; then
        note "You are in the usual session now. Next time, log in to \"TVWCS ($(set -- $WMS; echo "${1:-i3}"))\" at the login screen for TV mode."; fi ;; esac
}

# ---- running TVWCS
user_runtime() { if [ -n "${XDG_RUNTIME_DIR:-}" ]; then echo "$XDG_RUNTIME_DIR"; elif [ -d "/run/user/$(id -u)" ]; then echo "/run/user/$(id -u)"; fi; }
running() { [ -n "$1" ] && kill -0 "$1" 2>/dev/null && { [ ! -r "/proc/$1/cmdline" ] || grep -q tvwcs "/proc/$1/cmdline"; }; }
find_running() {   # -> PID and RUNTIME of the TVWCS running for this user (PID "" when none)
    PID=""; RUNTIME=""
    for D in "$(user_runtime)" "${XDG_CACHE_HOME:-$HOME/.cache}/tvwcs"; do [ -n "$D" ] || continue
        P=$(cat "$D/tvwcs.pid" 2>/dev/null || true); if running "$P"; then PID=$P; RUNTIME=$D; return 0; fi; done
}
wm_socket() {   # wm_socket <i3|sway>: the socket of this user's running i3 / sway that answers (also from an SSH login)
    TOOL=i3-msg; [ "$1" = sway ] && TOOL=swaymsg; have "$TOOL" || return 1; R=$(user_runtime)
    if [ "$1" = sway ]; then set -- "${SWAYSOCK:-}" "${R:-/nonexistent}"/sway-ipc."$(id -u)".*.sock
    else set -- "${I3SOCK:-}" "${R:-/nonexistent}"/i3/ipc-socket.* /tmp/i3-"$(id -un)".*/ipc-socket.*; fi
    for S in "$@"; do [ -n "$S" ] && [ -S "$S" ] && "$TOOL" -s "$S" -t get_version >/dev/null 2>&1 && { echo "$S"; return 0; }; done
    return 1
}
wm_msg() {   # wm_msg <i3|sway> <args>: a command to the running i3 / sway; fails when none runs
    S=$(wm_socket "$1") || return 1; TOOL=i3-msg; [ "$1" = sway ] && TOOL=swaymsg; shift; "$TOOL" -s "$S" "$@"
}
restart_tvwcs() {
    [ -z "${TVWCS_NO_RESTART:-}" ] || return 0
    find_running; [ -n "$PID" ] || return 0
    XDG_RUNTIME_DIR="$RUNTIME" "$DEST/bin/tvwcs" stop >/dev/null 2>&1 || kill "$PID" 2>/dev/null || true
    N=0; while running "$PID" && [ $N -lt 50 ]; do sleep 0.1; N=$((N+1)); done
    if wm_msg sway -q "exec '$DEST/bin/tvwcs'" >/dev/null 2>&1 || wm_msg i3 -q "exec --no-startup-id '$DEST/bin/tvwcs'" >/dev/null 2>&1; then
        say "Restarted TVWCS with $TARGET."
    else say "TVWCS was stopped; it starts with the new version at the next log-in."; fi
}

# ====================================================================== removing TVWCS
remove_candidates() {   # the packages this installer installs (or, from before it kept a list, could have)
    if [ -s "$RECORD" ]; then cat "$RECORD"; return; fi
    printf '%s\n' python3-gi gir1.2-gtk-4.0 python3-gi-cairo sway swayidle swaylock i3 xinit xdotool x11-xserver-utils xsettingsd libxss1 i3lock \
        xsecurelock unclutter-xfixes greetd cage pipewire pipewire-pulse wireplumber pulseaudio-utils network-manager bluez gir1.2-vte-3.91 \
        udisks2 xdg-desktop-portal xdg-desktop-portal-gtk fonts-open-sans
}
removable_packages() {   # installed, marked as installed by hand, and not needed by anything else that is installed
    MANUAL=$(apt-mark showmanual 2>/dev/null || true); C=$(remove_candidates | tr '\n' ' ')
    for P in $C; do
        pkg_installed "$P" || continue
        echo "$MANUAL" | grep -qx "$P" || continue
        USERS=$(apt-cache rdepends --installed --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances "$P" 2>/dev/null |
                sed -n '3,$s/^[ |]*//p' | sort -u)
        OUTSIDE=""; for U in $USERS; do case " $C " in *" $U "*) ;; *) OUTSIDE=1 ;; esac; done
        [ -n "$OUTSIDE" ] || printf '%s ' "$P"
    done
}
remove_tvwcs() {
    heading "Removing TVWCS"
    LS=$(login_screen); TO=""
    if [ "$LS" = tvwcs ]; then
        OTHERS=$(other_login_screens); OTHERS=${OTHERS% }
        if [ -z "$OTHERS" ]; then
            say "TVWCS's login screen is the only one installed, so TVWCS cannot be removed yet: the computer would have no"
            say "way to log in. Install another login screen first (such as SDDM: sudo apt install sddm), then run this again."
            exit 1
        fi
        set -- $OTHERS
        if [ $# = 1 ]; then TO=$1; say "TVWCS's login screen is in use: the computer goes back to $(login_screen_name "$TO")."
        else say "TVWCS's login screen is in use. Which login screen should the computer use instead?"
            set --; for U in $OTHERS; do set -- "$@" "$(login_screen_name "$U")"; done; choose 1 "$@"; TO=$(echo $OTHERS | cut -d' ' -f"$CHOICE"); fi
    fi
    PKGS=""; MARK=""
    if [ "$(distro)" = debian ] && have apt-mark; then PKGS=$(removable_packages); PKGS=${PKGS% }; fi
    if [ -n "$PKGS" ]; then
        say; say "These packages were installed for TVWCS and nothing else installed needs them:"; say "  $PKGS"
        say "This script does not uninstall them. It can mark them as removable (installed automatically), so that"
        say "\"sudo apt autoremove\" uninstalls them when you run it yourself."
        ask_no "Mark them as removable?" && MARK=1
    fi
    KEEP_DATA=1
    say; ask_no "Also delete your TVWCS settings, channels and launch profiles ($TVCONF)?" && KEEP_DATA=""
    say; ask_yes "Remove TVWCS now?" || { say "Nothing was changed."; exit 0; }
    find_running; [ -z "$PID" ] || { XDG_RUNTIME_DIR="$RUNTIME" "$DEST/bin/tvwcs" stop >/dev/null 2>&1 || kill "$PID" 2>/dev/null || true; }
    if [ -n "$TO" ] || [ -d /usr/local/lib/tvwcs-greeter ]; then
        if [ "$LS" = tvwcs ]; then loginscreen_root disable --to "$TO" || { warn "Could not switch the login screen; nothing was removed."; exit 1; }; fi
    fi
    for WM in i3 sway; do
        CFG=$(wm_config "$WM"); [ -n "$CFG" ] && [ "$(include_state "$CFG")" != none ] || continue
        cp "$CFG" "$CFG.tvwcs-backup"; T=$WORK/cfg
        awk '/^# TVWCS/ { held = $0; next } /^[ \t]*include[ \t]/ && /tvwcs\.conf/ { held = ""; next } { if (held != "") print held; held = ""; print }' "$CFG" > "$T" && cat "$T" > "$CFG"
        say "Removed TVWCS from $CFG (backup: $CFG.tvwcs-backup)."
        XDG_CONFIG_HOME="$CONFIG_HOME" PYTHONPATH="$DEST" python3 -c 'import sys; from tvwcs.power import use_tvwcs_locker; use_tvwcs_locker(sys.argv[1],"")' "$CFG" 2>/dev/null || true
    done
    F=$(profile_file); if grep -qxF "$START_BEGIN" "$F" 2>/dev/null; then UNDO=/dev/null; remove_start_lines; fi
    ROOT_FILES="$BINDIR/tvwcs-session $SHARE/xsessions/tvwcs-i3.desktop $SHARE/wayland-sessions/tvwcs-sway.desktop $SHARE/pixmaps/tvwcs.svg"
    for R in "$ETC"/sudoers.d/zz-tvwcs-power-*; do [ -e "$R" ] && ROOT_FILES="$ROOT_FILES $R"; done
    grep -q TVWCS "$GETTY_OVERRIDE" 2>/dev/null && ROOT_FILES="$ROOT_FILES $GETTY_OVERRIDE"
    for R in "$ETC/lightdm/lightdm.conf.d/50-tvwcs-autologin.conf" "$ETC/sddm.conf.d/50-tvwcs-autologin.conf"; do
        grep -q 'tvwcs-' "$R" 2>/dev/null && ROOT_FILES="$ROOT_FILES $R"; done
    EXISTING=""; for R in $ROOT_FILES; do [ -e "$R" ] && EXISTING="$EXISTING $R"; done
    # shellcheck disable=SC2086
    if [ -n "$EXISTING" ] || [ -d "${TVWCS_ROOT:-}/usr/local/lib/tvwcs-greeter" ] || [ -d "$ETC/tvwcs" ]; then
        as_root rm -rf $EXISTING "${TVWCS_ROOT:-}/usr/local/lib/tvwcs-greeter" "$ETC/tvwcs" || warn "Could not remove some of TVWCS's system files:$EXISTING"
    fi
    # shellcheck disable=SC2086
    [ -z "$MARK" ] || { root apt-mark auto $PKGS >/dev/null && say "Marked as removable: $PKGS. Run \"sudo apt autoremove\" to uninstall them."; }
    rm -f "$DATA_HOME/applications/com.tvwcs.ControlPanel.desktop"
    rm -rf "$DEST"
    if [ -z "$KEEP_DATA" ]; then rm -rf "$TVCONF"; else rm -f "$TVCONF"/*-session.conf "$TVCONF/hotkeys.conf"; fi
    say; say "TVWCS is removed.$( [ -n "$KEEP_DATA" ] && echo " Your settings are kept in $TVCONF.")"
}

# ====================================================================== --missing (for the in-app updater)
list_missing() {
    WMS=""; have i3 && WMS=i3; have sway && WMS="$WMS sway"; [ -n "$WMS" ] || WMS=sway
    GREETER=keep; [ "$(login_screen)" = tvwcs ] && GREETER=tvwcs
    work_out_packages
    printf '%s' "$NEEDS" | while IFS='	' read -r LABEL PKGS; do printf 'need\t%s\t%s\n' "$PKGS" "$LABEL"; done
}

# ====================================================================== main
main() {
    case "${1:-}" in
        "") ;;
        --missing) find_package; list_missing; exit 0 ;;
        -h|--help) sed -n '2,/^set -eu/p' "$0" 2>/dev/null | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
        *) warn "install.sh: unknown option $1 (try --help)"; exit 2 ;;
    esac
    case "$DEST" in *\'*|*\"*|*"
"*) warn "install.sh: the install folder may not contain quotes or line breaks: $DEST"; exit 1 ;; esac
    WORK=$(mktemp -d); UNDO=$WORK/undo; : > "$UNDO"
    trap 'rm -rf "$WORK"' EXIT
    trap 'revert; exit 130' INT TERM
    find_tty; find_package
    if [ -z "$TTY" ] && [ -n "${SSH_CONNECTION:-}" ]; then say "There is no terminal to ask questions on. To be asked, connect with: ssh -t <computer>"; fi
    if [ "$(id -u)" = 0 ] && [ -z "${TVWCS_DEST:-}" ]; then warn "Run install.sh as the user TVWCS is for, not as root: it asks for your password when it needs it."; exit 1; fi
    [ "$(distro)" = debian ] || say "Note: this installer can only install packages on Debian and its family; on this system, install them yourself."

    choose_version
    if [ "$ACTION" = remove ]; then remove_tvwcs; exit 0; fi
    if [ -n "$WANT" ] && version_lt "$WANT" 4.0.0; then   # an earlier version has its own installer and questions
        download_release "$WANT" || fail "TVWCS $WANT could not be downloaded."
        say "TVWCS $WANT has an installer of its own; it asks its own questions now."
        exec sh "$SRC/install.sh" < "${TTY:-/dev/null}"
    fi
    choose_wms
    choose_login_screen
    choose_usual
    choose_keys
    choose_extras
    [ -n "$WMS" ] || say "Neither i3 nor sway is set up; run install.sh in a terminal to choose one."
    work_out_packages

    heading "Ready to install TVWCS $TARGET"
    if [ -n "$NEEDS" ]; then say "These packages will be installed:"; show_needs; fi
    for WM in $WMS; do say "  TVWCS ($WM) session at the login screen (TV mode)$( [ -f "$(session_config "$WM")" ] && echo ", already set up")"
        case "$(usual_of "$WM")" in add|create|keep|move) say "  TVWCS in your usual $WM session (desktop mode)" ;; esac; done
    case "$GREETER" in tvwcs) [ "$(login_screen)" = tvwcs ] && say "  TVWCS's login screen, brought up to date" || say "  TVWCS's login screen" ;; sddm) say "  SDDM as the login screen" ;; esac
    if [ -n "$TTY" ]; then ask_yes "Go ahead?" || { say "Nothing was changed."; exit 0; }; fi

    # ---- from here on, things change; a failure undoes them
    [ -z "$WANT" ] || download_release "$WANT" || fail "TVWCS $WANT could not be downloaded."
    if [ -n "$TTY" ] && [ -n "$NEEDS" ]; then install_packages || fail "the packages could not be installed."; fi
    copy_program || fail "the program could not be copied to $DEST."
    add_launcher
    default_hotkeys
    clean_up_old_setup
    for WM in $WMS; do
        have "$WM" || [ -f "$(session_config "$WM")" ] || [ -f "$ETC/$WM/config" ] || [ -f "$ETC/$WM/config.keycodes" ] || continue
        set_up_session_config "$WM" || fail "TVWCS's $WM session could not be set up."
        set_up_usual "$WM" || fail "the usual $WM config could not be set up."
    done
    if [ -z "$TTY" ] && [ -n "$WMS" ]; then
        for WM in $WMS; do [ -f "$(entry_path "$WM")" ] || note "Run install.sh in a terminal once to add TVWCS's $WM session to the login screen."; done
    fi
    if [ -n "$TTY" ] && [ -n "$WMS" ]; then
        add_login_entries || fail "TVWCS's sessions could not be added to the login screen."
        LS_NEW=""; set_up_login_screen || fail "the login screen could not be set up."
        [ -z "$POWER_RULE" ] || power_rule
        [ -z "$UNCLUTTER_OFF" ] || as_root sed -i 's/^[[:space:]]*START_UNCLUTTER=.*/START_UNCLUTTER="false"/' "$ETC/default/unclutter" || true
    fi
    : > "$UNDO"   # done: nothing to undo any more
    for WM in $WMS; do case "$(usual_of "$WM")" in add|move|create)
        wm_msg "$WM" -q reload >/dev/null 2>&1 && say "Reloaded $WM." || true ;; esac; done
    restart_tvwcs

    say; say "TVWCS $TARGET is installed in $DEST."
    [ -z "$UPGRADE_NOTES" ] || { say; printf '%s' "$UPGRADE_NOTES"; }
    if [ -n "$TTY" ] && [ -n "$WMS" ]; then
        say "To use it in TV mode, choose \"TVWCS ($(set -- $WMS; [ $# = 2 ] && echo sway || echo "$1"))\" at the login screen."
        if [ -n "${LS_NEW:-}" ] && [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && ! wm_socket i3 >/dev/null && ! wm_socket sway >/dev/null && [ "$(init_system)" = systemd ]; then
            if ask_yes "Show the login screen now?"; then
                U=greetd; [ "$GREETER" = sddm ] && U=sddm
                root systemctl start "$U.service" || say "It shows at the next start."
            fi
        fi
    fi
}

main "$@"
