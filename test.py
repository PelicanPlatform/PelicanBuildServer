import os

import pytest
import tempfile

from util import atomic_dir_replace

# Write tests for the utility functions in the `utils.py` file


class TestUtils:

    @pytest.mark.asyncio
    async def test_atomic_dir_swap(self):
        # Create two temporary directories
        with tempfile.TemporaryDirectory() as temp_dir_0, tempfile.TemporaryDirectory() as temp_dir_1:

            # Create a symlink to the first directory
            target_path = f"{temp_dir_0}_symlink"
            os.symlink(temp_dir_0, target_path)

            # Create two unique files in each directory
            with open(temp_dir_0 + "/temp.txt", "w") as temp_file_0, open(temp_dir_1 + "/temp.txt", "w") as temp_file_1:
                temp_file_0.write("Hello, World! 0")
                temp_file_1.write("Hello, World! 1")

            # Verify that the files are in the correct directories
            with open(f"{target_path}/temp.txt", "r") as target_file:
                assert target_file.read() == "Hello, World! 0"

            # Create a context manager that swaps the directories
            atomic_dir_replace(temp_dir_1, target_path)

            # Verify that the files were swapped
            with open(f"{target_path}/temp.txt", "r") as target_file:
                assert target_file.read() == "Hello, World! 1"

            # Verify that the original directory was deleted
            assert not os.path.exists(temp_dir_0)



