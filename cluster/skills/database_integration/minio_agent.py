"""
MinIO Integration Agent - Full operations for MinIO object storage
"""

from minio import Minio
from minio.error import S3Error
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import structlog
import io

from .base_storage import BaseStorageAgent

logger = structlog.get_logger()


class MinIOAgent(BaseStorageAgent):
    """
    MinIO integration agent with full capabilities

    Capabilities:
    - Object operations (upload, download, delete)
    - Bucket management
    - Presigned URLs
    - Versioning
    - Object metadata
    - Multipart uploads
    - Copy operations
    - List objects with pagination
    """

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
            "copy_objects"
        ]

    async def connect(self) -> bool:
        """Establish MinIO connection"""
        try:
            if self.client:
                return True

            endpoint = self.config.get('endpoint', 'localhost:9000')
            access_key = self.config['access_key']
            secret_key = self.config['secret_key']
            secure = self.config.get('secure', False)

            self.client = Minio(
                endpoint=endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure
            )

            # Test connection
            self.client.list_buckets()

            self.is_connected = True
            logger.info("Connected to MinIO", endpoint=endpoint)
            return True

        except Exception as e:
            logger.error("MinIO connection failed", error=str(e))
            self.is_connected = False
            return False

    async def disconnect(self):
        """Close MinIO connection"""
        # MinIO client doesn't need explicit disconnect
        self.client = None
        self.is_connected = False
        logger.info("Disconnected from MinIO")

    async def upload(self, bucket: str, object_name: str,
                    file_path: Optional[Union[str, Path]] = None,
                    data: Optional[bytes] = None,
                    metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Upload object"""
        if not self.client:
            await self.connect()

        try:
            if file_path:
                # Upload from file
                result = self.client.fput_object(
                    bucket,
                    object_name,
                    str(file_path),
                    metadata=metadata
                )
            elif data:
                # Upload from bytes
                data_stream = io.BytesIO(data)
                result = self.client.put_object(
                    bucket,
                    object_name,
                    data_stream,
                    length=len(data),
                    metadata=metadata
                )
            else:
                raise ValueError("Either file_path or data must be provided")

            logger.info(f"Uploaded {object_name} to {bucket}")
            return {
                'etag': result.etag,
                'version_id': result.version_id,
                'bucket': bucket,
                'object_name': object_name
            }

        except S3Error as e:
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
                self.client.fget_object(bucket, object_name, str(file_path))
                logger.info(f"Downloaded {object_name} to {file_path}")
                return str(file_path)
            else:
                # Download to memory
                response = self.client.get_object(bucket, object_name)
                data = response.read()
                response.close()
                response.release_conn()

                logger.info(f"Downloaded {object_name} from {bucket}")
                return data

        except S3Error as e:
            logger.error(f"Download failed", error=str(e))
            raise

    async def delete(self, bucket: str, object_name: str) -> bool:
        """Delete object"""
        if not self.client:
            await self.connect()

        try:
            self.client.remove_object(bucket, object_name)
            logger.info(f"Deleted {object_name} from {bucket}")
            return True

        except S3Error as e:
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
            objects = self.client.list_objects(
                bucket,
                prefix=prefix,
                recursive=recursive
            )

            results = []
            for obj in objects:
                results.append({
                    'object_name': obj.object_name,
                    'size': obj.size,
                    'etag': obj.etag,
                    'last_modified': obj.last_modified,
                    'content_type': obj.content_type
                })

                if max_keys and len(results) >= max_keys:
                    break

            return results

        except S3Error as e:
            logger.error(f"List objects failed", error=str(e))
            return []

    async def get_metadata(self, bucket: str, object_name: str) -> Dict[str, Any]:
        """Get object metadata"""
        if not self.client:
            await self.connect()

        try:
            stat = self.client.stat_object(bucket, object_name)

            return {
                'object_name': stat.object_name,
                'size': stat.size,
                'etag': stat.etag,
                'last_modified': stat.last_modified,
                'content_type': stat.content_type,
                'metadata': stat.metadata,
                'version_id': stat.version_id
            }

        except S3Error as e:
            logger.error(f"Get metadata failed", error=str(e))
            return {}

    async def get_info(self) -> Dict[str, Any]:
        """Get MinIO information"""
        if not self.client:
            await self.connect()

        try:
            buckets = self.client.list_buckets()

            return {
                'endpoint': self.config.get('endpoint'),
                'buckets': [b.name for b in buckets],
                'bucket_count': len(buckets)
            }

        except S3Error as e:
            logger.error(f"Get info failed", error=str(e))
            return {}

    async def create_bucket(self, bucket: str,
                           region: Optional[str] = None) -> bool:
        """Create bucket"""
        if not self.client:
            await self.connect()

        try:
            if not self.client.bucket_exists(bucket):
                self.client.make_bucket(bucket, location=region)
                logger.info(f"Created bucket {bucket}")
            else:
                logger.info(f"Bucket {bucket} already exists")

            return True

        except S3Error as e:
            logger.error(f"Create bucket failed", error=str(e))
            return False

    async def delete_bucket(self, bucket: str) -> bool:
        """Delete bucket"""
        if not self.client:
            await self.connect()

        try:
            self.client.remove_bucket(bucket)
            logger.info(f"Deleted bucket {bucket}")
            return True

        except S3Error as e:
            logger.error(f"Delete bucket failed", error=str(e))
            return False

    async def list_buckets(self) -> List[Dict[str, Any]]:
        """List all buckets"""
        if not self.client:
            await self.connect()

        try:
            buckets = self.client.list_buckets()

            return [{
                'name': b.name,
                'creation_date': b.creation_date
            } for b in buckets]

        except S3Error as e:
            logger.error(f"List buckets failed", error=str(e))
            return []

    async def presigned_get_url(self, bucket: str, object_name: str,
                               expires_seconds: int = 3600) -> str:
        """Generate presigned GET URL"""
        if not self.client:
            await self.connect()

        try:
            from datetime import timedelta

            url = self.client.presigned_get_object(
                bucket,
                object_name,
                expires=timedelta(seconds=expires_seconds)
            )

            logger.info(f"Generated presigned URL for {object_name}")
            return url

        except S3Error as e:
            logger.error(f"Presigned URL generation failed", error=str(e))
            return ""

    async def presigned_put_url(self, bucket: str, object_name: str,
                               expires_seconds: int = 3600) -> str:
        """Generate presigned PUT URL"""
        if not self.client:
            await self.connect()

        try:
            from datetime import timedelta

            url = self.client.presigned_put_object(
                bucket,
                object_name,
                expires=timedelta(seconds=expires_seconds)
            )

            logger.info(f"Generated presigned PUT URL for {object_name}")
            return url

        except S3Error as e:
            logger.error(f"Presigned URL generation failed", error=str(e))
            return ""
