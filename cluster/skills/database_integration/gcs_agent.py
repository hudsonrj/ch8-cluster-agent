"""
Google Cloud Storage Integration Agent - Full operations for GCS
"""

from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import structlog

from .base_storage import BaseStorageAgent

logger = structlog.get_logger()


class GoogleCloudStorageAgent(BaseStorageAgent):
    """
    Google Cloud Storage integration agent with full capabilities

    Capabilities:
    - Object operations (upload, download, delete)
    - Bucket management
    - Signed URLs
    - Versioning
    - Object metadata
    - Copy operations
    - Batch operations
    - Lifecycle policies
    """

    def _define_capabilities(self) -> List[str]:
        return [
            "connect",
            "upload",
            "download",
            "delete",
            "list_objects",
            "bucket_management",
            "signed_urls",
            "versioning",
            "metadata",
            "copy_objects",
            "batch_operations"
        ]

    async def connect(self) -> bool:
        """Establish GCS connection"""
        try:
            if self.client:
                return True

            credentials_path = self.config.get('credentials_path')
            project_id = self.config.get('project_id')

            if credentials_path:
                self.client = storage.Client.from_service_account_json(
                    credentials_path,
                    project=project_id
                )
            else:
                # Use default credentials
                self.client = storage.Client(project=project_id)

            # Test connection
            list(self.client.list_buckets(max_results=1))

            self.is_connected = True
            logger.info("Connected to Google Cloud Storage", project=project_id)
            return True

        except Exception as e:
            logger.error("GCS connection failed", error=str(e))
            self.is_connected = False
            return False

    async def disconnect(self):
        """Close GCS connection"""
        if self.client:
            self.client.close()
            self.client = None
            self.is_connected = False
            logger.info("Disconnected from Google Cloud Storage")

    async def upload(self, bucket: str, object_name: str,
                    file_path: Optional[Union[str, Path]] = None,
                    data: Optional[bytes] = None,
                    metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Upload object"""
        if not self.client:
            await self.connect()

        try:
            bucket_obj = self.client.bucket(bucket)
            blob = bucket_obj.blob(object_name)

            if metadata:
                blob.metadata = metadata

            if file_path:
                # Upload from file
                blob.upload_from_filename(str(file_path))
            elif data:
                # Upload from bytes
                blob.upload_from_string(data)
            else:
                raise ValueError("Either file_path or data must be provided")

            logger.info(f"Uploaded {object_name} to {bucket}")
            return {
                'etag': blob.etag,
                'generation': blob.generation,
                'bucket': bucket,
                'object_name': object_name
            }

        except GoogleCloudError as e:
            logger.error(f"Upload failed", error=str(e))
            raise

    async def download(self, bucket: str, object_name: str,
                      file_path: Optional[Union[str, Path]] = None) -> Union[bytes, str]:
        """Download object"""
        if not self.client:
            await self.connect()

        try:
            bucket_obj = self.client.bucket(bucket)
            blob = bucket_obj.blob(object_name)

            if file_path:
                # Download to file
                blob.download_to_filename(str(file_path))
                logger.info(f"Downloaded {object_name} to {file_path}")
                return str(file_path)
            else:
                # Download to memory
                data = blob.download_as_bytes()
                logger.info(f"Downloaded {object_name} from {bucket}")
                return data

        except GoogleCloudError as e:
            logger.error(f"Download failed", error=str(e))
            raise

    async def delete(self, bucket: str, object_name: str) -> bool:
        """Delete object"""
        if not self.client:
            await self.connect()

        try:
            bucket_obj = self.client.bucket(bucket)
            blob = bucket_obj.blob(object_name)
            blob.delete()

            logger.info(f"Deleted {object_name} from {bucket}")
            return True

        except GoogleCloudError as e:
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
            bucket_obj = self.client.bucket(bucket)

            kwargs = {}
            if prefix:
                kwargs['prefix'] = prefix
            if not recursive:
                kwargs['delimiter'] = '/'
            if max_keys:
                kwargs['max_results'] = max_keys

            blobs = bucket_obj.list_blobs(**kwargs)

            results = []
            for blob in blobs:
                results.append({
                    'object_name': blob.name,
                    'size': blob.size,
                    'etag': blob.etag,
                    'last_modified': blob.updated,
                    'content_type': blob.content_type,
                    'generation': blob.generation
                })

            return results

        except GoogleCloudError as e:
            logger.error(f"List objects failed", error=str(e))
            return []

    async def get_metadata(self, bucket: str, object_name: str) -> Dict[str, Any]:
        """Get object metadata"""
        if not self.client:
            await self.connect()

        try:
            bucket_obj = self.client.bucket(bucket)
            blob = bucket_obj.blob(object_name)
            blob.reload()

            return {
                'object_name': blob.name,
                'size': blob.size,
                'etag': blob.etag,
                'last_modified': blob.updated,
                'content_type': blob.content_type,
                'metadata': blob.metadata or {},
                'generation': blob.generation
            }

        except GoogleCloudError as e:
            logger.error(f"Get metadata failed", error=str(e))
            return {}

    async def get_info(self) -> Dict[str, Any]:
        """Get GCS information"""
        if not self.client:
            await self.connect()

        try:
            buckets = list(self.client.list_buckets())

            return {
                'project_id': self.config.get('project_id'),
                'buckets': [b.name for b in buckets],
                'bucket_count': len(buckets)
            }

        except GoogleCloudError as e:
            logger.error(f"Get info failed", error=str(e))
            return {}

    async def create_bucket(self, bucket: str,
                           region: Optional[str] = None) -> bool:
        """Create bucket"""
        if not self.client:
            await self.connect()

        try:
            bucket_obj = self.client.bucket(bucket)

            if region:
                bucket_obj.location = region

            self.client.create_bucket(bucket_obj)

            logger.info(f"Created bucket {bucket}")
            return True

        except GoogleCloudError as e:
            logger.error(f"Create bucket failed", error=str(e))
            return False

    async def delete_bucket(self, bucket: str) -> bool:
        """Delete bucket"""
        if not self.client:
            await self.connect()

        try:
            bucket_obj = self.client.bucket(bucket)
            bucket_obj.delete()

            logger.info(f"Deleted bucket {bucket}")
            return True

        except GoogleCloudError as e:
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
                'creation_date': b.time_created,
                'location': b.location
            } for b in buckets]

        except GoogleCloudError as e:
            logger.error(f"List buckets failed", error=str(e))
            return []

    async def copy_object(self, source_bucket: str, source_object: str,
                         dest_bucket: str, dest_object: str) -> bool:
        """Copy object"""
        if not self.client:
            await self.connect()

        try:
            source_bucket_obj = self.client.bucket(source_bucket)
            source_blob = source_bucket_obj.blob(source_object)

            dest_bucket_obj = self.client.bucket(dest_bucket)

            source_bucket_obj.copy_blob(
                source_blob,
                dest_bucket_obj,
                dest_object
            )

            logger.info(f"Copied {source_object} to {dest_object}")
            return True

        except GoogleCloudError as e:
            logger.error(f"Copy failed", error=str(e))
            return False

    async def generate_signed_url(self, bucket: str, object_name: str,
                                  expires_seconds: int = 3600,
                                  method: str = 'GET') -> str:
        """Generate signed URL"""
        if not self.client:
            await self.connect()

        try:
            from datetime import timedelta

            bucket_obj = self.client.bucket(bucket)
            blob = bucket_obj.blob(object_name)

            url = blob.generate_signed_url(
                expiration=timedelta(seconds=expires_seconds),
                method=method
            )

            logger.info(f"Generated signed URL for {object_name}")
            return url

        except GoogleCloudError as e:
            logger.error(f"Signed URL generation failed", error=str(e))
            return ""
