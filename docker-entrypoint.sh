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

# Persist python-keyring across container recreations.
# python-keyring's `keyrings.alt` file backend stores its passwords in
# `$XDG_DATA_HOME/python_keyring/keyring_pass.cfg`. Default $XDG_DATA_HOME
# is `$HOME/.local/share` — inside the container, so every `docker compose up`
# (or PUID change, or image bump) wipes the cached Apple ID password and
# the user has to re-authenticate. Pointing XDG_DATA_HOME at the bind-mounted
# /config makes the keyring file persist for the life of the volume.
export XDG_DATA_HOME=/config
# /config/python_keyring is created above as root; the conditional chown
# block below skips /config when it's already owned by abc (common on
# bind-mounted hosts) and would leave the new subdir root-owned and
# unwritable. Always chown the keyring dir specifically.
chown abc:abc /config/python_keyring 2>/dev/null || true

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
