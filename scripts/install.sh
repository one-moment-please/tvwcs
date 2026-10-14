#!/bin/sh
# Installs TVWCS into ~/.local/share/tvwcs (the program; your data stays in ~/.config/tvwcs) and sets up the
# window manager: it offers to add TVWCS's include line to your i3 and/or sway config, moves an install from the
# old location (~/.config/i3/tvwcs) over, and can create a config from the standard template if you have none.
# Every change to a window manager config is asked first, and the file is backed up as <config>.tvwcs-backup.
# Safe to re-run to upgrade; your settings in ~/.config/tvwcs are untouched.
#
# Environment: TVWCS_DEST=<folder> installs somewhere else. TVWCS_ASSUME_YES=1 answers yes to adding or updating
# the include line and removing the old copy (for scripted installs). TVWCS_MIGRATE=1 answers yes only to moving
# from the old location: updating the include line and removing the old copy (the in-app updater sets it once you
# have agreed to the move there).
# TVWCS_NO_RESTART=1 skips the offer to restart a running TVWCS. TVWCS_WMS="i3 sway" chooses which window managers
# to set up (default: those installed). TVWCS_ETC overrides /etc (where the standard config templates are).
set -eu
RUN_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)  # folder holding this script (repo scripts/, or a release root)

# Work out the source layout: repository (script lives in scripts/) vs. release/installed (script at the root).
if [ -d "$RUN_DIR/../package/tvwcs" ]; then
    SRC=$(CDPATH= cd -- "$RUN_DIR/.." && pwd)          # repository root
    PKG=$SRC/package/tvwcs; BIN=$SRC/package/bin/tvwcs; CONF=$SRC/data/tvwcs.conf; DOCS=$SRC
elif [ -d "$RUN_DIR/tvwcs" ]; then
    SRC=$RUN_DIR                                        # release zip or already-installed folder
    PKG=$SRC/tvwcs; BIN=$SRC/bin/tvwcs; CONF=$SRC/tvwcs.conf; DOCS=$SRC
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
case "$DEST" in
    *\'*|*\"*|*"
"*) echo "install.sh: the install folder may not contain quotes or line breaks: $DEST" >&2; exit 1 ;;
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
    for MD in README.md CHANGELOG.md PROJECT_OVERVIEW.md LICENSE; do [ -f "$DOCS/$MD" ] && cp "$DOCS/$MD" "$DEST/"; done
    chmod +x "$DEST/bin/tvwcs"
}

if [ "$SRC" = "$DEST" ]; then
    echo "TVWCS is already installed in $DEST — nothing to copy. Re-running install.sh from that folder just re-checks your setup."
else
    install_files
fi
VERSION=$(cat "$SRC/VERSION" 2>/dev/null || echo "?")
echo "TVWCS $VERSION installed in $DEST"

# An install in the old location is moved over: its hand-edited fragment backup comes along, and the hotkeys
# (which run its launcher by full path) are pointed at the new one.
MIGRATING=""
if [ "$LEGACY" != "$DEST" ] && [ -f "$LEGACY/bin/tvwcs" ]; then
    MIGRATING=1
    echo "Found an older TVWCS in $LEGACY; moving it to $DEST."
    if [ -f "$LEGACY/tvwcs.conf.bak" ] && [ ! -f "$DEST/tvwcs.conf.bak" ]; then cp "$LEGACY/tvwcs.conf.bak" "$DEST/"; fi
fi

