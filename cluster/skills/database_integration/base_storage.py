"""
Base Storage Agent - Abstract base for object storage integrations
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, BinaryIO
from pathlib import Path
import structlog

logger = structlog.get_logger()


class BaseStorageAgent(ABC):
    """
    Abstract base class for object storage agents

    All storage agents must implement:
    - connect() - Establish connection
    - disconnect() - Close connection
    - upload() - Upload object
    - download() - Download object
    - delete() - Delete object
    - list_objects() - List objects
    - get_metadata() - Get object metadata
    - get_info() - Get storage info
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.client = None
        self.is_connected = False
        self.capabilities = self._define_capabilities()

        logger.info(
            f"Initialized {self.__class__.__name__}",
            capabilities=self.capabilities
        )

    @abstractmethod
    def _define_capabilities(self) -> List[str]:
        """Define what operations this storage agent can perform"""
        pass

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish storage connection

        Returns:
            bool: True if connection successful
        """
        pass

    @abstractmethod
    async def disconnect(self):
        """Close storage connection"""
        pass

    @abstractmethod
    async def upload(self, bucket: str, object_name: str,
                    file_path: Optional[Union[str, Path]] = None,
                    data: Optional[bytes] = None,
                    metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Upload object to storage

        Args:
            bucket: Bucket/container name
            object_name: Object key/name
            file_path: Local file path to upload
            data: Binary data to upload (if not using file_path)
            metadata: Object metadata

        Returns:
            Upload result (etag, version, etc)
        """
        pass

    @abstractmethod
    async def download(self, bucket: str, object_name: str,
                      file_path: Optional[Union[str, Path]] = None) -> Union[bytes, str]:
        """
        Download object from storage

        Args:
            bucket: Bucket/container name
            object_name: Object key/name
            file_path: Local file path to save (if None, return bytes)

        Returns:
            Downloaded data as bytes or file path
        """
        pass

    @abstractmethod
    async def delete(self, bucket: str, object_name: str) -> bool:
        """
        Delete object from storage

        Args:
            bucket: Bucket/container name
            object_name: Object key/name

        Returns:
            bool: True if deleted successfully
        """
        pass

    @abstractmethod
    async def list_objects(self, bucket: str,
                          prefix: Optional[str] = None,
                          recursive: bool = True,
                          max_keys: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        List objects in storage

        Args:
            bucket: Bucket/container name
            prefix: Object prefix filter
            recursive: List recursively
            max_keys: Maximum number of keys to return

        Returns:
            List of object information dicts
        """
        pass

    @abstractmethod
    async def get_metadata(self, bucket: str, object_name: str) -> Dict[str, Any]:
        """
        Get object metadata

        Args:
            bucket: Bucket/container name
            object_name: Object key/name

        Returns:
            Object metadata
        """
        pass

    @abstractmethod
    async def get_info(self) -> Dict[str, Any]:
        """
        Get storage information

        Returns:
            Storage metadata (buckets, size, etc)
        """
        pass

    @abstractmethod
    async def create_bucket(self, bucket: str,
                           region: Optional[str] = None) -> bool:
        """
        Create a new bucket

        Args:
            bucket: Bucket name
            region: Region (if applicable)

        Returns:
            bool: True if created successfully
        """
        pass

    @abstractmethod
    async def delete_bucket(self, bucket: str) -> bool:
        """
        Delete a bucket

        Args:
            bucket: Bucket name

        Returns:
            bool: True if deleted successfully
        """
        pass

    @abstractmethod
    async def list_buckets(self) -> List[Dict[str, Any]]:
        """
        List all buckets

        Returns:
            List of bucket information
        """
        pass

    def get_capabilities(self) -> List[str]:
        """Get list of supported capabilities"""
        return self.capabilities

    async def health_check(self) -> Dict[str, Any]:
        """
        Check storage health

        Returns:
            Health status information
        """
        try:
            if not self.is_connected:
                await self.connect()

            info = await self.get_info()

            return {
                'healthy': True,
                'connected': self.is_connected,
                'info': info
            }
        except Exception as e:
            logger.error("Health check failed", error=str(e))
            return {
                'healthy': False,
                'connected': False,
                'error': str(e)
            }

    async def copy_object(self, source_bucket: str, source_object: str,
                         dest_bucket: str, dest_object: str) -> bool:
        """
        Copy object from one location to another

        Args:
            source_bucket: Source bucket
            source_object: Source object name
            dest_bucket: Destination bucket
            dest_object: Destination object name

        Returns:
            bool: True if copied successfully
        """
        # Default implementation: download then upload
        try:
            data = await self.download(source_bucket, source_object)
            await self.upload(dest_bucket, dest_object, data=data)
            return True
        except Exception as e:
            logger.error("Copy failed", error=str(e))
            return False
