# Release File Server

Downloads files for a Github repositories releases and serves them by semver tag.

## Usage

This website will auto update daily and provides a webhook for manual updates. Files are served by NGINX and the 
file update functionality is provided by FASTAPI.

### Webhook

A webhook is provided to manually toggle an update post release.

https://pelican-release-server.chtc.chtc.io/api/docs

## File Scheme

Saves files by semver tag in the following directory structure:

### All Releases

Per release directories, file names include the release tag.

/X.Y.Z - Directory for a single release

### Tracking Releases

Directories to track the lifecycle of a release, always pointing to the latest applicable release. The files in the 
directories are symlinked and renamed to omit the release tag. The only file not symlinked is `checksums.txt` which is 
copied and updated to match the version-less names of the files.

- /X.Y - Directory for latest minor release
- /X - Directory for latest major release
- /latest - Directory for latest release

## Build, Run, Release

### Build

```shell
docker build -t release-webhook .
```

```shell
docker run -it -p 8080:8000 --env-file example.env -v ${PWD}/releases:/srv/releases release-webhook
```

### Release

```shell
docker build --platform linux/amd64 -t hub.opensciencegrid.org/opensciencegrid/release-webhook .
```

```shell
docker push hub.opensciencegrid.org/opensciencegrid/release-webhook
```

## Run the NGINX server that sits in front of the webhook

```shell
docker run -it -p 80:80 --env-file example.env -v ${PWD}/releases:/srv/releases  -v ${PWD}/nginx.conf:/etc/nginx/templates/nginx.conf.template nginx
```
