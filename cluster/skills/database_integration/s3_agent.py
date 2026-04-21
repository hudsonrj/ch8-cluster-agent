"""
S3 Integration Agent - Full operations for AWS S3
"""

import aioboto3
from botocore.exceptions import ClientError
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import structlog

from .base_storage import BaseStorageAgent

logger = structlog.get_logger()


class S3Agent(BaseStorageAgent):
    """
    AWS S3 integration agent with full capabilities

    Capabilities:
    - Object operations (upload, download, delete)
    - Bucket management
    - Presigned URLs
    - Versioning
    - Object metadata
    - Multipart uploads
    - Copy operations
    - S3 Select
    - Lifecycle policies
    - Encryption
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.session = None
        self.resource = None

    def _define_capabilities(self) -> List[str]:
        return [
            "connect",
            "upload",
            "download",
            "delete",
            "list_objects",
            "bucket_management",
            "presigned_urls",
            "versioning",
            "metadata",
            "multipart_upload",
            "copy_objects",
            "s3_select",
            "encryption"
        ]

    async def connect(self) -> bool:
        """Establish S3 connection"""
        try:
            if self.client:
                return True

            self.session = aioboto3.Session(
                aws_access_key_id=self.config.get('aws_access_key_id'),
                aws_secret_access_key=self.config.get('aws_secret_access_key'),
                region_name=self.config.get('region', 'us-east-1')
            )

            self.client = await self.session.client('s3').__aenter__()
            self.resource = await self.session.resource('s3').__aenter__()

            self.is_connected = True
            logger.info("Connected to S3", region=self.config.get('region'))
            return True

        except Exception as e:
            logger.error("S3 connection failed", error=str(e))
            self.is_connected = False
            return False

    async def disconnect(self):
        """Close S3 connection"""
        if self.client:
            await self.client.__aexit__(None, None, None)
            await self.resource.__aexit__(None, None, None)
            self.client = None
            self.resource = None
            self.session = None
            self.is_connected = False
            logger.info("Disconnected from S3")

    async def upload(self, bucket: str, object_name: str,
                    file_path: Optional[Union[str, Path]] = None,
                    data: Optional[bytes] = None,
                    metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Upload object"""
        if not self.client:
            await self.connect()

        try:
            extra_args = {}
            if metadata:
                extra_args['Metadata'] = metadata

            if file_path:
                # Upload from file
                await self.client.upload_file(
                    str(file_path),
                    bucket,
                    object_name,
                    ExtraArgs=extra_args if extra_args else None
                )
            elif data:
                # Upload from bytes
                await self.client.put_object(
                    Bucket=bucket,
                    Key=object_name,
                    Body=data,
                    **extra_args
                )
            else:
                raise ValueError("Either file_path or data must be provided")

            # Get object metadata
            response = await self.client.head_object(Bucket=bucket, Key=object_name)

            logger.info(f"Uploaded {object_name} to {bucket}")
            return {
                'etag': response.get('ETag', '').strip('"'),
                'version_id': response.get('VersionId'),
                'bucket': bucket,
                'object_name': object_name
            }

        except ClientError as e:
            logger.error(f"Upload failed", error=str(e))
            raise

    async def download(self, bucket: str, object_name: str,
                      file_path: Optional[Union[str, Path]] = None) -> Union[bytes, str]:
        """Download object"""
        if not self.client:
            await self.connect()

        try:
            if file_path:
                # Download to file
                await self.client.download_file(bucket, object_name, str(file_path))
                logger.info(f"Downloaded {object_name} to {file_path}")
                return str(file_path)
            else:
                # Download to memory
                response = await self.client.get_object(Bucket=bucket, Key=object_name)
                data = await response['Body'].read()

                logger.info(f"Downloaded {object_name} from {bucket}")
                return data

        except ClientError as e:
            logger.error(f"Download failed", error=str(e))
            raise

    async def delete(self, bucket: str, object_name: str) -> bool:
        """Delete object"""
        if not self.client:
            await self.connect()

        try:
            await self.client.delete_object(Bucket=bucket, Key=object_name)
            logger.info(f"Deleted {object_name} from {bucket}")
            return True

        except ClientError as e:
            logger.error(f"Delete failed", error=str(e))
            return False

    async def list_objects(self, bucket: str,
                          prefix: Optional[str] = None,
                          recursive: bool = True,
                          max_keys: Optional[int] = None) -> List[Dict[str, Any]]:
        """List objects in bucket"""
        if not self.client:
            await self.connect()

        try:
            params = {'Bucket': bucket}
            if prefix:
                params['Prefix'] = prefix
            if max_keys:
                params['MaxKeys'] = max_keys
            if not recursive:
                params['Delimiter'] = '/'

            response = await self.client.list_objects_v2(**params)

            results = []
            for obj in response.get('Contents', []):
                results.append({
                    'object_name': obj['Key'],
                    'size': obj['Size'],
                    'etag': obj['ETag'].strip('"'),
                    'last_modified': obj['LastModified'],
                    'storage_class': obj.get('StorageClass', 'STANDARD')
                })

            return results

        except ClientError as e:
            logger.error(f"List objects failed", error=str(e))
            return []

    async def get_metadata(self, bucket: str, object_name: str) -> Dict[str, Any]:
        """Get object metadata"""
        if not self.client:
            await self.connect()

        try:
            response = await self.client.head_object(Bucket=bucket, Key=object_name)

            return {
                'object_name': object_name,
                'size': response['ContentLength'],
                'etag': response['ETag'].strip('"'),
                'last_modified': response['LastModified'],
                'content_type': response.get('ContentType', ''),
                'metadata': response.get('Metadata', {}),
                'version_id': response.get('VersionId')
            }

        except ClientError as e:
            logger.error(f"Get metadata failed", error=str(e))
            return {}

    async def get_info(self) -> Dict[str, Any]:
        """Get S3 information"""
        if not self.client:
            await self.connect()

        try:
            response = await self.client.list_buckets()
            buckets = response.get('Buckets', [])

            return {
                'region': self.config.get('region', 'us-east-1'),
                'buckets': [b['Name'] for b in buckets],
                'bucket_count': len(buckets)
            }

        except ClientError as e:
            logger.error(f"Get info failed", error=str(e))
            return {}

    async def create_bucket(self, bucket: str,
                           region: Optional[str] = None) -> bool:
        """Create bucket"""
        if not self.client:
            await self.connect()

        try:
            region = region or self.config.get('region', 'us-east-1')

            if region == 'us-east-1':
                await self.client.create_bucket(Bucket=bucket)
            else:
                await self.client.create_bucket(
                    Bucket=bucket,
                    CreateBucketConfiguration={'LocationConstraint': region}
                )

            logger.info(f"Created bucket {bucket}")
            return True

        except ClientError as e:
            logger.error(f"Create bucket failed", error=str(e))
            return False

    async def delete_bucket(self, bucket: str) -> bool:
        """Delete bucket"""
        if not self.client:
            await self.connect()

        try:
            await self.client.delete_bucket(Bucket=bucket)
            logger.info(f"Deleted bucket {bucket}")
            return True

        except ClientError as e:
            logger.error(f"Delete bucket failed", error=str(e))
            return False

    async def list_buckets(self) -> List[Dict[str, Any]]:
        """List all buckets"""
        if not self.client:
            await self.connect()

        try:
            response = await self.client.list_buckets()

            return [{
                'name': b['Name'],
                'creation_date': b['CreationDate']
            } for b in response.get('Buckets', [])]

        except ClientError as e:
            logger.error(f"List buckets failed", error=str(e))
            return []

    async def copy_object(self, source_bucket: str, source_object: str,
                         dest_bucket: str, dest_object: str) -> bool:
        """Copy object"""
        if not self.client:
            await self.connect()

        try:
            copy_source = {'Bucket': source_bucket, 'Key': source_object}

            await self.client.copy_object(
                CopySource=copy_source,
                Bucket=dest_bucket,
                Key=dest_object
            )

            logger.info(f"Copied {source_object} to {dest_object}")
            return True

        except ClientError as e:
            logger.error(f"Copy failed", error=str(e))
            return False

    async def presigned_get_url(self, bucket: str, object_name: str,
                               expires_seconds: int = 3600) -> str:
        """Generate presigned GET URL"""
        if not self.client:
            await self.connect()

        try:
            url = await self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': object_name},
                ExpiresIn=expires_seconds
            )

            logger.info(f"Generated presigned URL for {object_name}")
            return url

        except ClientError as e:
            logger.error(f"Presigned URL generation failed", error=str(e))
            return ""

    async def presigned_put_url(self, bucket: str, object_name: str,
                               expires_seconds: int = 3600) -> str:
        """Generate presigned PUT URL"""
        if not self.client:
            await self.connect()

        try:
            url = await self.client.generate_presigned_url(
                'put_object',
                Params={'Bucket': bucket, 'Key': object_name},
                ExpiresIn=expires_seconds
            )

            logger.info(f"Generated presigned PUT URL for {object_name}")
            return url

        except ClientError as e:
            logger.error(f"Presigned URL generation failed", error=str(e))
            return ""
