# TVWCS: Project goals and intended behavior

*Updated for Phase 2.5.*

## A short introduction

**TVWCS stands for TV Window Channel Switcher.** It is a lightweight, TV-style interface for using an ordinary Linux computer from the couch. It aims to make the computer feel more like a television or set-top box: browse a guide, assign channel numbers to things you use, pin favorites, search by name, and switch between applications that are already open.

TVWCS does not replace Linux, the desktop, or the applications. It is a remote-friendly launcher and application switcher that sits on top of the existing desktop (i3 today, sway later). It should work with normal Linux applications without requiring each application to ship a TVWCS-specific plugin.

## The problem it solves

A standard desktop assumes the user is sitting close to a monitor with a mouse and keyboard. On a television across the room, small controls, taskbars, window lists, and app launchers are awkward. Media-center applications can solve some of this, but often require plugins or special integrations for each service. TVWCS takes a different approach: keep the flexibility of a general-purpose Linux computer, and add a consistent couch-friendly way to find, launch, and return to applications.

## Design language: Metro / Modern UI

The interface follows the Windows Metro (Modern UI) language: flat, typographic and content-first.

- **Square everything.** Buttons, fields, dialogs and popovers have sharp 90° corners; there are no gradients, shadows or rounded shapes.
- **Solid colour blocks.** Dark neutral surfaces, one accent colour (configurable, default blue), light-weight large type, small spaced capitals for section titles.
- **Focus is unmistakable from across the room.** The focused item becomes a solid accent block with a white frame and bold text. Danger actions focus red.
- **Real icons.** Application logos appear wherever an app is listed; a coloured letter tile stands in when no icon exists. Window rows can carry a badge (an unread count or an urgent marker).
- **Symbols over words where the meaning is universal** (power, close, lock, refresh, settings); words where it is not (Guide, Edit).
- **Scales to the room.** The whole interface (type, icons, spacing, panel widths) scales for a desktop monitor, a 1080p TV across the room, or a 4K TV.

## The central user experience

### 1. The screen layout: two panels

TVWCS is one borderless panel placed in the usable area of the active workspace, that is, the workspace on the monitor under the pointer, excluding the bar. It is made of up to two panels, left to right:

- **The Quick Menu** is a full-height column at the **left**, with a small margin above, below and to its left. It is always present.
- **The Applications pane** opens **alongside** it and fills the rest. It always opens on the applications guide; a button at its **top right** switches it between the guide and **Settings**.

Every panel keeps the **same margin** from the screen edges and from its neighbours. The Quick Menu can be open on its own; the Applications pane always has the Quick Menu with it.

