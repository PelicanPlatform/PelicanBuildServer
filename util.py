import functools
import ssl
import time
from datetime import datetime
import certifi
import os
import shutil
import re
import packaging.version
import logging
import aiohttp
import aiofiles as aiof
import asyncio

from aiohttp import ClientResponseError

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Create default ssl context for dev
ssl_context = ssl.create_default_context(cafile=certifi.where())


def create_file_directories(file_path: str) -> None:
    """
    Create the directories for the filepath
    :param file_path: Filepath to populate directories for
    :return:
    """
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        os.makedirs(directory)
        logger.info(f"Created directory: {directory}")


async def install_file(session: aiohttp.ClientSession, url: str, directory: str, skip_existing: bool = True) -> None:
    """
    Install file at url to the current directory
    :param session: aiohttp session
    :param url: URL of the file to install
    :param directory: Directory to install the file
    :param skip_existing: Skip the download if the file is present
    """

    file_name = url.split('/')[-1]
    filepath = f"{directory}/{file_name}"

    if os.path.exists(filepath) and skip_existing:
        logger.debug(f"Skipping download of existing file: {filepath}")
        return

    async with session.get(url) as response:
        file_name = url.split('/')[-1]
        filepath = f"{directory}/{file_name}"
        create_file_directories(filepath)
        logger.info(f"Downloading file: {url} to {filepath}")

        async with aiof.open(filepath, "wb") as f:
            while True:
                chunk = await response.content.read(1024)  # Read in 1KB chunks
                if not chunk:
                    break
                await f.write(chunk)
        logger.info(f"Downloaded file: {filepath}")


async def install_assets(session: aiohttp.ClientSession, url: str, directory: str) -> None:
    """
    Install assets from the url to the directory
    :param session: aiohttp session
    :param url: Url to the assets api endpoint
    :param directory: Download directory
    :return:
    """

    async with session.get(url) as response:
        assets = await response.json()
        asset_urls = [asset['browser_download_url'] for asset in assets]
        tasks = [install_file(session, asset_url, directory) for asset_url in asset_urls]
        logger.info(f"Installing assets from: {url}")
        await asyncio.gather(*tasks)


async def install_releases(session: aiohttp.ClientSession, repo: str, directory: str) -> None:
    """
    Iterate through the release api and if the assets don't exist in the directory, download them
    :param session: aiohttp session
    :param repo: The Github repository to download
    :param directory: Directory to download the assets to
    :return:
    """

    async with session.get(f"https://api.github.com/repos/{repo}/releases") as response:
        releases = await response.json()

        tasks = []
        for release in releases:
            tag = release['tag_name'].replace("v", "")
            asset_directory = f"{directory}/{tag}"
            tasks.append(install_assets(session, release['assets_url'], asset_directory))

        if len(tasks) == 0:
            logger.info("No new releases found.")
            return

        await asyncio.gather(*tasks)


async def dynamic_linking(session: aiohttp.ClientSession, repo: str, directory: str) -> None:
    """
    Create symbolic links for the latest, major and minor releases
    :param session: aiohttp session
    :param repo: The Github repository to download
    :param directory: Directory to download the assets to
    :return:
    """

    release_tags = await get_release_tags(session, repo)
    await create_tracking_directories(release_tags, directory)


async def get_release_tags(session: aiohttp.ClientSession, repo: str) -> list[packaging.version.Version]:

    async with session.get(f"https://api.github.com/repos/{repo}/releases") as response:

        releases = await response.json()
        release_tags = [packaging.version.parse(release['tag_name'].replace("v", "")) for release in releases]

        # Sort the release tags
        release_tags.sort(reverse=True)

        return release_tags


