# Setting up a TV computer with Debian and TVWCS

This guide starts from an empty computer and ends with it booting straight into TVWCS. Debian is installed with the network installer and no desktop. You set up the SSH server and Avahi on it. Then you install TVWCS from another computer on your home network, so the TV computer needs a keyboard only for the first steps.

**You need:**
- the TV computer (64-bit PC, "amd64"), connected to your network, by cable if you can
- a USB stick of 1 GB or more (it will be erased)
- another computer on the same network, running Windows 10 or 11, macOS or Linux
- a keyboard for the TV computer, for the Debian install and the first log-in

## 1. Download Debian and write it to the USB stick

1. On the other computer, go to <https://www.debian.org/distrib/netinst> and download the **amd64** network install image (`debian-<version>-amd64-netinst.iso`, about 700 MB).
2. Write it to the USB stick:
   - **Windows:** [Rufus](https://rufus.ie) (choose the stick and the ISO, then **Start**; pick **DD image mode** if it asks), or [balenaEtcher](https://etcher.balena.io).
   - **macOS:** balenaEtcher.
   - **Linux:** balenaEtcher, or `sudo dd if=debian-*-netinst.iso of=/dev/sdX bs=4M status=progress conv=fsync`. Replace `/dev/sdX` with the stick, not a partition of it; `lsblk` lists the drives. Everything on that drive is lost.

## 2. Install Debian, without a desktop

1. Put the stick in the TV computer and start it from the stick. Most computers show a boot menu with **F12**, **F11**, **F8** or **Esc** right after switching on. Debian starts with Secure Boot on, so there is no need to turn it off.
2. Choose **Graphical install** (or **Install**) and answer the questions:
   - **Language, location, keyboard:** your own.
   - **Hostname:** a name for the TV computer, such as `livingroom`. Other computers reach it as **`livingroom.local`**. Use letters, digits and hyphens only.
   - **Domain name:** leave it empty.
   - **Root password:** leave it **empty** (press Continue twice). Debian then lets the user you create next use `sudo`, which TVWCS's installer uses. If you set a root password, see the note in step 3.
   - **Your user:** a full name, a user name (such as `tv`) and its password. This is the user you sign in as over SSH, and the one the computer logs in as by itself later.
   - **Partitioning:** **Guided – use entire disk**, then **All files in one partition**. This erases the disk.
   - **Package manager:** your country, then `deb.debian.org`. Leave the proxy empty.
3. On **Software selection**, choose **only** these two, and clear every other box:
   - [x] **SSH server**
   - [x] **standard system utilities**
   - [ ] Debian desktop environment, and every desktop under it (GNOME, Xfce, GNOME Flashback, KDE Plasma, Cinnamon, MATE, LXDE, LXQt): **cleared**
   - [ ] web server: **cleared**

   In the text installer, **Space** ticks and clears a box, and **Enter** continues.
4. Install the GRUB boot loader to the disk when asked. When the install finishes, take the stick out and let the computer restart.

## 3. Turn on SSH and Avahi on the TV computer

The computer starts to a text log-in. Log in as your user (`tv`) with its password, then run:

```bash
sudo apt update
sudo apt install openssh-server avahi-daemon libnss-mdns
sudo systemctl enable --now ssh avahi-daemon
hostname -I
```

- `openssh-server` is the SSH server (already there if you ticked **SSH server**; apt then says so).
- `avahi-daemon` announces the computer on your network as `<hostname>.local`, so you can use its name instead of its IP address. `libnss-mdns` lets it look up other `.local` names too.
- The last command shows the computer's IP address, such as `192.168.1.20`. Note it in case the name does not work from the other computer.

**If you set a root password** in step 2, your user cannot use `sudo` yet. Run `su -` (it asks for the root password), then `apt install sudo openssh-server avahi-daemon libnss-mdns`, `usermod -aG sudo tv` (your user name), `systemctl enable --now ssh avahi-daemon` and `exit`. Then log out with `exit` and log in again.

You can now leave the TV computer. The rest happens from the other computer.

## 4. Install TVWCS from the other computer

1. Open a terminal on the other computer: **PowerShell** on Windows (SSH is built in), **Terminal** on macOS, any terminal on Linux.
2. Sign in to the TV computer. The `-t` lets TVWCS's installer ask its questions:

   ```bash
   ssh -t tv@livingroom.local
   ```

   Use your user name and hostname, or the IP address (`ssh -t tv@192.168.1.20`) if the name is not found. The first time, answer `yes` to the question about the host's fingerprint, then type your password.
3. Download TVWCS and run its installer. `wget` comes with Debian's standard system utilities:

   ```bash
   cd "$(mktemp -d)"
   wget -qO- https://github.com/one-moment-please/tvwcs/archive/refs/heads/main.tar.gz | tar -xz
   ./tvwcs-main/scripts/install.sh
   ```

4. Answer the installer's questions. For a TV, these are the usual answers:
   - **Install one now? 1) i3 with Xorg (recommended)  2) sway  3) neither:** press Enter for **i3**. It installs i3 with Xorg and what TVWCS needs alongside it. sudo asks for your password.
   - **Missing packages … Install them now?** Enter (yes). The list says what each one is for: GTK for TVWCS's windows, PipeWire for sound, and the Settings app's tools for sound, displays, Bluetooth, the network and its terminal.
   - **There is no i3 config yet. Create one from the standard template?** Enter (yes), then choose the key for `$mod` and your keyboard layout.
   - **Add TVWCS to your i3 config?** Enter (yes).
   - **Let TVWCS sleep, reboot and shut down without asking for your password?** your choice. Yes is handy with a remote.
   - **There is no login screen on this computer. Log in as tv automatically when it starts, and start i3?** `y`. Anyone who switches the computer on gets your session without a password, which suits a TV. When the installer finishes, i3 and TVWCS start on the TV's screen straight away, and from then on whenever the computer starts.

That is all. The TV now shows TVWCS. The Quick Menu's ⚙ button opens **Settings**, which is also in the applications guide under **System**.

## 5. Optional: sign in with a key instead of a password

A key is safer than a password, and you are not asked for a password each time.

1. On the other computer, make a key if you have none: `ssh-keygen -t ed25519` (press Enter to accept the defaults).
2. Copy it to the TV computer:
   - **macOS and Linux:** `ssh-copy-id tv@livingroom.local`
   - **Windows (PowerShell):** `type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh tv@livingroom.local "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"`
3. Check that `ssh tv@livingroom.local` no longer asks for your password.
4. On the TV, open **Settings › System information**. Under **Remote access (SSH)**, set **Sign in with** to **Keys only**. Settings refuses this while no key has been added for your user, so you cannot lock yourself out.

The same section turns the SSH server on and off, and shows the command to connect with, the user, the computer's local name and its IP addresses.

## If something does not work

- **`ssh: Could not resolve hostname livingroom.local`:** use the IP address from step 3. Check on the TV computer that Avahi runs (`systemctl status avahi-daemon`). Some routers block the announcements between Wi-Fi and wired devices.
- **`Connection refused`:** the SSH server is not running. On the TV computer, run `sudo systemctl enable --now ssh`.
- **The installer asks no questions:** you signed in without `-t`. Sign in again with `ssh -t`.
- **The TV still shows a text log-in after the install:** someone was logged in on that screen during the install. Log out there (`exit`), or restart the computer (`sudo reboot`).
- **No sound:** PipeWire needs no setup: Debian starts it at every log-in. If there is still no sound, restart the computer once (`sudo reboot`). Then choose the output on the **Sound** page of Settings. An HDMI output the sound card is not using yet is listed there too; choosing it switches the card over.
