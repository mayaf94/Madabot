#!/usr/bin/env python3
"""
Upload Code to S3 for Context Gathering

This script uploads code files to S3 so the analyzer Lambda can fetch them
for providing code context to AI analysis.

Usage:
    python scripts/upload_code_to_s3.py --bucket-name <bucket> --directory <path>
    python scripts/upload_code_to_s3.py --auto  # Auto-detect bucket from Terraform output
"""

import argparse
import os
import json
import subprocess
from pathlib import Path
import boto3
from botocore.exceptions import ClientError


class CodeUploader:
    """Uploads code files to S3 for AI context gathering"""

    # File extensions to upload (source code files)
    ALLOWED_EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx',
        '.go', '.java', '.rb', '.php',
        '.yaml', '.yml', '.json', '.tf',
        '.sh', '.bash', '.sql'
    }

    # Directories to skip
    SKIP_DIRECTORIES = {
        '__pycache__', '.git', 'node_modules', '.terraform',
        'venv', 'env', '.venv', 'dist', 'build',
        '.pytest_cache', '.mypy_cache', 'coverage'
    }

    def __init__(self, bucket_name: str, dry_run: bool = False):
        """
        Initialize code uploader

        Args:
            bucket_name: S3 bucket name
            dry_run: If True, only print what would be uploaded without uploading
        """
        self.bucket_name = bucket_name
        self.dry_run = dry_run
        self.s3_client = boto3.client('s3')

    def should_upload_file(self, file_path: Path) -> bool:
        """
        Determine if a file should be uploaded

        Args:
            file_path: Path to the file

        Returns:
            True if file should be uploaded
        """
        # Check extension
        if file_path.suffix not in self.ALLOWED_EXTENSIONS:
            return False

        # Check if in skip directory
        for part in file_path.parts:
            if part in self.SKIP_DIRECTORIES:
                return False

        # Skip test files (optional - comment out if you want to include tests)
        # if 'test' in file_path.name.lower():
        #     return False

        return True

    def upload_file(self, local_path: Path, s3_key: str) -> bool:
        """
        Upload a file to S3

        Args:
            local_path: Local file path
            s3_key: S3 key (path in bucket)

        Returns:
            True if successful
        """
        try:
            if self.dry_run:
                print(f"  [DRY RUN] Would upload: {local_path} → s3://{self.bucket_name}/{s3_key}")
                return True

            # Read file content
            with open(local_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=content.encode('utf-8'),
                ContentType='text/plain',
                Metadata={
                    'original-path': str(local_path),
                    'uploaded-by': 'upload_code_to_s3.py'
                }
            )

            print(f"  ✅ Uploaded: {local_path} → s3://{self.bucket_name}/{s3_key}")
            return True

        except Exception as e:
            print(f"  ❌ Error uploading {local_path}: {e}")
            return False

    def upload_directory(self, directory: Path, prefix: str = "") -> dict:
        """
        Upload all code files from a directory

        Args:
            directory: Local directory path
            prefix: S3 key prefix (subdirectory in bucket)

        Returns:
            Dictionary with upload statistics
        """
        stats = {
            'total': 0,
            'uploaded': 0,
            'skipped': 0,
            'failed': 0
        }

        print(f"\n📂 Scanning directory: {directory}")

        for root, dirs, files in os.walk(directory):
            # Remove skip directories from traversal
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRECTORIES]

            root_path = Path(root)

            for file_name in files:
                file_path = root_path / file_name
                stats['total'] += 1

                # Check if should upload
                if not self.should_upload_file(file_path):
                    stats['skipped'] += 1
                    continue

                # Calculate S3 key (relative path from directory)
                relative_path = file_path.relative_to(directory)
                s3_key = str(Path(prefix) / relative_path) if prefix else str(relative_path)

                # Upload file
                if self.upload_file(file_path, s3_key):
                    stats['uploaded'] += 1
                else:
                    stats['failed'] += 1

        return stats

    def upload_mapping_config(self, mapping: dict) -> bool:
        """
        Upload code mapping configuration to S3

        Args:
            mapping: Dictionary mapping log groups to code file paths

        Returns:
            True if successful
        """
        try:
            config_key = 'config/code-mapping.json'

            if self.dry_run:
                print(f"  [DRY RUN] Would upload mapping config: {config_key}")
                print(f"    Mapping: {json.dumps(mapping, indent=2)}")
                return True

            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=config_key,
                Body=json.dumps(mapping, indent=2).encode('utf-8'),
                ContentType='application/json',
                Metadata={
                    'uploaded-by': 'upload_code_to_s3.py'
                }
            )

            print(f"  ✅ Uploaded mapping config: s3://{self.bucket_name}/{config_key}")
            return True

        except Exception as e:
            print(f"  ❌ Error uploading mapping config: {e}")
            return False


