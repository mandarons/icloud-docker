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
mkdir -p /icloud /config/session_data

# Set ownership if not already correct
for dir in /app /config /icloud; do
    if [ "$(stat -c %u:%g "$dir" 2>/dev/null)" != "$(id -u abc):$(id -g abc)" ]; then
        echo "Setting ownership for $dir"
        chown -R abc:abc "$dir"
    fi
done

# Execute the main application as abc user
echo "Starting iCloud Docker application..."
exec su-exec abc /app/init.sh
