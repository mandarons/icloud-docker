#!/bin/sh
# Docker entrypoint script to replace s6-overlay functionality

# Set default values
PUID=${PUID:-911}
PGID=${PGID:-911}

# Update user and group IDs
echo "Setting up user 'abc' with UID: $PUID, GID: $PGID"
groupmod -o -g "$PGID" abc
usermod -o -u "$PUID" abc

# Display sponsorship message
echo "
====================================================
To support this project, please consider sponsoring.
https://github.com/sponsors/mandarons
https://www.buymeacoffee.com/mandarons

User UID:    $(id -u abc)
User GID:    $(id -g abc)
===================================================="

# Display build version if available
if [ -f /build_version ]; then
    cat /build_version
fi

# Create necessary directories
mkdir -p /icloud /config/session_data /home/abc /config/python_keyring

# Migrate python-keyring from old location to new if needed.
# PR #460 moved keyring to /config/python_keyring via XDG_DATA_HOME=/config
# (set in Dockerfile). Users who had keyring at the old location
# ($HOME/.local/share/python_keyring/) need it copied to the new path.
OLD_KEYRING="/home/abc/.local/share/python_keyring/keyring_pass.cfg"
NEW_KEYRING="/config/python_keyring/keyring_pass.cfg"
if [ -f "$OLD_KEYRING" ] && [ ! -f "$NEW_KEYRING" ]; then
    echo "Migrating keyring from $OLD_KEYRING to $NEW_KEYRING"
    cp "$OLD_KEYRING" "$NEW_KEYRING"
fi

# Set ownership if not already correct
for dir in /app /config /icloud /home/abc; do
    if [ "$(stat -c %u:%g "$dir" 2>/dev/null)" != "$(id -u abc):$(id -g abc)" ]; then
        echo "Setting ownership for $dir"
        chown -R abc:abc "$dir"
    fi
done

# Execute the main application as abc user
echo "Starting iCloud Docker application..."
exec su-exec abc /app/init.sh
