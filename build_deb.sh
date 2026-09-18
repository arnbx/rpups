#!/bin/bash
# Run this script on a Debian/Ubuntu system (like your Raspberry Pi) to build the .deb package.

echo "Setting up package structure..."
mkdir -p build_deb/rpups_1.0-1_all/DEBIAN
mkdir -p build_deb/rpups_1.0-1_all/usr/local/bin
mkdir -p build_deb/rpups_1.0-1_all/etc/rpups
mkdir -p build_deb/rpups_1.0-1_all/etc/systemd/system

echo "Copying application files..."
cp rpups.py build_deb/rpups_1.0-1_all/usr/local/bin/rpups
chmod 755 build_deb/rpups_1.0-1_all/usr/local/bin/rpups

cp rpups.service build_deb/rpups_1.0-1_all/etc/systemd/system/
chmod 644 build_deb/rpups_1.0-1_all/etc/systemd/system/rpups.service

echo '{"poweroff_threshold": 20}' > build_deb/rpups_1.0-1_all/etc/rpups/config.json
chmod 644 build_deb/rpups_1.0-1_all/etc/rpups/config.json

echo "Creating DEBIAN control files..."
# 1. The control file (Package metadata)
cat <<EOF > build_deb/rpups_1.0-1_all/DEBIAN/control
Package: rpups
Version: 1.0-1
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-smbus, i2c-tools
Maintainer: Arnab Bose <hello@arnabbose.dev>
Description: Raspberry Pi UPS Manager
 A command-line tool and system daemon for managing Raspberry Pi UPS hardware on Debian-based systems.
EOF
chmod 644 build_deb/rpups_1.0-1_all/DEBIAN/control

# 2. The postinst script (Runs after installation)
cat <<'EOF' > build_deb/rpups_1.0-1_all/DEBIAN/postinst
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    systemctl daemon-reload
    systemctl enable rpups.service
    systemctl restart rpups.service || true
fi
exit 0
EOF
chmod 755 build_deb/rpups_1.0-1_all/DEBIAN/postinst

# 3. The prerm script (Runs before uninstallation)
cat <<'EOF' > build_deb/rpups_1.0-1_all/DEBIAN/prerm
#!/bin/sh
set -e
if [ "$1" = "remove" ]; then
    systemctl stop rpups.service || true
    systemctl disable rpups.service || true
fi
exit 0
EOF
chmod 755 build_deb/rpups_1.0-1_all/DEBIAN/prerm

echo "Building the .deb package..."
# Uses dpkg-deb which is standard on Debian systems
dpkg-deb --build build_deb/rpups_1.0-1_all
mv build_deb/rpups_1.0-1_all.deb rpups_new.deb

# Clean up
rm -rf build_deb

echo "Successfully built rpups_new.deb!"
