"""
Base Extractor Agent - Abstract class for all data extractors
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger()


class BaseExtractorAgent(ABC):
    """
    Base class for all data extraction agents
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.agent_type = self.__class__.__name__
        self.capabilities = self._define_capabilities()

    @abstractmethod
    def _define_capabilities(self) -> List[str]:
        """Define what this extractor can do"""
        pass

    @abstractmethod
    async def extract(self, source: Any, query: Optional[Dict[str, Any]] = None) -> Any:
        """
        Extract data from source

        Args:
            source: File path, content string, or file-like object
            query: Optional extraction parameters (xpath, jq, filters, etc)

        Returns:
            Extracted data
        """
        pass

    @abstractmethod
    async def validate(self, source: Any) -> bool:
        """Validate if source can be processed by this extractor"""
        pass

    async def extract_with_transform(self, source: Any, query: Dict[str, Any],
                                     transform: Optional[callable] = None) -> Any:
        """
        Extract and optionally transform data

        Args:
            source: Data source
            query: Extraction query
            transform: Optional transformation function

        Returns:
            Extracted (and transformed) data
        """
        data = await self.extract(source, query)

        if transform:
            data = transform(data)

        return data

    def get_metadata(self) -> Dict[str, Any]:
        """Get extractor metadata"""
        return {
            'agent_type': self.agent_type,
            'capabilities': self.capabilities,
            'supported_formats': self._get_supported_formats()
        }

    @abstractmethod
    def _get_supported_formats(self) -> List[str]:
        """List of supported file formats"""
        pass