def get_bucket_from_terraform() -> str:
    """
    Get S3 bucket name from Terraform output

    Returns:
        Bucket name from Terraform output
    """
    try:
        result = subprocess.run(
            ['terraform', 'output', '-json', 'code_storage_bucket_name'],
            cwd='terraform',
            capture_output=True,
            text=True,
            check=True
        )
        # Terraform output is JSON string, need to parse and strip quotes
        bucket_name = json.loads(result.stdout)
        return bucket_name
    except subprocess.CalledProcessError:
        raise RuntimeError(
            "Failed to get bucket name from Terraform. "
            "Make sure you've run 'terraform apply' first."
        )
    except FileNotFoundError:
        raise RuntimeError("Terraform not found. Please install Terraform.")


def main():
    parser = argparse.ArgumentParser(
        description='Upload code files to S3 for AI context gathering'
    )
    parser.add_argument(
        '--bucket-name',
        help='S3 bucket name (or use --auto to get from Terraform)'
    )
    parser.add_argument(
        '--auto',
        action='store_true',
        help='Auto-detect bucket name from Terraform output'
    )
    parser.add_argument(
        '--directory',
        default='.',
        help='Directory to upload (default: current directory)'
    )
    parser.add_argument(
        '--prefix',
        default='',
        help='S3 key prefix (subdirectory in bucket)'
    )
    parser.add_argument(
        '--mapping-file',
        default='config/code-mapping.json',
        help='Path to code mapping configuration file'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be uploaded without actually uploading'
    )

    args = parser.parse_args()

    # Get bucket name
    if args.auto:
        print("🔍 Getting bucket name from Terraform output...")
        bucket_name = get_bucket_from_terraform()
        print(f"   Found bucket: {bucket_name}")
    elif args.bucket_name:
        bucket_name = args.bucket_name
    else:
        parser.error("Either --bucket-name or --auto must be specified")

    # Initialize uploader
    uploader = CodeUploader(bucket_name, dry_run=args.dry_run)

    # Upload directory
    directory = Path(args.directory).resolve()
    if not directory.exists():
        print(f"❌ Directory not found: {directory}")
        return 1

    print(f"\n{'=' * 60}")
    print(f"Code Upload to S3")
    print(f"{'=' * 60}")
    print(f"Bucket: {bucket_name}")
    print(f"Directory: {directory}")
    print(f"Prefix: {args.prefix or '(root)'}")
    print(f"Dry Run: {args.dry_run}")
    print(f"{'=' * 60}")

    stats = uploader.upload_directory(directory, prefix=args.prefix)

    # Upload mapping configuration if exists
    mapping_path = Path(args.mapping_file)
    if mapping_path.exists():
        print(f"\n📋 Found mapping configuration: {mapping_path}")
        with open(mapping_path, 'r') as f:
            mapping = json.load(f)
        uploader.upload_mapping_config(mapping)
    else:
        print(f"\n⚠️  Mapping configuration not found: {mapping_path}")
        print("   Code files uploaded but mapping config not created.")
        print("   Create config/code-mapping.json to map log groups to code files.")

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"Upload Summary")
    print(f"{'=' * 60}")
    print(f"Total files scanned: {stats['total']}")
    print(f"✅ Uploaded: {stats['uploaded']}")
    print(f"⏭️  Skipped: {stats['skipped']}")
    print(f"❌ Failed: {stats['failed']}")
    print(f"{'=' * 60}")

    if not args.dry_run:
        print(f"\n✨ Code uploaded to s3://{bucket_name}/")
        print("   The analyzer Lambda can now fetch code context for alerts!")

    return 0 if stats['failed'] == 0 else 1


if __name__ == '__main__':
    exit(main())
