# iCloud-drive-docker [![Build Status](https://travis-ci.org/mandarons/icloud-drive-docker.svg?branch=main)](https://travis-ci.org/mandarons/icloud-drive-docker) [![codecov](https://codecov.io/gh/mandarons/icloud-drive-docker/branch/main/graph/badge.svg)](https://codecov.io/gh/mandarons/icloud-drive-docker) [![Docker](https://badgen.net/docker/pulls/mandarons/icloud-drive)](https://hub.docker.com/r/mandarons/icloud-drive) [![Join the chat at https://gitter.im/mandarons/iCloud-drive-docker](https://badges.gitter.im/mandarons/iCloud-drive-docker.svg)](https://gitter.im/mandarons/iCloud-drive-docker?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge) <a href="https://www.buymeacoffee.com/mandarons" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: 20px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

iCloud-drive-docker is a simple iCloud drive client in Docker environment. It uses [pyiCloud](https://github.com/picklepete/pyicloud) python library to interact
with iCloud drive server.

Primary use case of iCloud-drive-docker is to periodically sync wanted or all of your iCloud drive contents, using your
iCloud username and password.

## Installation

### Installation using Docker Hub
```
docker run --name icloud-drive -v ${PWD}/drive:/app/drive mandarons/icloud-drive 
```

### Installation using docker-compose
```yaml
version: "3.4"
services:
  icloud-drive:
    image: mandarons/icloud-drive
    environment:
      - PUID=<insert the output of `id -u $user`>
      - GUID=<insert the output of `id -g $user`>
    container_name: icloud-drive
    restart: unless-stopped
    volumes:
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
      - ${PWD}/icloud-drive/config.yaml:/app/config.yaml
      - ${PWD}/icloud-drive/drive:/app/drive
```

### Authentication (required after container creation)
```
docker exec -it icloud-drive /bin/sh -c "icloud --username=<icloud-username>"
```
Follow the steps to authenticate.

## Sample Configuration File
```yaml
credentials:
  # iCloud drive username: required
  username: username@domain.com
  # iCloud drive password: optional
  password:
settings:
  # Auto-sync interval in seconds: optional, default: 1800
  sync_interval: 1800
  # Destination to sync: required
  destination: './drive'
  # Flag if remove files/folders that are present locally but not on iCloud server: optional, default: false
  remove_obsolete: false
  # Verbosity of messages: optional, default: false
  verbose: false
filters:
  # Paths to be 'included' in syncing iCloud drive content
  folders:
    - Documents
  file_extensions: #Optional, leave empty for syncing all the content recursively
    # File extensions to be included in syncing iCloud drive content
    - pdf
    - png
    - jpg
    - jpeg
```
***Note: On every sync, this client iterates all the files and folders. Depending on number of files in your iCloud drive,
syncing can take longer.***
