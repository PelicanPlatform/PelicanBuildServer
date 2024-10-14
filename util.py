import json
import os
import shutil
import re
import packaging.version
import logging
import aiohttp
import aiofiles as aiof
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


async def install_releases(repo: str, directory: str) -> None:
    """
    Iterate through the release api and if the assets don't exist in the directory, download them
    :param repo: The Github repository to download
    :param directory: Directory to download the assets to
    :return:
    """
    async with aiohttp.ClientSession() as session:
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


async def dynamic_linking(repo: str, directory: str) -> None:
    """
    Create symbolic links for the latest, major and minor releases
    :param repo: The Github repository to download
    :param directory: Directory to download the assets to
    :return:
    """

    release_tags = await get_release_tags(repo)
    await apply_symbolic_links(release_tags, directory)
    await update_latest_release(release_tags[0], directory)


async def get_release_tags(repo: str) -> list[packaging.version.Version]:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.github.com/repos/{repo}/releases") as response:

            releases = await response.json()
            release_tags = [packaging.version.parse(release['tag_name'].replace("v", "")) for release in releases]

            # Sort the release tags
            release_tags.sort(reverse=True)

            return release_tags


async def apply_symbolic_links(release_tags: list[packaging.version.Version], directory: str) -> None:
    """
    Iterate the present releases and apply symbolic links for the latest, major and minor releases
    :param release_tags: List of release tags in semver order
    :param directory: Directory to apply symbolic links to
    :return:
    """

    # Iterate the tags into a mapping dictionary
    tag_mapping = {}
    for tag in release_tags:

        if tag.major not in tag_mapping:
            tag_mapping[tag.major] = tag

        major_minor_tag = f"{tag.major}.{tag.minor}"
        if major_minor_tag not in tag_mapping:
            tag_mapping[major_minor_tag] = tag

    # Create the symbolic links
    for tag_root, tag in tag_mapping.items():
        tag_directory = f"{directory}/{tag.base_version}"
        tag_relative_directory = f"./{tag.base_version}"
        tag_root_directory = f"{directory}/{tag_root}"
        if os.path.exists(tag_directory):
            logging.info(f"Creating symbolic link: {tag_root_directory} -> {tag_relative_directory}")
            try:
                os.remove(tag_root_directory)
            except FileNotFoundError:
                pass
            os.symlink(tag_relative_directory, tag_root_directory)


async def update_latest_release(release_tag: packaging.version.Version, directory: str) -> None:
    """
    Create a latest directory. This links to the highest semver tag and recreates the checksum.txt file with the new filenames
    :param repo:
    :param directory:
    :return:
    """

    # Create a fresh latest directory
    latest_directory = f"{directory}/latest"
    if os.path.exists(latest_directory):
        shutil.rmtree(latest_directory)
    os.makedirs(latest_directory)
    logging.info(f"Created latest directory: {latest_directory}")

    # For each file in the tag directory create a symlink in the latest directory
    tag_directory = f"{directory}/{release_tag}"
    for file in os.listdir(tag_directory):

        # Handle the checksum file separately
        if file == "checksums.txt":
            continue

        relative_tag_file = f"../{release_tag.base_version}/{file}"
        latest_file = f"{latest_directory}/{strip_version(file)}"
        os.symlink(relative_tag_file, latest_file)
        logging.info(f"Created symbolic link: {latest_file} -> {relative_tag_file}")

    # Copy and update the checksum file
    checksum_file = f"{tag_directory}/checksums.txt"
    latest_checksum_file = f"{latest_directory}/checksums.txt"
    with open(checksum_file, "r") as f_existing:
        with open(latest_checksum_file, "w") as f_latest:
            for line in f_existing:
                checksum, file = line.split()
                latest_file = strip_version(file)
                f_latest.write(f"{checksum} {latest_file}\n")


def strip_version(version: str) -> str:
    r = re.compile(r"[-_]\d+\.\d+\.\d+[-_r]+\d*")
    return r.sub("", version)


async def update(repo: str, directory: str) -> None:
    await install_releases(repo, directory)
    await dynamic_linking(repo, directory)


async def main():
    # await install_releases("PelicanPlatform/pelican", "releases")
    await update_latest_release(packaging.version.Version("7.10.9"), "releases")


if __name__ == "__main__":
    asyncio.run(main())
