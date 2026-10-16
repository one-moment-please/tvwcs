# Setting up a TV computer with Debian

This guide takes an empty computer to one that starts straight into TVWCS. You install Debian without a desktop, turn on SSH, and then install TVWCS from another computer. The TV computer needs a keyboard only for the first steps.

**You need:**
- the TV computer (64-bit PC, "amd64"), on your network, by cable if you can
- a USB stick of 1 GB or more (it will be erased)
- another computer on the same network (Windows 10 or 11, macOS or Linux)
- a keyboard for the TV computer, for the first steps

## 1. Write Debian to the USB stick

1. On the other computer, download the **amd64** network install image from <https://www.debian.org/distrib/netinst> (`debian-<version>-amd64-netinst.iso`, about 700 MB).
2. Write it to the stick:
   - **Windows:** [Rufus](https://rufus.ie) (choose the stick and the ISO, then **Start**; pick **DD image mode** if asked) or [balenaEtcher](https://etcher.balena.io).
   - **macOS:** balenaEtcher.
   - **Linux:** balenaEtcher, or `sudo dd if=debian-*-netinst.iso of=/dev/sdX bs=4M status=progress conv=fsync`. `/dev/sdX` is the whole stick, not a partition; `lsblk` lists drives. Everything on it is lost.

## 2. Install Debian without a desktop

1. Start the TV computer from the stick. The boot menu key is usually **F12**, **F11**, **F8** or **Esc**. You can leave Secure Boot on.
2. Choose **Graphical install** (or **Install**) and answer:
   - **Language, location, keyboard:** your own.
   - **Hostname:** a name such as `livingroom`. Other computers will reach it as **`livingroom.local`**. Use letters, digits and hyphens only.
   - **Domain name:** leave empty.
   - **Root password:** leave **empty** (press Continue twice). Your user then gets `sudo`, which the TVWCS installer needs. If you do set one, see the note in step 3.
   - **Your user:** a name (such as `tv`) and a password. You sign in over SSH as this user, and the computer logs in as it later.
   - **Partitioning:** **Guided – use entire disk**, then **All files in one partition**. This erases the disk.
   - **Package manager:** your country, then `deb.debian.org`. No proxy.
3. On **Software selection**, tick only:
   - [x] **SSH server**
   - [x] **standard system utilities**

   Clear everything else, including every desktop and the web server. In the text installer, **Space** ticks a box and **Enter** continues.
4. Install GRUB to the disk when asked. When it finishes, remove the stick and let the computer restart.

## 3. Turn on SSH and Avahi

The computer starts to a text login. Log in as your user, then run:

```bash
sudo apt update
sudo apt install openssh-server avahi-daemon libnss-mdns
sudo systemctl enable --now ssh avahi-daemon
hostname -I
```

- Avahi makes the computer reachable as `<hostname>.local`.
- `hostname -I` shows its IP address (such as `192.168.1.20`). Write it down in case the name does not work.

**If you set a root password:** run `su -`, then `apt install sudo openssh-server avahi-daemon libnss-mdns`, `usermod -aG sudo tv` (your user name), `systemctl enable --now ssh avahi-daemon` and `exit`. Log out and in again.

The rest is done from the other computer.

## 4. Install TVWCS from the other computer

1. Open a terminal: **PowerShell** on Windows, **Terminal** on macOS, any terminal on Linux.
2. Sign in to the TV computer. The `-t` lets the installer ask questions:

   ```bash
   ssh -t tv@livingroom.local
   ```

   Use your own user and hostname, or the IP address. The first time, answer `yes` to the fingerprint question, then type your password.
3. Download TVWCS and run the installer:

   ```bash
   cd "$(mktemp -d)"
   wget -qO- https://github.com/one-moment-please/tvwcs/releases/latest/download/tvwcs.tar.gz | tar -xz
   ./tvwcs/install.sh
   ```

4. Answer its questions. For a TV computer:

   | Question | Answer |
   |---|---|
   | **How should TVWCS be set up?** | Enter (**1**, only TVWCS). |
   | **Install one now? 1) i3 with Xorg (recommended) 2) sway 3) both 4) neither** | Enter (**i3**). sudo asks for your password. |
   | **Missing packages … Install them now?** | Enter (yes). |
   | **There is no i3 config yet. Create one from the standard template?** | Enter, then choose the `$mod` key and keyboard layout. |
   | **Add TVWCS to your i3 config?** | Enter (yes). |
   | **Let TVWCS sleep, reboot and shut down without asking for your password?** | Your choice. `y` is handy with a remote. |
   | **Install TVWCS's login screen? (It installs greetd and cage.)** | Enter (yes). It shows who can log in and takes the password from the remote. |
   | **Log in as tv automatically when the computer starts, and start i3?** | `y`. Anyone who switches the computer on gets your session, which suits a TV. The login screen then shows only after logging out. |
   | **Show the login screen now?** | Enter (yes). It logs you in by itself if you said yes above. |
   | **Will TVWCS be used on a TV or on a desktop monitor?** | Enter (**TV**). |

When the installer finishes, the TV shows TVWCS, and it does so every time the computer starts. Press ⚙ in the Quick Menu to open **Settings**.

## 5. Optional: sign in with a key instead of a password

1. On the other computer, make a key if you have none: `ssh-keygen -t ed25519` (press Enter for the defaults).
2. Copy it to the TV computer:
   - **macOS and Linux:** `ssh-copy-id tv@livingroom.local`
   - **Windows (PowerShell):** `type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh tv@livingroom.local "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"`
3. Check that `ssh tv@livingroom.local` no longer asks for a password.
4. On the TV, open **Settings › System information › Remote access (SSH)** and set **Sign in with** to **Keys only**. Settings refuses this until your user has a key, so you cannot lock yourself out.

## If something does not work

- **`Could not resolve hostname livingroom.local`:** use the IP address. Check that Avahi runs on the TV computer (`systemctl status avahi-daemon`). Some routers block these announcements between Wi-Fi and wired devices.
- **`Connection refused`:** the SSH server is not running. On the TV computer: `sudo systemctl enable --now ssh`.
- **The installer asks no questions:** you signed in without `-t`.
- **The TV still shows a text login:** someone was logged in on that screen during the install. Log out there (`exit`) or restart (`sudo reboot`).
- **No sound:** restart once (`sudo reboot`), then choose the output on the **Sound** page of Settings. HDMI outputs not in use yet are listed there too.
