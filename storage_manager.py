import logging
import os
import uuid
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AsyncWasabiStorageManager:
    def __init__(self, max_workers: int = 5):
        self.access_key = os.getenv('WASABI_ACCESS_KEY')
        self.secret_key = os.getenv('WASABI_SECRET_KEY')
        self.bucket_name = os.getenv('WASABI_BUCKET_NAME')
        self.region = os.getenv('WASABI_REGION', 'us-east-1')

        # Thread pool for sync operations
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        # Set the correct regional endpoint URL for Wasabi
        regional_endpoints = {
            'us-east-1': 'https://s3.wasabisys.com',
            'us-east-2': 'https://s3.us-east-2.wasabisys.com',
            'us-west-1': 'https://s3.us-west-1.wasabisys.com',
            'eu-central-1': 'https://s3.eu-central-1.wasabisys.com',
            'eu-west-1': 'https://s3.eu-west-1.wasabisys.com',
            'eu-west-2': 'https://s3.eu-west-2.wasabisys.com',
            'ap-northeast-1': 'https://s3.ap-northeast-1.wasabisys.com',
            'ap-northeast-2': 'https://s3.ap-northeast-2.wasabisys.com',
            'ap-southeast-1': 'https://s3.ap-southeast-1.wasabisys.com',
            'ap-southeast-2': 'https://s3.ap-southeast-2.wasabisys.com'
        }

        # Use region-specific endpoint or fall back to env variable
        self.endpoint_url = regional_endpoints.get(self.region,
                                                   os.getenv('WASABI_ENDPOINT_URL', 'https://s3.wasabisys.com'))

        if not all([self.access_key, self.secret_key, self.bucket_name]):
            raise ValueError("Missing required Wasabi credentials. Please check your .env file.")

        logger.info(f"Connecting to Wasabi region: {self.region}, endpoint: {self.endpoint_url}")

        # Initialize S3 client for Wasabi with correct regional endpoint
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region
        )

        # Initialize S3 resource for advanced operations
        self.s3_resource = boto3.resource(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region
        )

        # Ensure bucket exists
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Bucket '{self.bucket_name}' exists and is accessible")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                try:
                    # For regions other than us-east-1, we need to specify location constraint
                    if self.region != 'us-east-1':
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.region}
                        )
                    else:
                        self.s3_client.create_bucket(Bucket=self.bucket_name)
                    logger.info(f"Created bucket '{self.bucket_name}' in region '{self.region}'")
                except ClientError as create_error:
                    logger.error(f"Failed to create bucket: {create_error}")
                    raise
            else:
                logger.error(f"Error accessing bucket: {e}")
                raise
        except NoCredentialsError:
            logger.error("No credentials found. Please check your Wasabi access key and secret key.")
            raise

    def _sanitize_filename_for_metadata(self, filename: str) -> str:
        """Sanitize filename to contain only ASCII characters for S3 metadata"""
        # Remove or replace non-ASCII characters
        sanitized = re.sub(r'[^\x00-\x7F]+', '_', filename)
        # Replace multiple underscores with single underscore
        sanitized = re.sub(r'_{2,}', '_', sanitized)
        # Remove leading/trailing underscores
        sanitized = sanitized.strip('_')
        return sanitized

    def _upload_file_sync(self, file_content: bytes, filename: str, content_type: str = None) -> str:
        """Upload file to Wasabi and return the file key (sync version)"""
        # Generate unique file key with original extension
        file_extension = filename.split('.')[-1] if '.' in filename else 'bin'
        file_key = f"{uuid.uuid4()}.{file_extension}"

        try:
            # Prepare extra arguments
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type

            # Add metadata for better file management - sanitize filename for ASCII compliance
            sanitized_filename = self._sanitize_filename_for_metadata(filename)
            extra_args['Metadata'] = {
                'original_filename': sanitized_filename,
                'upload_timestamp': str(uuid.uuid4().time_low)
            }

            # Upload using put_object for better control
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_key,
                Body=file_content,
                **extra_args
            )

            logger.info(f"Successfully uploaded file '{filename}' with key: {file_key}")
            return file_key

        except ClientError as e:
            logger.error(f"Failed to upload file '{filename}': {e}")
            raise Exception(f"Failed to upload file: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error uploading file '{filename}': {e}")
            raise Exception(f"Unexpected upload error: {str(e)}")

    async def upload_file(self, file_content: bytes, filename: str, content_type: str = None) -> str:
        """Upload file to Wasabi and return the file key (async wrapper)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._upload_file_sync,
            file_content,
            filename,
            content_type
        )

    def _get_file_url_sync(self, file_key: str, expiration: int = 3600) -> str:
        """Generate a presigned URL for file download (sync version)"""
        try:
            # Check if file exists first
            self.s3_client.head_object(Bucket=self.bucket_name, Key=file_key)

            # Generate presigned URL forcing download
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': file_key,
                    'ResponseContentDisposition': 'attachment',  # Force download
                    'ResponseContentType': 'application/octet-stream'  # Generic binary type
                },
                ExpiresIn=expiration
            )

            logger.info(f"Generated presigned URL for {file_key} (forced download), expires in {expiration} seconds")
            return url

        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.error(f"File not found: {file_key}")
                raise Exception(f"File not found: {file_key}")
            else:
                logger.error(f"Failed to generate presigned URL for {file_key}: {e}")
                raise Exception(f"Failed to generate URL: {str(e)}")

    async def get_file_url(self, file_key: str, expiration: int = 3600) -> str:
        """Generate a presigned URL for file download (async wrapper)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._get_file_url_sync,
            file_key,
            expiration
        )

    def _delete_file_sync(self, file_key: str) -> bool:
        """Delete file from Wasabi (sync version)"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_key)
            logger.info(f"Successfully deleted file with key: {file_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete file {file_key}: {e}")
            return False

    async def delete_file(self, file_key: str) -> bool:
        """Delete file from Wasabi (async wrapper)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self._delete_file_sync, file_key)

    def _list_files_sync(self, prefix: str = "", max_keys: int = 100):
        """List files in Wasabi bucket (sync version)"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )

            files = []
            for obj in response.get('Contents', []):
                files.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].isoformat(),
                    'etag': obj['ETag'].strip('"')
                })

            logger.info(f"Listed {len(files)} files from bucket '{self.bucket_name}'")
            return files

        except ClientError as e:
            logger.error(f"Failed to list files: {e}")
            raise Exception(f"Failed to list files: {str(e)}")

    async def list_files(self, prefix: str = "", max_keys: int = 100):
        """List files in Wasabi bucket (async wrapper)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._list_files_sync,
            prefix,
            max_keys
        )

    def _get_bucket_info_sync(self):
        """Get bucket information and test connectivity (sync version)"""
        try:
            # Test bucket access
            response = self.s3_client.head_bucket(Bucket=self.bucket_name)

            # Get bucket location
            location = self.s3_client.get_bucket_location(Bucket=self.bucket_name)

            return {
                'bucket_name': self.bucket_name,
                'region': location.get('LocationConstraint', 'us-east-1'),
                'accessible': True,
                'endpoint': self.endpoint_url
            }
        except ClientError as e:
            logger.error(f"Cannot access bucket info: {e}")
            return {
                'bucket_name': self.bucket_name,
                'accessible': False,
                'error': str(e)
            }

    async def get_bucket_info(self):
        """Get bucket information and test connectivity (async wrapper)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self._get_bucket_info_sync)

    def __del__(self):
        """Clean up thread pool on deletion"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)