The first hotkey shows or hides the Quick Menu; the second opens the Applications pane beside it (and closes it again). Navigation is spatial: **Right** past the last control of the Quick Menu opens the Applications pane; **Left** goes back, and **Esc** (or the remote's **Back** key) steps back one level: dialog, Settings, Applications, Quick Menu. With *Button hints* turned on in Settings (off by default), a button with only an icon shows its tooltip after it has been selected for 3 seconds, for 6 seconds, so a remote gets the same hints as a mouse. Typing any text, anywhere, goes straight into the search field.

### 2. The Quick Menu

From top to bottom:

- **Header:** the Guide toggle and Close.
- **Universal search:** profiles, application names, custom commands, channel numbers and open windows in one field. Just type; no need to select it first. Typing a channel number and pressing Enter activates that channel.
- **Open applications, organised by workspace.** TVWCS treats a workspace, not a window, as the unit you "change channel" between. An application alone on its workspace is listed as that application. Applications that share a workspace are grouped into one workspace entry, **named after what is in it** ("Brave + Text Editor"), with their logos and any badges.
- **Favorites**, pinned launch profiles, listed below the open applications.

Each row mirrors the Guide: in the Guide the application is on the left and its controls on the right; in the Quick Menu the application is on the right and a single **options button** (☰) on the left, or **Left** on the remote while the application is selected, expands the row's options in place. They fold away again as soon as the selection moves off them:

- **An application:** open it the other way (tiled in the current workspace, or in a workspace of its own), its `.desktop` actions, and Close.
- **A workspace:** move it to another monitor (the option only exists when there is another monitor, and then offers a choice of which), expand it into its individual apps (to open just one, or reach that app's own options), and close the workspace and every app on it (after a confirmation).
- **A favorite:** its launch-mode icon (see below) and `.desktop` actions.

### 3. Settings

Settings shares the Applications pane with the guide (switched with the button at its top right) and holds everything that is about TVWCS itself rather than about launching something. Every row is one button, so it works with a D-pad alone. See "Settings" below.

### 4. The Channel Guide

The Guide is the main browseable catalogue. It discovers installed graphical applications from standard Linux XDG `.desktop` entries and groups them into foldable categories such as Media, Internet, Games, Office, Graphics, Development, Utilities, System, and Other. Each row shows the application's logo, channel, name and, less prominently, its description. At its top is the user's own channel lineup: any launch profile can be given a number and the numbered profiles are shown together. The Guide imposes no fixed lineup. Unassigned apps remain browsable by category.

A **secondary profile** (a second way to start the same application) is shown under its application with a **↳** where the logo would be, and instead of the application's description it lists what makes it different: the chosen `.desktop` action and any custom launch command (or a description the owner wrote). A lock mark shows a PIN-protected profile. The Guide never jumps or collapses because of an edit such as favoriting.

### 5. Launch profiles

An application is the installed program; a launch profile is one particular way to start it. One browser might have profiles for a streaming website, a private session, or a kiosk mode. A profile has a human-readable name, an optional custom command, an optional `.desktop` action, an optional channel, a favorite state, a **launch mode**, an optional description, and an optional **PIN**.

If the command is empty, TVWCS uses the application's standard desktop launcher. If a custom command is entered, TVWCS starts it as an argument list rather than a shell script, which keeps the behavior understandable and avoids silently interpreting shell operators.

**PIN protection.** Any profile can be protected by a PIN of its own, for example to keep a child out of a browser profile on a shared TV. The owner chooses when it is asked: only when launching, or also when showing the app if it is open on a workspace that is not on screen. The PIN is entered on an on-screen keypad that works with a D-pad. It is a convenience lock, not strong security, and editing or deleting a protected profile needs its PIN too.

**Descriptions.** The description beside a profile defaults to its application's `.desktop` description (main profile) or to its launch options (secondary profile), and either can be overridden from the edit pages.

### 6. Where an app opens: launch modes

Every profile has one of two launch modes:

- **Tiled in the current workspace** (the default): the app opens beside whatever is already showing.
- **Always in a new workspace:** the app opens alone on a fresh workspace. Everything else stays on its own workspace and is simply not displayed, so nothing is moved, closed or minimized.

The mode is chosen in the profile's **edit page**, and can be flipped from the icon beside a favorite. Separately, a **Settings toggle governs selecting apps that are already running**: with it on, selecting an open app gives it a workspace of its own; with it off, the app is tiled into the current workspace. Either way, an app's options offer the opposite for that one time, and an app individually set to always launch in a new workspace is unaffected by the toggle.

### 7. Workspaces as units

A workspace holding two or more applications is a working set (for example, a video call plus notes). It is listed under Open applications as one entry named for its contents, and selecting it **opens the whole workspace** on the monitor the user is looking at. Its options can send the whole workspace to another monitor, expand it into its apps, or close it with everything on it.

### 8. Channels and favorites

Channel numbers are assigned by the user and stored locally. A number is a shortcut to a profile, not an application category and not a global standard. Numbers are unique within the user's configuration and a profile can have none. Favorites are independent: a favorite does not need a channel, and a channel does not have to be a favorite.

### 9. Switching between open applications


TVWCS prefers focusing an existing window over starting another copy when it can identify a match. The window manager remains responsible for windows, focus, and workspaces; TVWCS issues requests through i3 and does not implement its own window management.

Application identity is imperfect across Linux apps. Matching uses the window class, instance, the `.desktop` file's `StartupWMClass`, and names, and is therefore best-effort. The same matching drives logos, badges and launch modes on open windows.

## Settings

- **Interface size:** Desktop, 10-foot (1080p TV) or 10-foot (4K TV), chosen from a small pop-up list.
- **Close when clicking outside** TVWCS.
- **Open running apps in a new workspace** (the toggle described under launch modes).
- **Hotkeys:** which keys show the Quick Menu and the Guide. A modifier tapped on its own (such as Super) can be used; it is delivered only when pressed and released alone, so Super+Enter and every other Super shortcut keep working.
- **At login:** open a chosen app (favorites listed first, then apps with channel numbers), or reopen the last app used, once per login.
- **Check for updates:** asks GitHub for the latest published release; if it is newer, offers to download it, install it over the current copy (keeping the user's data), remove the download and restart TVWCS.
- **System:** Lock, Refresh applications, Sleep, Log out, Reboot, Shut down. Log out, Reboot and Shut down always ask for confirmation first; the safe choice (Cancel) is pre-selected, and Esc backs out.

## What TVWCS is, and is not

**It is:**
- A lightweight TV-style guide and launcher with a Metro look.
- A universal place to search for apps and profiles.
- A user-configurable channel lineup and a favorites list.
- A workspace and open-window switcher.
- A layer above Linux that uses standard desktop application metadata.
- Designed first for i3 and ordinary keyboard-like remote input.

**It is not:**
- A replacement operating system or window manager.
- A media server or player like Jellyfin, Emby, Kodi, or VLC.
- A promise that every app will become fully controllable with a D-pad.
- A system requiring a custom plugin for every streaming site or app.
- A fixed, centrally maintained channel list.
- A finished sway implementation (log-out and lock detect sway; window, workspace and hotkey control is i3 only for now).

## Technical direction

The target is Linux Mint/Debian/Ubuntu with i3. GTK 4 supplies the interface and the Metro theme (one CSS block). The application catalogue comes from XDG desktop entries. i3's IPC, exposed by `i3-msg`, enumerates windows and workspaces, reports each monitor's usable rectangle, switches and moves workspaces, and positions the TVWCS panel. TVWCS does not read raw evdev devices; a remote that behaves like a keyboard works through the normal Linux input path.

The code is divided into small modules so the logic can be tested without a display: `model` (profiles, settings, layout maths, badges, search), `applications` (discovery, window-to-app matching), `workspaces` (workspace entries and names), `hotkeys` (hotkey specs and the i3 config they produce), `pinlock` (PIN hashing and try limits), `ownership` (which profile launched which window), `window_manager` (i3 adapter, with a clear boundary for a future sway adapter) and `system_actions`; and, for the GTK interface, `widgets`, `theme`, `ui_window`, `ui_settings`, `ui_editors` and `main`.

### Where things live

| What | Where |
|---|---|
| The program | `~/.config/i3/tvwcs/` (recommended) |
| i3 integration | `~/.config/i3/tvwcs/tvwcs.conf` |
| The user's data and settings | `~/.config/tvwcs/config.json` |
| Hotkeys, written by Settings | `~/.config/tvwcs/hotkeys.conf` |

The i3 config gains a single line, `include ~/.config/i3/tvwcs/tvwcs.conf`. That file starts TVWCS, includes the generated hotkeys file, and sets the window rules (floating, borderless panel; centered dialogs). Because the usable area differs per monitor and bar, TVWCS computes the panel's exact position and size at run time; the margin and Quick Menu width are settings in `config.json`. The user's data is kept apart from the program so that upgrading never touches channels, favorites or hotkeys. TVWCS recognises its own windows by an exact title (`TVWCS`) or a distinctive prefix (`TVWCS · `), never by a prefix an ordinary document name could share.

## Phase 2.5 deliverables

1. Launch-as-another-user removed (a custom launch command covers it).
2. Per-profile PIN protection with a D-pad keypad, scoped to launching only or to launching and showing.
3. Description overrides on the application page and on secondary-profile editors.
4. Settings choices open as a small pop-up list; the login-app chooser lists favorites, then channels, then the rest.
5. The remote's Back key (XF86Back) acts as Esc everywhere in TVWCS.
6. Everything from Phase 2.4: spatial three-panel navigation, type-to-search, workspace-centric Open applications, Settings (interface size, close on outside click, hotkeys, login app, system actions), the missing-apps fix, Metro theme, equal-margin layout, launch modes, logos and badges, installation under `~/.config/i3/tvwcs`.

## What success looks like

A person on a couch presses a remote button and a clean, square, high-contrast menu slides in at the left of the screen, sized for the room. They see their open workspaces ("Brave + Text Editor", "Messages") above their favorites, see that the messaging app has three unread items, and jump to it. They press Right and the full catalogue opens beside it, still framed by the same margins; they find a game, which opens alone on its own workspace, while the video call and notes they had open stay together on another workspace, one selection away. The button at the top right of that pane opens Settings, where they change the hotkey to the Super key without losing Super+Enter. They never touch a mouse, no application needed a plugin, and a stray press on Shut down asks "Are you sure?" first.

## A concise explanation to say aloud

> TVWCS stands for TV Window Channel Switcher. It is a lightweight, Metro-styled, TV-like interface for a Linux computer connected to a television. A menu on the left of the screen gives you your favorites, your open apps and open workspaces, and search; a full guide can open beside it. You can assign your own channel numbers, and choose whether each app opens tiled with what you have or alone on its own workspace. It does not replace Linux or apps like Jellyfin and Steam. It sits above the existing desktop and provides a remote-friendly way to control it, without needing a plugin for every app.

## One-sentence mission

**Make a Linux computer as easy to browse and control from the couch as a television, without taking control away from Linux or its applications.**
