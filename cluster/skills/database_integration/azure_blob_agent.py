"""
Azure Blob Storage Integration Agent - Full operations for Azure Blob
"""

from azure.storage.blob.aio import BlobServiceClient
from azure.core.exceptions import AzureError
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import structlog

from .base_storage import BaseStorageAgent

logger = structlog.get_logger()


class AzureBlobAgent(BaseStorageAgent):
    """
    Azure Blob Storage integration agent with full capabilities

    Capabilities:
    - Blob operations (upload, download, delete)
    - Container management
    - SAS URLs
    - Blob metadata
    - Copy operations
    - Blob leases
    - Snapshots
    - Tier management (Hot/Cool/Archive)
    """

    def _define_capabilities(self) -> List[str]:
        return [
            "connect",
            "upload",
            "download",
            "delete",
            "list_blobs",
            "container_management",
            "sas_urls",
            "metadata",
            "copy_blobs",
            "leases",
            "snapshots",
            "tier_management"
        ]

    async def connect(self) -> bool:
        """Establish Azure Blob connection"""
        try:
            if self.client:
                return True

            connection_string = self.config.get('connection_string')
            account_url = self.config.get('account_url')
            account_key = self.config.get('account_key')

            if connection_string:
                self.client = BlobServiceClient.from_connection_string(connection_string)
            elif account_url and account_key:
                self.client = BlobServiceClient(
                    account_url=account_url,
                    credential=account_key
                )
            else:
                raise ValueError("Either connection_string or (account_url + account_key) required")

            # Test connection
            await self.client.get_service_properties()

            self.is_connected = True
            logger.info("Connected to Azure Blob Storage")
            return True

        except Exception as e:
            logger.error("Azure Blob connection failed", error=str(e))
            self.is_connected = False
            return False

    async def disconnect(self):
        """Close Azure Blob connection"""
        if self.client:
            await self.client.close()
            self.client = None
            self.is_connected = False
            logger.info("Disconnected from Azure Blob Storage")

    async def upload(self, bucket: str, object_name: str,
                    file_path: Optional[Union[str, Path]] = None,
                    data: Optional[bytes] = None,
                    metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Upload blob"""
        if not self.client:
            await self.connect()

        try:
            # In Azure, bucket = container
            container_client = self.client.get_container_client(bucket)
            blob_client = container_client.get_blob_client(object_name)

            if file_path:
                # Upload from file
                with open(file_path, 'rb') as f:
                    await blob_client.upload_blob(f, metadata=metadata, overwrite=True)
            elif data:
                # Upload from bytes
                await blob_client.upload_blob(data, metadata=metadata, overwrite=True)
            else:
                raise ValueError("Either file_path or data must be provided")

            # Get blob properties
            props = await blob_client.get_blob_properties()

            logger.info(f"Uploaded {object_name} to {bucket}")
            return {
                'etag': props.etag,
                'version_id': props.version_id,
                'bucket': bucket,
                'object_name': object_name
            }

        except AzureError as e:
            logger.error(f"Upload failed", error=str(e))
            raise

    async def download(self, bucket: str, object_name: str,
                      file_path: Optional[Union[str, Path]] = None) -> Union[bytes, str]:
        """Download blob"""
        if not self.client:
            await self.connect()

        try:
            container_client = self.client.get_container_client(bucket)
            blob_client = container_client.get_blob_client(object_name)

            if file_path:
                # Download to file
                with open(file_path, 'wb') as f:
                    stream = await blob_client.download_blob()
                    data = await stream.readall()
                    f.write(data)

                logger.info(f"Downloaded {object_name} to {file_path}")
                return str(file_path)
            else:
                # Download to memory
                stream = await blob_client.download_blob()
                data = await stream.readall()

                logger.info(f"Downloaded {object_name} from {bucket}")
                return data

        except AzureError as e:
            logger.error(f"Download failed", error=str(e))
            raise

    async def delete(self, bucket: str, object_name: str) -> bool:
        """Delete blob"""
        if not self.client:
            await self.connect()

        try:
            container_client = self.client.get_container_client(bucket)
            blob_client = container_client.get_blob_client(object_name)

            await blob_client.delete_blob()

            logger.info(f"Deleted {object_name} from {bucket}")
            return True

        except AzureError as e:
            logger.error(f"Delete failed", error=str(e))
            return False

    async def list_objects(self, bucket: str,
                          prefix: Optional[str] = None,
                          recursive: bool = True,
                          max_keys: Optional[int] = None) -> List[Dict[str, Any]]:
        """List blobs in container"""
        if not self.client:
            await self.connect()

        try:
            container_client = self.client.get_container_client(bucket)

            kwargs = {}
            if prefix:
                kwargs['name_starts_with'] = prefix

            blobs = container_client.list_blobs(**kwargs)

            results = []
            async for blob in blobs:
                results.append({
                    'object_name': blob.name,
                    'size': blob.size,
                    'etag': blob.etag,
                    'last_modified': blob.last_modified,
                    'content_type': blob.content_settings.content_type if blob.content_settings else None,
                    'blob_type': blob.blob_type
                })

                if max_keys and len(results) >= max_keys:
                    break

            return results

        except AzureError as e:
            logger.error(f"List blobs failed", error=str(e))
            return []

    async def get_metadata(self, bucket: str, object_name: str) -> Dict[str, Any]:
        """Get blob metadata"""
        if not self.client:
            await self.connect()

        try:
            container_client = self.client.get_container_client(bucket)
            blob_client = container_client.get_blob_client(object_name)

            props = await blob_client.get_blob_properties()

            return {
                'object_name': object_name,
                'size': props.size,
                'etag': props.etag,
                'last_modified': props.last_modified,
                'content_type': props.content_settings.content_type if props.content_settings else None,
                'metadata': props.metadata or {},
                'version_id': props.version_id,
                'blob_tier': props.blob_tier
            }

        except AzureError as e:
            logger.error(f"Get metadata failed", error=str(e))
            return {}

    async def get_info(self) -> Dict[str, Any]:
        """Get Azure Blob Storage information"""
        if not self.client:
            await self.connect()

        try:
            containers = []
            async for container in self.client.list_containers():
                containers.append(container.name)

            return {
                'account_name': self.config.get('account_name', 'unknown'),
                'containers': containers,
                'container_count': len(containers)
            }

        except AzureError as e:
            logger.error(f"Get info failed", error=str(e))
            return {}

    async def create_bucket(self, bucket: str,
                           region: Optional[str] = None) -> bool:
        """Create container"""
        if not self.client:
            await self.connect()

        try:
            container_client = self.client.get_container_client(bucket)
            await container_client.create_container()

            logger.info(f"Created container {bucket}")
            return True

        except AzureError as e:
            logger.error(f"Create container failed", error=str(e))
            return False

    async def delete_bucket(self, bucket: str) -> bool:
        """Delete container"""
        if not self.client:
            await self.connect()

        try:
            container_client = self.client.get_container_client(bucket)
            await container_client.delete_container()

            logger.info(f"Deleted container {bucket}")
            return True

        except AzureError as e:
            logger.error(f"Delete container failed", error=str(e))
            return False

    async def list_buckets(self) -> List[Dict[str, Any]]:
        """List all containers"""
        if not self.client:
            await self.connect()

        try:
            containers = []
            async for container in self.client.list_containers():
                containers.append({
                    'name': container.name,
                    'creation_date': container.last_modified
                })

            return containers

        except AzureError as e:
            logger.error(f"List containers failed", error=str(e))
            return []

    async def copy_object(self, source_bucket: str, source_object: str,
                         dest_bucket: str, dest_object: str) -> bool:
        """Copy blob"""
        if not self.client:
            await self.connect()

        try:
            source_container_client = self.client.get_container_client(source_bucket)
            source_blob_client = source_container_client.get_blob_client(source_object)

            dest_container_client = self.client.get_container_client(dest_bucket)
            dest_blob_client = dest_container_client.get_blob_client(dest_object)

            source_url = source_blob_client.url
            await dest_blob_client.start_copy_from_url(source_url)

            logger.info(f"Copied {source_object} to {dest_object}")
            return True

        except AzureError as e:
            logger.error(f"Copy failed", error=str(e))
            return False

    async def generate_sas_url(self, bucket: str, object_name: str,
                              expires_seconds: int = 3600,
                              permission: str = 'r') -> str:
        """Generate SAS URL"""
        if not self.client:
            await self.connect()

        try:
            from datetime import datetime, timedelta
            from azure.storage.blob import generate_blob_sas, BlobSasPermissions

            container_client = self.client.get_container_client(bucket)
            blob_client = container_client.get_blob_client(object_name)

            # Get account name and key
            account_name = self.config.get('account_name')
            account_key = self.config.get('account_key')

            if not account_name or not account_key:
                logger.error("account_name and account_key required for SAS URLs")
                return ""

            # Set permissions
            permissions = BlobSasPermissions(read=('r' in permission))

            sas_token = generate_blob_sas(
                account_name=account_name,
                container_name=bucket,
                blob_name=object_name,
                account_key=account_key,
                permission=permissions,
                expiry=datetime.utcnow() + timedelta(seconds=expires_seconds)
            )

            url = f"{blob_client.url}?{sas_token}"

            logger.info(f"Generated SAS URL for {object_name}")
            return url

        except AzureError as e:
            logger.error(f"SAS URL generation failed", error=str(e))
            return ""
