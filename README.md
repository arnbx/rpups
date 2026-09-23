# Raspberry Pi UPS Manager (rpups)

A command-line tool and system daemon for managing Raspberry Pi UPS hardware on Debian-based systems.

## Features

- Background daemon that automatically powers off the Raspberry Pi when running on battery and the capacity falls below a specified threshold.
- Tells the UPS to wait 30 seconds, allowing for a graceful shutdown, and automatically turns the Raspberry Pi back on when AC power returns.
- Simple command-line interface to check UPS state and configure parameters.

## Installation

Run the installation script on your Raspberry Pi:

```bash
cd rpups_system
chmod +x install.sh
sudo ./install.sh
```

This will:
1. Install necessary dependencies (`python3-smbus`, `i2c-tools`).
2. Install the `rpups` command globally.
3. Install and start the `rpups` background systemd service.

## Usage

You can use the `rpups` command to check the status or configure settings.

- **Check remaining capacity:**
  ```bash
  rpups remain
  ```

- **Check battery percentage:**
  ```bash
  rpups remain -p
  ```

- **Check charging state:**
  ```bash
  rpups state
  ```

- **Set poweroff threshold (e.g., to 10%):**
  Requires `sudo` to update the configuration file.
  ```bash
  sudo rpups poweroff 10
  ```

- **View startup and shutdown logs:**
  Displays the persistent log containing the last 10 power events.
  ```bash
  rpups log
  ```

- **View help:**
  ```bash
  rpups -h
  ```

## Modifying and Rebuilding the `.deb` Package

If you want to edit the python code or service configuration and re-build the `.deb` installer yourself in the future, you can easily do so!

1. Edit the source files (`rpups.py`, `rpups.service`).
2. To rebuild it on your Raspberry Pi, you just run:

```bash
chmod +x build_deb.sh
./build_deb.sh
```

This script packages everything up into a fresh `.deb` installer (`rpups_new.deb`) using `dpkg-deb`.


## Testing the System

Once installed, you'll want to verify that everything works correctly—especially the automatic shutdown and recovery.

### 1. Verify the Daemon
Check that the background service is running and healthy:
```bash
systemctl status rpups.service
```
*(You can press `q` to exit the status view).*

### 2. Verify the CLI
Run a few commands to ensure they can read from the UPS:
```bash
rpups state
rpups remain -p
```

### 3. Test the Auto-Shutdown and Auto-Wakeup
To test the automatic power-off feature without waiting for the battery to drain naturally:

1. **Check current battery:** Run `rpups remain -p` to see your current percentage (e.g., 95%).
2. **Unplug AC Power:** Disconnect the wall power so the UPS is running purely on battery.
3. **Set a high threshold:** Set the shutdown threshold just *above* your current battery level. If you are at 95%, set it to 96:
   ```bash
   sudo rpups poweroff 96
   ```
4. **Wait:** Within 60 seconds, the background daemon will detect that the battery is below the threshold and that it is discharging. The Raspberry Pi will gracefully shut down.
5. **Observe the UPS:** The UPS hardware will wait for ~30 seconds after receiving the shutdown command.
6. **Test Auto-Wakeup:** Once the Raspberry Pi is completely off, **plug the AC power back in**. The UPS should detect the power and automatically turn the Raspberry Pi back on.
7. **Reset the Threshold:** Once booted back up, don't forget to restore the threshold to a normal level (e.g., 20%):
   ```bash
   sudo rpups poweroff 20
   ```
