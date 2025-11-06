"""
Code Context Fetcher - S3-Based Implementation

Fetches relevant code from S3 to provide context for AI analysis.
Reads code files stored in S3 bucket and provides relevant snippets for alerts.
"""

import os
import re
import boto3
import json
from typing import Dict, List, Optional, Any


class CodeFetcher:
    """Fetches code context for alerts from S3"""

    def __init__(self, bucket_name: Optional[str] = None):
        """
        Initialize code fetcher

        Args:
            bucket_name: S3 bucket name for code storage (defaults to env var CODE_BUCKET)
        """
        self.bucket_name = bucket_name or os.environ.get('CODE_BUCKET', '')
        self.s3_client = boto3.client('s3') if self.bucket_name else None

        # Code mapping will be loaded from S3
        self.code_mapping = {}
        if self.bucket_name:
            self._load_code_mapping()

    def _load_code_mapping(self):
        """
        Load code mapping configuration from S3

        Reads code-mapping.json from S3 bucket which maps log groups to code files.
        Falls back to default mapping if file doesn't exist.
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key='config/code-mapping.json'
            )
            self.code_mapping = json.loads(response['Body'].read().decode('utf-8'))
            print(f"✅ Loaded code mapping from S3: {len(self.code_mapping)} entries")
        except self.s3_client.exceptions.NoSuchKey:
            print("⚠️ code-mapping.json not found in S3, using default mapping")
            self.code_mapping = {
                '/aws/test-app': 'test/test_app.py'
            }
        except Exception as e:
            print(f"❌ Error loading code mapping from S3: {e}")
            self.code_mapping = {
                '/aws/test-app': 'test/test_app.py'
            }

    def extract_line_numbers_from_stacktrace(self, message: str) -> List[int]:
        """
        Extract line numbers from Python stack traces

        Args:
            message: Error message potentially containing stack trace

        Returns:
            List of line numbers found in stack trace
        """
        # Pattern: File "...", line 123
        # Also matches: line 123, at line 123, etc.
        pattern = r'line\s+(\d+)'
        matches = re.findall(pattern, message, re.IGNORECASE)
        return [int(m) for m in matches]

    def read_file_content(self, file_path: str) -> Optional[str]:
        """
        Read file content from S3

        Args:
            file_path: S3 key for the file (e.g., 'test/test_app.py')

        Returns:
            File content as string, or None if file not found
        """
        if not self.s3_client or not self.bucket_name:
            print("❌ S3 client not initialized - CODE_BUCKET not configured")
            return None

        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=file_path
            )

            content = response['Body'].read().decode('utf-8')
            print(f"✅ Read code file from S3: {file_path} ({len(content)} chars)")
            return content

        except self.s3_client.exceptions.NoSuchKey:
            print(f"⚠️ Code file not found in S3: {file_path}")
            return None
        except Exception as e:
            print(f"❌ Error reading code file from S3 {file_path}: {e}")
            return None

    def get_code_snippet(self, content: str, line_number: Optional[int] = None, context_lines: int = 10) -> str:
        """
        Extract relevant code snippet with context

        Args:
            content: Full file content
            line_number: Specific line to highlight (optional)
            context_lines: Number of lines before/after to include

        Returns:
            Formatted code snippet
        """
        lines = content.split('\n')

        if line_number is None:
            # No specific line - return first 50 lines or key functions
            return '\n'.join(lines[:50])

        # Extract context around specific line
        start = max(0, line_number - context_lines - 1)
        end = min(len(lines), line_number + context_lines)

        snippet_lines = []
        for i in range(start, end):
            line = lines[i]
            line_num = i + 1

            # Highlight the error line
            if line_num == line_number:
                snippet_lines.append(f"{line_num:4d}→ >>> {line}  # <-- ERROR LINE")
            else:
                snippet_lines.append(f"{line_num:4d}→ {line}")

        return '\n'.join(snippet_lines)

    def get_code_context(self, alert: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get code context for an alert

        Args:
            alert: Alert data containing log_group, message, etc.

        Returns:
            Dictionary with code context, or None if no code found
        """
        log_group = alert.get('log_group', '')
        message = alert.get('message', '')

        # Check if we have a mapping for this log group
        file_path = self.code_mapping.get(log_group)

        if not file_path:
            print(f"ℹ️ No code mapping for log group: {log_group}")
            return None

        print(f"📄 Fetching code context for {log_group} → {file_path}")

        # Read the file
        content = self.read_file_content(file_path)

        if not content:
            return None

        # Extract line numbers from stack trace
        line_numbers = self.extract_line_numbers_from_stacktrace(message)

        # Get relevant snippet
        if line_numbers:
            # Use first line number found
            snippet = self.get_code_snippet(content, line_numbers[0], context_lines=10)
            highlighted_line = line_numbers[0]
        else:
            # No specific line - show key parts of the file
            snippet = self.get_code_snippet(content, None)
            highlighted_line = None

        return {
            'file_path': file_path,
            'log_group': log_group,
            'snippet': snippet,
            'highlighted_line': highlighted_line,
            'full_content_length': len(content),
            'is_test_app': 'test' in file_path.lower()
        }

    def format_code_context(self, code_context: Optional[Dict[str, Any]]) -> str:
        """
        Format code context for inclusion in AI prompt

        Args:
            code_context: Code context dictionary from get_code_context()

        Returns:
            Formatted markdown string
        """
        if not code_context:
            return ""

        file_path = code_context['file_path']
        snippet = code_context['snippet']
        is_test = code_context.get('is_test_app', False)
        highlighted_line = code_context.get('highlighted_line')

        lines = [
            "\n## Relevant Code Context",
            f"\n**Source File**: `{file_path}`"
        ]

        if highlighted_line:
            lines.append(f"**Error Location**: Line {highlighted_line}")

        if is_test:
            lines.append("\n⚠️ **Note**: This is a test application that generates synthetic errors for demonstration purposes.")

        lines.extend([
            "\n```python",
            snippet,
            "```"
        ])

        if is_test:
            lines.append("\n**Important**: The errors from this application are intentionally generated test scenarios, not real production issues.")

        return '\n'.join(lines)
