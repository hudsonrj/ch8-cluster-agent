"""
Base Database Agent - Abstract base for all database integrations
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union
import structlog

logger = structlog.get_logger()


class BaseDatabaseAgent(ABC):
    """
    Abstract base class for database integration agents

    All database agents must implement:
    - connect() - Establish connection
    - disconnect() - Close connection
    - execute() - Execute operations
    - query() - Query data
    - insert() - Insert data
    - update() - Update data
    - delete() - Delete data
    - get_info() - Get database info
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.connection = None
        self.is_connected = False
        self.capabilities = self._define_capabilities()

        logger.info(
            f"Initialized {self.__class__.__name__}",
            capabilities=self.capabilities
        )

    @abstractmethod
    def _define_capabilities(self) -> List[str]:
        """Define what operations this database agent can perform"""
        pass

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish database connection

        Returns:
            bool: True if connection successful
        """
        pass

    @abstractmethod
    async def disconnect(self):
        """Close database connection"""
        pass

    @abstractmethod
    async def execute(self, operation: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Execute a database operation

        Args:
            operation: Operation to execute
            params: Operation parameters

        Returns:
            Operation result
        """
        pass

    @abstractmethod
    async def query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Query data from database

        Args:
            query: Query string
            params: Query parameters

        Returns:
            List of result rows
        """
        pass

    @abstractmethod
    async def insert(self, table: str, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Any:
        """
        Insert data into database

        Args:
            table: Target table/collection
            data: Data to insert (single dict or list of dicts)

        Returns:
            Insert result (IDs, count, etc)
        """
        pass

    @abstractmethod
    async def update(self, table: str, data: Dict[str, Any],
                    where: Optional[Dict[str, Any]] = None) -> int:
        """
        Update data in database

        Args:
            table: Target table/collection
            data: Data to update
            where: Update conditions

        Returns:
            Number of rows/documents updated
        """
        pass

    @abstractmethod
    async def delete(self, table: str, where: Dict[str, Any]) -> int:
        """
        Delete data from database

        Args:
            table: Target table/collection
            where: Delete conditions

        Returns:
            Number of rows/documents deleted
        """
        pass

    @abstractmethod
    async def get_info(self) -> Dict[str, Any]:
        """
        Get database information

        Returns:
            Database metadata (version, size, tables, etc)
        """
        pass

    def get_capabilities(self) -> List[str]:
        """Get list of supported capabilities"""
        return self.capabilities

    async def health_check(self) -> Dict[str, Any]:
        """
        Check database health

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
