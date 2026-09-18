#!/bin/bash

# Ensure the script is run as root
if [ "$EUID" -ne 0 ]
  then echo "Please run as root (e.g., sudo ./install.sh)"
  exit
fi

echo "Installing rpups system..."

# Install required dependencies
echo "Installing dependencies..."
apt-get update
apt-get install -y python3-smbus i2c-tools

# Copy the python script to a bin directory
echo "Installing rpups command..."
cp rpups.py /usr/local/bin/rpups
chmod +x /usr/local/bin/rpups

# Create config directory and default config if not exists
echo "Setting up configuration directory..."
mkdir -p /etc/rpups
if [ ! -f /etc/rpups/config.json ]; then
    echo '{"poweroff_threshold": 20}' > /etc/rpups/config.json
fi

# Install the systemd service
echo "Installing systemd service..."
cp rpups.service /etc/systemd/system/
chmod 644 /etc/systemd/system/rpups.service

# Reload systemd and enable/start the service
echo "Enabling and starting rpups service..."
systemctl daemon-reload
systemctl enable rpups.service
systemctl restart rpups.service

echo "----------------------------------------"
echo "rpups installed successfully!"
echo "You can now use the 'rpups' command."
echo "Try running 'rpups --help' for usage."
