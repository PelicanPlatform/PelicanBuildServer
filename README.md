# Release File Server

Downloads files for a Github repositories releases and serves them by semver tag.

## Usage

This website will auto update daily and provides a webhook for manual updates.

## Scheme

Saves files by semver tag in the following directory structure:

/X.Y.Z - Directory for a single release
/X.Y - Directory for latest minor release
/X - Directory for latest major release
/latest - Directory for latest release
/index.json - JSON file describing this mapping

## Build and Run

```shell
docker build --platform linux/amd64 -t hub.opensciencegrid.org/opensciencegrid/release-webhook .
```

```shell
docker run -it -p 8080:8000 --env-file example.env -v ${PWD}/releases:/srv/releases hub.opensciencegrid.org/opensciencegrid/release-webhook
```

```shell
docker push hub.opensciencegrid.org/opensciencegrid/release-webhook
```

## Run the NGINX server that sits in front of the webhook

```shell
docker run -it -p 80:80 --env-file example.env -v ${PWD}/releases:/srv/releases  -v ${PWD}/nginx.conf:/etc/nginx/templates/nginx.conf.template nginx
```
