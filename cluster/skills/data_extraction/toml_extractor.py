"""
TOML Extractor Agent - Specialized in TOML parsing and extraction
"""

import tomli
import tomli_w
from typing import Dict, Any, List, Optional, Union
import structlog
from pathlib import Path

from .base_extractor import BaseExtractorAgent

logger = structlog.get_logger()


class TOMLExtractorAgent(BaseExtractorAgent):
    """
    Specialized agent for TOML extraction

    Capabilities:
    - Parse TOML files
    - Extract nested values
    - Handle arrays and tables
    - TOML to JSON/YAML conversion
    - Validate TOML
    """

    def _define_capabilities(self) -> List[str]:
        return [
            "parse_toml",
            "extract_nested",
            "handle_tables",
            "toml_to_json",
            "toml_to_yaml",
            "validate_toml"
        ]

    def _get_supported_formats(self) -> List[str]:
        return [".toml"]

    async def validate(self, source: Any) -> bool:
        """Validate if source is valid TOML"""
        try:
            if isinstance(source, (str, Path)) and Path(source).exists():
                with open(source, 'rb') as f:
                    tomli.load(f)
            else:
                tomli.loads(source if isinstance(source, str) else source.decode())
            return True
        except Exception as e:
            logger.error("TOML validation failed", error=str(e))
            return False

    async def extract(self, source: Union[str, Path],
                     query: Optional[Dict[str, Any]] = None) -> Any:
        """
        Extract data from TOML

        Args:
            source: TOML file path or string
            query: {
                'path': 'database.connections.primary',
                'output_format': 'dict' | 'json' | 'yaml'
            }

        Returns:
            Extracted data
        """
        query = query or {}

        # Load TOML
        if isinstance(source, (str, Path)) and Path(source).exists():
            with open(source, 'rb') as f:
                data = tomli.load(f)
        else:
            content = source if isinstance(source, str) else source.decode()
            data = tomli.loads(content)

        # Extract specific path if provided
        if 'path' in query:
            data = self._extract_path(data, query['path'])

        # Format output
        output_format = query.get('output_format', 'dict')

        if output_format == 'json':
            import json
            return json.dumps(data, indent=2)

        elif output_format == 'yaml':
            import yaml
            return yaml.dump(data, default_flow_style=False)

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

    async def extract_table(self, source: Union[str, Path],
                           table_name: str) -> Dict[str, Any]:
        """Extract specific table"""
        data = await self.extract(source)
        return data.get(table_name, {})

    async def extract_array(self, source: Union[str, Path],
                           array_path: str) -> List[Any]:
        """Extract array"""
        data = await self.extract(source, {'path': array_path})
        return data if isinstance(data, list) else []

    async def toml_to_json(self, source: Union[str, Path],
                          output_path: Optional[str] = None) -> Union[str, None]:
        """Convert TOML to JSON"""
        import json

        data = await self.extract(source)
        json_str = json.dumps(data, indent=2)

        if output_path:
            with open(output_path, 'w') as f:
                f.write(json_str)
            logger.info(f"Converted {source} to {output_path}")
            return None

        return json_str

    async def toml_to_yaml(self, source: Union[str, Path],
                          output_path: Optional[str] = None) -> Union[str, None]:
        """Convert TOML to YAML"""
        import yaml

        data = await self.extract(source)
        yaml_str = yaml.dump(data, default_flow_style=False)

        if output_path:
            with open(output_path, 'w') as f:
                f.write(yaml_str)
            logger.info(f"Converted {source} to {output_path}")
            return None

        return yaml_str

    async def get_all_tables(self, source: Union[str, Path]) -> List[str]:
        """Get list of all table names"""
        data = await self.extract(source)

        tables = []
        for key, value in data.items():
            if isinstance(value, dict):
                tables.append(key)

        return tables

    async def merge_toml_files(self, sources: List[Union[str, Path]]) -> Dict[str, Any]:
        """Merge multiple TOML files"""
        merged = {}

        for source in sources:
            data = await self.extract(source)
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
