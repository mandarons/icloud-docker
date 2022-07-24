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
docker run --name icloud -v ${PWD}/icloud:/app/icloud -v ${PWD}/config.yaml:/app/config.yaml -e ENV_ICLOUD_PASSWORD=<icloud_password> -v ${PWD}/session_data:/app/session_data mandarons/icloud-drive 
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
    env_file:
      - .env.icloud #should contain ENV_ICLOUD_PASSWORD=<password>
    container_name: icloud
    restart: unless-stopped
    volumes:
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
      - ${PWD}/icloud/config.yaml:/app/config.yaml
      - ${PWD}/icloud/data:/app/icloud
      - ${PWD}/session_data:/app/session_data
```

### Authentication (required after container creation or authentication expiration)
```
# Login manually if ENV_ICLOUD_PASSWORD is not specified and/or 2FA is required
docker exec -it icloud /bin/sh -c "icloud --username=<icloud-username> --session-directory=/app/session_data"
```
For China server users, Please add `--region=china` as follows:
```
# Login manually if ENV_ICLOUD_PASSWORD is not specified and/or 2FA is required
docker exec -it icloud /bin/sh -c "icloud --username=<icloud-username> --region=china --session-directory=/app/session_data"
```
Follow the steps to authenticate.

## Sample Configuration File
```yaml
app:
  logger:
    # level - debug, info (default), warning or error
    level: "info"
    # log filename icloud.log (default)
    filename: "icloud.log"
  credentials:
    # iCloud drive username
    username: "please@replace.me"
    # Retry login interval - default is 10 minutes
    retry_login_interval: 600
  # Drive destination
  root: "icloud"
  smtp:
    ## If you want to recieve email notifications about expired/missing 2FA credentials then uncomment
    # email: "user@test.com"
    ## optional, to email address. Default is sender email.
    # to: "receiver@test.com"
    # password:
    # host: "smtp.test.com"
    # port: 587
    # If your email provider doesn't handle TLS
    # no_tls: true
  region: global # For China server users, set this to - china (default: global)
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