# Hotkeys live with your data, not with the program, so upgrades never reset them. TVWCS rewrites this file when
# you change a hotkey in Settings; here we only make sure it exists with the defaults so the include has a target.
HK="$CONFIG_HOME/tvwcs/hotkeys.conf"
if [ ! -f "$HK" ]; then
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
# distro -> the family whose package manager and names apply, from /etc/os-release (ID, then ID_LIKE)
distro() {
    ( if [ -r "$ETC/os-release" ]; then . "$ETC/os-release"; elif [ -r /usr/lib/os-release ]; then . /usr/lib/os-release; fi; for D in ${ID:-} ${ID_LIKE:-}; do
        case "$D" in
            arch|artix|manjaro|endeavouros) echo arch; exit ;;
            fedora|rhel|centos|rocky|almalinux|nobara) echo fedora; exit ;;
            opensuse*|suse|sles) echo suse; exit ;;
            void) echo void; exit ;;
            alpine) echo alpine; exit ;;
            gentoo) echo gentoo; exit ;;
            debian|ubuntu|linuxmint|devuan|pop|raspbian) echo debian; exit ;;
        esac
    done; echo unknown )
}
# pkg <need>: that need's package name here (gtk = GTK 4 and PyGObject)
pkg() {
    case "$(distro):$1" in
        debian:gtk) echo "python3-gi gir1.2-gtk-4.0" ;;      debian:i3) echo i3 ;;
        arch:gtk) echo "python-gobject gtk4" ;;              arch:i3) echo i3-wm ;;
        fedora:gtk|suse:gtk) echo "python3-gobject gtk4" ;;  void:gtk) echo "python3-gobject gtk4" ;;
        alpine:gtk) echo "py3-gobject3 gtk4.0" ;;            alpine:i3) echo i3wm ;;
        gentoo:gtk) echo "dev-python/pygobject gui-libs/gtk" ;;
        gentoo:i3) echo x11-wm/i3 ;;                         gentoo:xdotool) echo x11-misc/xdotool ;;
        *:gtk) echo "PyGObject GTK4" ;;                      *) echo "$1" ;;
    esac
}
install_hint() {
    case "$(distro)" in
        debian) echo "sudo apt install $1" ;;   arch) echo "sudo pacman -S $1" ;;   fedora) echo "sudo dnf install $1" ;;
        suse) echo "sudo zypper install $1" ;;  void) echo "sudo xbps-install $1" ;; alpine) echo "doas apk add $1" ;;
        gentoo) echo "sudo emerge $1" ;;        *) echo "install with your package manager: $1" ;;
    esac
}
missing=""
python3 -c 'import gi; gi.require_version("Gtk","4.0")' 2>/dev/null || missing="$missing $(pkg gtk)"
command -v i3 >/dev/null 2>&1 || command -v sway >/dev/null 2>&1 || missing="$missing $(pkg i3)"
command -v sway >/dev/null 2>&1 || command -v xdotool >/dev/null 2>&1 || missing="$missing $(pkg xdotool)"
[ -z "$missing" ] || echo "Missing packages:  $(install_hint "${missing# }")"

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

CHANGED_WMS=""
include_in() {   # include_in <wm> <config>: add or update the include line (after asking)
    WM=$1; CFG=$2
    case $(include_state "$CFG") in
        current) echo "Your $WM config ($CFG) already includes TVWCS." ;;
        other)
            if ask "Your $WM config ($CFG) includes TVWCS from its old location. Update it to $INCLUDE_PATH?" migrate; then
                backup "$CFG"; TMP=$(mktemp)
                LINE="$INCLUDE_LINE" awk '/^[ \t]*include[ \t]/ && /tvwcs\.conf/ { if (!done) print ENVIRON["LINE"]; done = 1; next } { print }' "$CFG" > "$TMP"
                cat "$TMP" > "$CFG"; rm -f "$TMP"
                echo "Updated the include line in $CFG (backup: $CFG.tvwcs-backup)."; CHANGED_WMS="$CHANGED_WMS $WM"
            else
                echo "Left $CFG unchanged. Change its TVWCS include line to:"; echo "    $INCLUDE_LINE"
            fi ;;
        none)
            if ask "Add TVWCS to your $WM config ($CFG)? This appends one include line."; then
                backup "$CFG"
                { echo; echo "# TVWCS: its window rules, hotkeys and autostart. Added by TVWCS's install.sh."; echo "$INCLUDE_LINE"; } >> "$CFG"
                echo "Added the include line to $CFG (backup: $CFG.tvwcs-backup)."; CHANGED_WMS="$CHANGED_WMS $WM"
            else
                echo "Left $CFG unchanged. To use TVWCS, add this line to it and reload $WM:"; echo "    $INCLUDE_LINE"
            fi ;;
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
    if [ -z "$L" ]; then   # Arch, Fedora and the rest write the X keyboard settings here (localectl too, without systemd by hand)
        for F in "$ETC"/X11/xorg.conf.d/*keyboard*.conf; do
            [ -f "$F" ] || continue
            L=$(awk 'tolower($0) ~ /option[ \t]+"xkblayout"/ { gsub(/"/, ""); print $3; exit }' "$F")
            V=$(awk 'tolower($0) ~ /option[ \t]+"xkbvariant"/ { gsub(/"/, ""); print $3; exit }' "$F")
            [ -n "$L" ] && break
        done
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
choose_keys() {   # asked once, shared by i3 and sway
    [ -n "$MOD" ] && return
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

create_i3_config() {
    CFG="$CONFIG_HOME/i3/config"; mkdir -p "$(dirname "$CFG")"
    WIZ_MOD=win; [ "$MOD" = Mod1 ] && WIZ_MOD=alt
    # The standard way: i3-config-wizard writes the default config with key names from the current keyboard
    # layout. It reads the live keymap, so it is only used for the current layout and with a display.
    if [ -n "$LAYOUT_IS_CURRENT" ] && [ -n "${DISPLAY:-}" ] && command -v i3-config-wizard >/dev/null 2>&1; then
        XDG_CONFIG_HOME="$CONFIG_HOME" i3-config-wizard -m "$WIZ_MOD" >/dev/null 2>&1 || true   # fails afterwards when i3 is not running
    fi
    if [ ! -s "$CFG" ]; then
        if [ -f "$ETC/i3/config.keycodes" ]; then keycode_config "$ETC/i3/config.keycodes" "$MOD" > "$CFG"
        elif [ -f "$ETC/i3/config" ]; then M="$MOD" awk '{gsub(/Mod1/, ENVIRON["M"]); print}' "$ETC/i3/config" > "$CFG"
        else echo "No i3 template found in $ETC/i3 (is i3 installed?); no config created." >&2; return 1; fi
    fi
    if [ -z "$LAYOUT_IS_CURRENT" ]; then
        { echo; echo "# Keyboard layout, chosen when TVWCS's install.sh created this file"
          echo "exec_always --no-startup-id setxkbmap -layout $LAYOUT${VARIANT:+ -variant $VARIANT}"; } >> "$CFG"
    fi
    echo "Created $CFG from the standard i3 template (\$mod = $( [ "$MOD" = Mod4 ] && echo Super || echo Alt ))."
}

create_sway_config() {
    CFG="$CONFIG_HOME/sway/config"; mkdir -p "$(dirname "$CFG")"
    [ -f "$ETC/sway/config" ] || { echo "No sway template found at $ETC/sway/config (is sway installed?); no config created." >&2; return 1; }
    M="$MOD" awk '/^set \$mod / {print "set $mod " ENVIRON["M"]; next} {print}' "$ETC/sway/config" > "$CFG"
    # sway does not take the layout from X: it uses "us" unless told otherwise, so any other layout is written down.
    if [ "$LAYOUT" != us ] || [ -n "$VARIANT" ]; then
        { echo; echo "# Keyboard layout, chosen when TVWCS's install.sh created this file"
          echo "input type:keyboard {"; echo "    xkb_layout $LAYOUT"; [ -n "$VARIANT" ] && echo "    xkb_variant $VARIANT"; echo "}"; } >> "$CFG"
    fi
    echo "Created $CFG from the standard sway template (\$mod = $( [ "$MOD" = Mod4 ] && echo Super || echo Alt ))."
}

setup_wm() {   # setup_wm <i3|sway>
    WM=$1; CFG=$(wm_config "$WM")
    if [ -n "$CFG" ]; then include_in "$WM" "$CFG"; return; fi
    if [ -t 0 ] && ask "There is no $WM config yet. Create one from the standard template?"; then
        choose_keys
        if create_${WM}_config; then include_in "$WM" "$(wm_config "$WM")"; return; fi
    fi
    echo "No $WM config found. Once you have one, add this line to it and reload $WM:"; echo "    $INCLUDE_LINE"
}

echo
WMS=${TVWCS_WMS:-}
if [ -z "$WMS" ]; then
    command -v i3 >/dev/null 2>&1 && WMS="i3"
    command -v sway >/dev/null 2>&1 && WMS="$WMS sway"
    [ -n "$WMS" ] || WMS="i3"   # nothing installed yet: still say what to add once it is
fi
for WM in $WMS; do setup_wm "$WM"; done

# A window manager that is running reloads its changed config, so TVWCS's hotkeys work straight away.
for WM in $CHANGED_WMS; do
    if [ "$WM" = i3 ] && [ -z "${SWAYSOCK:-}" ] && command -v i3-msg >/dev/null 2>&1 && i3-msg -t get_version >/dev/null 2>&1; then
        i3-msg -q reload && echo "Reloaded i3."
    elif [ "$WM" = sway ] && [ -n "${SWAYSOCK:-}" ] && command -v swaymsg >/dev/null 2>&1; then
        swaymsg -q reload && echo "Reloaded sway."
    fi
done

# ------------------------------------------------------------------ restart a running TVWCS
# A running TVWCS keeps using the old program until it is restarted. Offer to do that now. The in-app updater sets
# TVWCS_NO_RESTART because it restarts TVWCS itself; without a terminal to ask in, only say what to do.
PIDFILE="${XDG_RUNTIME_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/tvwcs}/tvwcs.pid"   # the same rule as tvwcs/session.py
PID=$(cat "$PIDFILE" 2>/dev/null || true)
running() { [ -n "$1" ] && kill -0 "$1" 2>/dev/null && { [ ! -r "/proc/$1/cmdline" ] || grep -q tvwcs "/proc/$1/cmdline"; }; }
start_tvwcs() {
    # Start it the way the window manager does (so it gets its environment), or detached from this terminal.
    if [ -n "${SWAYSOCK:-}" ] && command -v swaymsg >/dev/null 2>&1; then
        swaymsg -q "exec '$DEST/bin/tvwcs'"
    elif command -v i3-msg >/dev/null 2>&1 && i3-msg -t get_version >/dev/null 2>&1; then
        i3-msg -q "exec --no-startup-id '$DEST/bin/tvwcs'"
    else
        setsid nohup "$DEST/bin/tvwcs" >/dev/null 2>&1 < /dev/null &
    fi
}
restart_tvwcs() {
    "$DEST/bin/tvwcs" stop >/dev/null 2>&1 || true
    n=0; while running "$PID" && [ $n -lt 50 ]; do sleep 0.1; n=$((n+1)); done
    if running "$PID"; then echo "TVWCS did not stop; restart it yourself (or log in again) to load the new version." >&2; return; fi
    start_tvwcs
    n=0; while [ $n -lt 50 ]; do
        NEW=$(cat "$PIDFILE" 2>/dev/null || true)
        if [ "$NEW" != "$PID" ] && running "$NEW"; then echo "TVWCS restarted with version $VERSION."; return; fi
        sleep 0.1; n=$((n+1))
    done
    echo "TVWCS was stopped but did not come back; start it with: $DEST/bin/tvwcs" >&2
}
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
