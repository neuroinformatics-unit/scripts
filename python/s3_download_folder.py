"""
Command-line script for downloading files from an S3 folder to a local directory.

Prerequisites:
1. Install the AWS CLI: https://aws.amazon.com/cli/
   It can also be installed via `conda-forge` with `conda install -c conda-forge awscli`.
2. Make sure you have your AWS access key ID and secret access key configured 
   either through environment variables or AWS CLI configuration (`aws configure`)
3. Install the Python dependencies: `pip install boto3 typer[all]`

Run the script from the command line as follows:
python s3_download_folder.py s3_bucket_name s3_prefix local_folder
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import boto3
import typer


def setup_logging(
    log_file: Path,
    logger_name: str = "s3_download",
):
    """Setup logging to file and console with INFO level"""
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    # Create a file handler with log rotation
    file_handler = RotatingFileHandler(log_file, maxBytes=1e6)
    # Create a console handler
    console_handler = logging.StreamHandler()

    formatter = logging.Formatter(
        "%(asctime)s - %(pathname)s:%(lineno)d - %(levelname)s - %(message)s"
    )

    # Set formatter for handlers
    for handler in [file_handler, console_handler]:
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def list_files(
    s3_client: boto3.client,
    s3_bucket: str,
    s3_prefix: str,
):
    """List files in specific S3 URL"""
    response = s3_client.list_objects_v2(Bucket=s3_bucket, Prefix=s3_prefix)
    for obj in response.get("Contents", []):
        yield obj["Key"]


def main(
    s3_bucket: str,
    s3_prefix: str,
    local_dir: Path,
    aws_region: str = "eu-west-2",
):
    """Download files from S3 folder to local directory.

    This function will download all files from the specified S3 folder to the
    specified local directory. Any subdirectories in the S3 prefix will be
    replicated in the local directory. A 'download_log.txt' file will also be
    saved in this directory. If a file already exists locally, it will be
    skipped.

    Parameters
    ----------
    s3_bucket : str
        S3 bucket name
    s3_prefix : str
        S3 prefix (folder) name
    local_dir : Path
        Local directory to save the files to. Any subdirectories in the S3
        prefix will be replicated in the local directory.
        A 'download_log.txt' file will also be saved in this directory.
    aws_region : str, optional
        AWS region, by default 'eu-west-2' (London, UK)

    Examples
    --------
    >>> main(
    ...     s3_bucket='aind-behavior-data',
    ...     s3_prefix='pose_estimation_training/LP-results/face-leave_one_out_results',
    ...     local_dir=Path('/path/to/local/directory'),
    ...     aws_region='eu-west-2',
    ... )
    """

    # Prepare local directory
    local_dir.mkdir(parents=True, exist_ok=True)
    (local_dir / s3_prefix).mkdir(parents=True, exist_ok=True)

    # Initialize S3 client
    s3 = boto3.client("s3", region_name=aws_region)

    # Start logging
    setup_logging(local_dir / "download_log.txt", logger_name="s3_download")
    logger = logging.getLogger("s3_download")

    for obj_key in list_files(s3, s3_bucket, s3_prefix):
        local_file_path = local_dir / obj_key
        if local_file_path.exists():
            logger.info(f"Skipping {obj_key}, already exists locally")
        else:
            local_file_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                s3.download_file(s3_bucket, obj_key, local_file_path.as_posix())
                logger.info(f"Downloaded {obj_key} to {local_file_path}")
            except Exception as e:
                logger.error(f"Failed to download {obj_key} to {local_file_path}: {e}")


if __name__ == "__main__":
    typer.run(main)