# Backwards compatibility - keep the original synchronous class
class WasabiStorageManager:
    def __init__(self):
        self.access_key = os.getenv('WASABI_ACCESS_KEY')
        self.secret_key = os.getenv('WASABI_SECRET_KEY')
        self.bucket_name = os.getenv('WASABI_BUCKET_NAME')
        self.region = os.getenv('WASABI_REGION', 'us-east-1')

        # Set the correct regional endpoint URL for Wasabi
        regional_endpoints = {
            'us-east-1': 'https://s3.wasabisys.com',
            'us-east-2': 'https://s3.us-east-2.wasabisys.com',
            'us-west-1': 'https://s3.us-west-1.wasabisys.com',
            'eu-central-1': 'https://s3.eu-central-1.wasabisys.com',
            'eu-west-1': 'https://s3.eu-west-1.wasabisys.com',
            'eu-west-2': 'https://s3.eu-west-2.wasabisys.com',
            'ap-northeast-1': 'https://s3.ap-northeast-1.wasabisys.com',
            'ap-northeast-2': 'https://s3.ap-northeast-2.wasabisys.com',
            'ap-southeast-1': 'https://s3.ap-southeast-1.wasabisys.com',
            'ap-southeast-2': 'https://s3.ap-southeast-2.wasabisys.com'
        }

        # Use region-specific endpoint or fall back to env variable
        self.endpoint_url = regional_endpoints.get(self.region,
                                                   os.getenv('WASABI_ENDPOINT_URL', 'https://s3.wasabisys.com'))

        if not all([self.access_key, self.secret_key, self.bucket_name]):
            raise ValueError("Missing required Wasabi credentials. Please check your .env file.")

        logger.info(f"Connecting to Wasabi region: {self.region}, endpoint: {self.endpoint_url}")

        # Initialize S3 client for Wasabi with correct regional endpoint
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region
        )

        # Initialize S3 resource for advanced operations
        self.s3_resource = boto3.resource(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region
        )

        # Ensure bucket exists
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Bucket '{self.bucket_name}' exists and is accessible")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                try:
                    # For regions other than us-east-1, we need to specify location constraint
                    if self.region != 'us-east-1':
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.region}
                        )
                    else:
                        self.s3_client.create_bucket(Bucket=self.bucket_name)
                    logger.info(f"Created bucket '{self.bucket_name}' in region '{self.region}'")
                except ClientError as create_error:
                    logger.error(f"Failed to create bucket: {create_error}")
                    raise
            else:
                logger.error(f"Error accessing bucket: {e}")
                raise
        except NoCredentialsError:
            logger.error("No credentials found. Please check your Wasabi access key and secret key.")
            raise

    def _sanitize_filename_for_metadata(self, filename: str) -> str:
        """Sanitize filename to contain only ASCII characters for S3 metadata"""
        # Remove or replace non-ASCII characters
        sanitized = re.sub(r'[^\x00-\x7F]+', '_', filename)
        # Replace multiple underscores with single underscore
        sanitized = re.sub(r'_{2,}', '_', sanitized)
        # Remove leading/trailing underscores
        sanitized = sanitized.strip('_')
        return sanitized

    def upload_file(self, file_content: bytes, filename: str, content_type: str = None) -> str:
        """Upload file to Wasabi and return the file key"""
        # Generate unique file key with original extension
        file_extension = filename.split('.')[-1] if '.' in filename else 'bin'
        file_key = f"{uuid.uuid4()}.{file_extension}"

        try:
            # Prepare extra arguments
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type

            # Add metadata for better file management - sanitize filename for ASCII compliance
            sanitized_filename = self._sanitize_filename_for_metadata(filename)
            extra_args['Metadata'] = {
                'original_filename': sanitized_filename,
                'upload_timestamp': str(uuid.uuid4().time_low)
            }

            # Upload using put_object for better control
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_key,
                Body=file_content,
                **extra_args
            )

            logger.info(f"Successfully uploaded file '{filename}' with key: {file_key}")
            return file_key

        except ClientError as e:
            logger.error(f"Failed to upload file '{filename}': {e}")
            raise Exception(f"Failed to upload file: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error uploading file '{filename}': {e}")
            raise Exception(f"Unexpected upload error: {str(e)}")

    def get_file_url(self, file_key: str, expiration: int = 3600) -> str:
        """Generate a presigned URL for file download"""
        try:
            # Check if file exists first
            self.s3_client.head_object(Bucket=self.bucket_name, Key=file_key)

            # Generate presigned URL forcing download
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': file_key,
                    'ResponseContentDisposition': 'attachment',  # Force download
                    'ResponseContentType': 'application/octet-stream'  # Generic binary type
                },
                ExpiresIn=expiration
            )

            logger.info(f"Generated presigned URL for {file_key} (forced download), expires in {expiration} seconds")
            return url

        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.error(f"File not found: {file_key}")
                raise Exception(f"File not found: {file_key}")
            else:
                logger.error(f"Failed to generate presigned URL for {file_key}: {e}")
                raise Exception(f"Failed to generate URL: {str(e)}")

    def delete_file(self, file_key: str) -> bool:
        """Delete file from Wasabi"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_key)
            logger.info(f"Successfully deleted file with key: {file_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete file {file_key}: {e}")
            return False

    def list_files(self, prefix: str = "", max_keys: int = 100):
        """List files in Wasabi bucket"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )

            files = []
            for obj in response.get('Contents', []):
                files.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].isoformat(),
                    'etag': obj['ETag'].strip('"')
                })

            logger.info(f"Listed {len(files)} files from bucket '{self.bucket_name}'")
            return files

        except ClientError as e:
            logger.error(f"Failed to list files: {e}")
            raise Exception(f"Failed to list files: {str(e)}")

    def get_bucket_info(self):
        """Get bucket information and test connectivity"""
        try:
            # Test bucket access
            response = self.s3_client.head_bucket(Bucket=self.bucket_name)

            # Get bucket location
            location = self.s3_client.get_bucket_location(Bucket=self.bucket_name)

            return {
                'bucket_name': self.bucket_name,
                'region': location.get('LocationConstraint', 'us-east-1'),
                'accessible': True,
                'endpoint': self.endpoint_url
            }
        except ClientError as e:
            logger.error(f"Cannot access bucket info: {e}")
            return {
                'bucket_name': self.bucket_name,
                'accessible': False,
                'error': str(e)
            }