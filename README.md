# iCloud-docker (Previously known as iCloud-drive-docker) 

[![CI - Main](https://github.com/mandarons/icloud-drive-docker/actions/workflows/ci-main-test-coverage-deploy.yml/badge.svg?branch=main)](https://github.com/mandarons/icloud-drive-docker/actions/workflows/ci-main-test-coverage-deploy.yml)
[![Tests](https://mandarons.github.io/icloud-drive-docker/badges/tests.svg)](https://mandarons.github.io/icloud-drive-docker/test-results/)
[![Coverage](https://mandarons.github.io/icloud-drive-docker/badges/coverage.svg)](https://mandarons.github.io/icloud-drive-docker/test-coverage/index.html)
[![Docker](https://badgen.net/docker/pulls/mandarons/icloud-drive)](https://hub.docker.com/r/mandarons/icloud-drive)
[![Discord](https://img.shields.io/discord/871555550444408883?style=for-the-badge)](https://discord.gg/HfAXY2ykhp)
<a href="https://www.buymeacoffee.com/mandarons" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: 20px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

:love_you_gesture: ***Please star this repository if you end up using the container. It will help me continue supporting this product.*** :pray:

iCloud-docker (previously known as iCloud-drive-docker) is a simple iCloud client in Docker environment. It uses [iCloudPy](https://github.com/mandarons/icloudpy) python library to interact with iCloud server.

Primary use case of iCloud-docker is to periodically sync wanted or all of your iCloud drive, photos using your iCloud username and password. 

***Please note that this application only downloads the files from server. It does not upload the local files to the server (yet).***

## Installation

### Installation using Docker Hub
```
docker run --name icloud -v ${PWD}/icloud:/app/icloud -v ${PWD}/config.yaml:/app/config.yaml mandarons/icloud-drive 
```

### Installation using docker-compose
```yaml
version: "3.4"
services:
  icloud:
    image: mandarons/icloud-drive
    environment:
      - PUID=<insert the output of `id -u $user`>
      - GUID=<insert the output of `id -g $user`>
    container_name: icloud
    restart: unless-stopped
    volumes:
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
      - ${PWD}/icloud/config.yaml:/app/config.yaml
      - ${PWD}/icloud/data:/app/icloud
```

### Authentication (required after container creation or authentication expiration)
```
docker exec -it icloud /bin/sh -c "icloud --username=<icloud-username>"
```
Follow the steps to authenticate.

## Sample Configuration File
```yaml
app:
  logger:
    # level - debug, info, warning (default) or error
    level: "warning"
    # log filename icloud.log (default)
    filename: "icloud.log"
  credentials:
    # iCloud drive username
    username: "please@replace.me"
  # Drive destination
  root: "icloud"
  smtp:
    # If you want to recieve email notifications about expired/missing 2FA credentials then uncomment
    # email: "user@test.com"
    # password:
    # host: "smtp.test.com"
    # port: 587
    # If your email provider doesn't handle TLS
    # no_tls: true
drive:
  destination: "drive"
  remove_obsolete: false
  sync_interval: 300
  filters:
    # File filters to be included in syncing iCloud drive content
    folders:
      - "folder1"
      - "folder2"
      - "folder3"
    file_extensions:
      # File extensions to be included
      - "pdf"
      - "png"
      - "jpg"
      - "jpeg"
photos:
  destination: "photos"
  remove_obsolete: false
  sync_inteval: 500
  filters:
    albums:
      - "album 1"
      - "album2"
    file_sizes: # valid values are original, medium and/or thumb
      - "original"
      # - "medium"
      # - "thumb"
```
***Note: On every sync, this client iterates all the files. Depending on number of files in your iCloud (drive + photos), syncing can take longer.***

## Use Cases
[Make scanned documents from iCloud Drive, searchable](https://mandarons.com/posts/make-scanned-documents-from-icloud-drive-searchable)
