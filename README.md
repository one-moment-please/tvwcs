# TVWCS — TV Window Channel Switcher

TVWCS is a lightweight, remote-friendly application launcher and window switcher designed to make a Linux PC easy to use from a television. It provides a TV-style interface for launching and switching between applications using a remote control, gamepad, or keyboard.

## How To Install And Use

TVWCS is written in python and can be extracted to any folder, and just needs the dependencies installed and for an include to be added to ~/.config/i3/config that points to the tvwcs.conf file in the folder. a install.sh file is included that will move the files to ~/.config/i3/tvwcs and check if the include has been added to the i3 config file. The dependencies are Python, GTK 4, and i3. On Linux Mint or Debian/Ubuntu, you can install the main requirements with:
```
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-4.0 i3-wm xdotool
```
After installation TVWCS can be launched by pressing F2. F2 was chosen as that is a button used on my USB remote, and I'm still troubleshooting reliability problems with setting the windows key to launch tvwcs without breaking all shortcuts.
TVWCS will by default open a quick menu that lets you search through all installed applications, view and manage open windows, and launch favorites. openign the guide will list all applications and allow you to assign a number code to them (useful if say you have a remote with a number pad), or create secondary profiles for the apps where you have set launch options for them. There is also a settings window that contains behavior options or other configurations such as window scaling, hotkey config, you can set any app to open at login, or you can sleep or shut down the computer.


## How It Works

TVWCS runs on top of an existing Linux desktop environment and uses **i3** for window management and **GTK** for its interface. It does not replace the underlying operating system or require application-specific plugins.

- **Guide:** Browse installed applications organized into expandable categories. Assign channel numbers, mark favorites, and create additional launch profiles.
- **Launch Profiles:** Configure alternative ways to launch an application, including available actions defined by its `.desktop` file and custom launch commands.
- **Quick Menu:** Quickly access favorites, search for applications, switch to open windows, and manage running applications.
- **Window Management:** Launch applications in a TV-friendly, exclusive-window mode by default, or configure a profile to display alongside other windows.
- **Remote Navigation:** Use directional controls to navigate the interface, with keyboard shortcuts to open the Guide and Quick Menu.

TVWCS discovers applications through standard Linux `.desktop` entries, allowing it to work with a wide range of desktop applications without requiring dedicated integrations.

## Project Goals

TVWCS aims to provide a simple, lightweight, and customizable foundation for a Linux home-theater PC. The long-term vision is to make a conventional Linux computer feel more like a television platform while retaining the flexibility of a desktop operating system.

## License

TVWCS is intended to be distributed under the MIT License. See the `LICENSE` file for details.

## Project Notes:
 - This project consists primarily of AI generated code where an AI was given a description of the project to make and then repeatedly given a list of revisions to remake the project to.
 - This project is not distributed with any code of conduct.9O9nuxk8
 - 
 - This project is free to copy, steal, plagiarize, mimic, reference, etc. 
