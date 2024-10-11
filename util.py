import json
import os
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


async def install_file(session: aiohttp.ClientSession, url: str, directory: str) -> None:
    """
    Install file at url to the current directory
    :param session: aiohttp session
    :param url: URL of the file to install
    :param directory: Directory to install the file
    """
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


async def install_new_releases(repo: str, directory: str) -> None:
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

                existing_tag_directories = []
                try:
                    existing_tag_directories = os.listdir(directory)
                except FileNotFoundError:
                    pass

                if tag not in existing_tag_directories:

                    asset_directory = f"{directory}/{tag}"
                    tasks.append(install_assets(session, release['assets_url'], asset_directory))
                    logger.info(f"New release found: {tag}, downloading assets.")

            if len(tasks) == 0:
                logger.info("No new releases found.")
                return

            await asyncio.gather(*tasks)


async def apply_symbolic_links(repo: str, directory: str) -> None:
    """
    Iterate the present releases and apply symbolic links for the latest, major and minor releases
    :param repo: Github repository that has the relevant releases
    :param directory: Directory to apply symbolic links to
    :return:
    """

    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.github.com/repos/{repo}/releases") as response:

            releases = await response.json()
            release_tags = [packaging.version.parse(release['tag_name'].replace("v", "")) for release in releases]

            # Sort the release tags
            release_tags.sort(reverse=True)

            # Iterate the tags into a mapping dictionary
            tag_mapping = {
                "latest": release_tags[0]
            }
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

            # Write the tag_mapping to an index.json file
            async with aiof.open(f"{directory}/index.json", "w") as f:
                await f.write(json.dumps({k: tag.base_version for k, tag in tag_mapping.items()}))


async def update(repo: str, directory: str) -> None:
    await install_new_releases(repo, directory)
    await apply_symbolic_links(repo, directory)


async def main():
    await install_new_releases("PelicanPlatform/pelican", "releases")
    await apply_symbolic_links("PelicanPlatform/pelican", "releases")


if __name__ == "__main__":
    asyncio.run(main())
