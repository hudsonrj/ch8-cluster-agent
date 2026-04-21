"""
YAML Extractor Agent - Specialized in YAML parsing and extraction
"""

import yaml
from typing import Dict, Any, List, Optional, Union
import structlog
from pathlib import Path

from .base_extractor import BaseExtractorAgent

logger = structlog.get_logger()


class YAMLExtractorAgent(BaseExtractorAgent):
    """
    Specialized agent for YAML extraction

    Capabilities:
    - Parse YAML files
    - Extract nested values
    - Handle multi-document YAML
    - Validate YAML
    - YAML to JSON conversion
    - Safe loading
    """

    def _define_capabilities(self) -> List[str]:
        return [
            "parse_yaml",
            "extract_nested",
            "multi_document",
            "validate_yaml",
            "yaml_to_json",
            "safe_load"
        ]

    def _get_supported_formats(self) -> List[str]:
        return [".yaml", ".yml"]

    async def validate(self, source: Any) -> bool:
        """Validate if source is valid YAML"""
        try:
            if isinstance(source, (str, Path)) and Path(source).exists():
                with open(source, 'r') as f:
                    yaml.safe_load(f)
            else:
                yaml.safe_load(source)
            return True
        except Exception as e:
            logger.error("YAML validation failed", error=str(e))
            return False

    async def extract(self, source: Union[str, Path],
                     query: Optional[Dict[str, Any]] = None) -> Any:
        """
        Extract data from YAML

        Args:
            source: YAML file path or string
            query: {
                'path': 'config.database.host',  # Dot notation
                'multi_document': True | False,
                'safe_load': True | False,
                'output_format': 'dict' | 'json'
            }

        Returns:
            Extracted data
        """
        query = query or {}

        safe_load = query.get('safe_load', True)
        multi_doc = query.get('multi_document', False)

        # Load YAML
        if isinstance(source, (str, Path)) and Path(source).exists():
            with open(source, 'r') as f:
                if multi_doc:
                    data = list(yaml.safe_load_all(f) if safe_load else yaml.load_all(f, Loader=yaml.FullLoader))
                else:
                    data = yaml.safe_load(f) if safe_load else yaml.load(f, Loader=yaml.FullLoader)
        else:
            if multi_doc:
                data = list(yaml.safe_load_all(source) if safe_load else yaml.load_all(source, Loader=yaml.FullLoader))
            else:
                data = yaml.safe_load(source) if safe_load else yaml.load(source, Loader=yaml.FullLoader)

        # Extract specific path if provided
        if 'path' in query:
            data = self._extract_path(data, query['path'])

        # Format output
        output_format = query.get('output_format', 'dict')
        if output_format == 'json':
            import json
            return json.dumps(data, indent=2)

        return data

    def _extract_path(self, data: Any, path: str) -> Any:
        """Extract value using dot notation path"""
        keys = path.split('.')
        current = data

        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list):
                try:
                    index = int(key)
                    current = current[index]
                except (ValueError, IndexError):
                    return None
            else:
                return None

        return current

    async def extract_nested(self, source: Union[str, Path],
                            path: str) -> Any:
        """Extract deeply nested value"""
        return await self.extract(source, {'path': path})

    async def extract_all_documents(self, source: Union[str, Path]) -> List[Dict[str, Any]]:
        """Extract all documents from multi-document YAML"""
        return await self.extract(source, {'multi_document': True})

    async def yaml_to_json(self, source: Union[str, Path],
                          output_path: Optional[str] = None) -> Union[str, None]:
        """Convert YAML to JSON"""
        import json

        data = await self.extract(source)
        json_str = json.dumps(data, indent=2)

        if output_path:
            with open(output_path, 'w') as f:
                f.write(json_str)
            logger.info(f"Converted {source} to {output_path}")
            return None

        return json_str

    async def merge_yaml_files(self, sources: List[Union[str, Path]]) -> Dict[str, Any]:
        """Merge multiple YAML files"""
        merged = {}

        for source in sources:
            data = await self.extract(source)
            if isinstance(data, dict):
                merged = self._deep_merge(merged, data)

        return merged

    def _deep_merge(self, dict1: Dict, dict2: Dict) -> Dict:
        """Deep merge two dictionaries"""
        result = dict1.copy()

        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    async def validate_schema(self, source: Union[str, Path],
                             schema: Dict[str, Any]) -> bool:
        """Validate YAML against schema (basic)"""
        try:
            data = await self.extract(source)

            # Basic type checking
            for key, expected_type in schema.items():
                if key not in data:
                    return False
                if not isinstance(data[key], expected_type):
                    return False

            return True
        except Exception as e:
            logger.error("YAML schema validation failed", error=str(e))
            return False