async def create_tracking_directories(release_tags: list[packaging.version.Version], directory: str) -> None:
    """
    Iterate the present releases and apply symbolic links for the latest, major and minor releases
    :param release_tags: List of release tags in semver order
    :param directory: Directory to apply symbolic links to
    :return:
    """

    # Iterate the tags into a mapping dictionary
    tag_mapping = {
        'latest': release_tags[0]
    }
    for tag in release_tags:

        if tag.major not in tag_mapping:
            tag_mapping[tag.major] = tag

        major_minor_tag = f"{tag.major}.{tag.minor}"
        if major_minor_tag not in tag_mapping:
            tag_mapping[major_minor_tag] = tag

    # Create the symbolic links
    for tag_root, tag in tag_mapping.items():
        create_tracking_directory(tag, tag_root, directory)


def create_tracking_directory(release_tag: packaging.version.Version, tracking_directory_name: str, directory: str) -> None:
    """
    Create a tracking directory. This links to an existing semver tag and updates the latest directory. Files are updated
    to not include the version number and the checksum file is updated to reflect the new filenames.
    :param release_tag: The release tag to link to
    :param tracking_directory_name: The name of the tracking directory ( latest, X, X.Y )
    :param directory: The directory the releases are stored in
    :return:
    """

    # Create a fresh latest directory
    tracking_directory = f"{directory}/{tracking_directory_name}"
    if os.path.exists(tracking_directory):
        shutil.rmtree(tracking_directory)
    os.makedirs(tracking_directory)
    logging.info(f"Created latest directory: {tracking_directory}")

    # For each file in the tag directory create a symlink in the latest directory
    tag_directory = f"{directory}/{release_tag}"
    for file in os.listdir(tag_directory):

        # Handle the checksum file separately
        if file == "checksums.txt":
            continue

        relative_tag_file = f"../{release_tag.base_version}/{file}"
        latest_file = f"{tracking_directory}/{strip_version(file)}"
        os.symlink(relative_tag_file, latest_file)
        logging.info(f"Created symbolic link: {latest_file} -> {relative_tag_file}")

    # Copy and update the checksum file
    checksum_file = f"{tag_directory}/checksums.txt"
    latest_checksum_file = f"{tracking_directory}/checksums.txt"
    with open(checksum_file, "r") as f_existing:
        with open(latest_checksum_file, "w") as f_latest:
            for line in f_existing:
                checksum, file = line.split()
                latest_file = strip_version(file)
                f_latest.write(f"{checksum} {latest_file}\n")


def strip_version(version: str) -> str:
    # Remove the version number from the file
    r = re.compile(r"[-_]\d+\.\d+\.\d+[-_r]+\d*")
    version = r.sub("", version)
    # Remove unnecessary pelican prefixes
    r = re.compile(r"pelican[-_]")
    version = r.sub("", version)
    return version


def retry_on_exception(exception, retries: int = 3):
    """
    Retry the function if the exception is raised. If the exception is a 403, wait until the rate limit is reset.
    :param exception: Exception to retry on
    :param retries: Number of retries
    :return: Decorator function
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):

            i = 0
            while i < retries:
                try:
                    return await func(*args, **kwargs)

                except ClientResponseError as e:
                    if e.status == 403:
                        reset_time = e.headers.get("X-Ratelimit-Reset")
                        if reset_time:
                            wait_time = int(reset_time) - int(time.time())
                            if wait_time > 0:
                                logging.info(f"Rate limit exceeded. Waiting until {datetime.fromtimestamp(int(reset_time))} UTC")
                                await asyncio.sleep(wait_time)
                                continue

                except exception as e:
                    logging.error(f"Caught exception: {e}")
                    if i == retries - 1:
                        raise e
                    await asyncio.sleep(10**(i+1))
                    i += 1

        return wrapper

    return decorator


@retry_on_exception(Exception, retries=4)
async def update(repo: str, directory: str) -> None:

    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector, raise_for_status=True) as session:
        await install_releases(session, repo, directory)
        await dynamic_linking(session, repo, directory)


async def main():
    await update("PelicanPlatform/pelican", "releases")


if __name__ == "__main__":
    asyncio.run(main())
