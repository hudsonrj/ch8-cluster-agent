"""
JSON Extractor Agent - Specialized in JSON parsing and extraction
"""

import json
import jsonpath_ng
from jsonpath_ng.ext import parse as jsonpath_parse
from typing import Dict, Any, List, Optional, Union
import structlog
from pathlib import Path

from .base_extractor import BaseExtractorAgent

logger = structlog.get_logger()


class JSONExtractorAgent(BaseExtractorAgent):
    """
    Specialized agent for JSON extraction

    Capabilities:
    - Parse JSON from file or string
    - Extract using JSONPath
    - Deep nested extraction
    - Array filtering
    - Schema validation
    - JSON to CSV conversion
    """

    def _define_capabilities(self) -> List[str]:
        return [
            "parse_json",
            "jsonpath_query",
            "deep_extract",
            "filter_arrays",
            "validate_schema",
            "json_to_csv",
            "flatten_nested"
        ]

    def _get_supported_formats(self) -> List[str]:
        return [".json", ".jsonl", ".ndjson"]

    async def validate(self, source: Any) -> bool:
        """Validate if source is valid JSON"""
        try:
            if isinstance(source, (str, Path)):
                with open(source, 'r') as f:
                    json.load(f)
            else:
                json.loads(source if isinstance(source, str) else source.decode())
            return True
        except Exception as e:
            logger.error("JSON validation failed", error=str(e))
            return False

    async def extract(self, source: Union[str, Path],
                     query: Optional[Dict[str, Any]] = None) -> Any:
        """
        Extract data from JSON

        Args:
            source: JSON file path or string
            query: {
                'jsonpath': '$.data[*].items',
                'filter': lambda x: x['active'] == True,
                'flatten': True | False,
                'output_format': 'dict' | 'list' | 'csv'
            }

        Returns:
            Extracted data
        """
        query = query or {}

        # Parse JSON
        if isinstance(source, (str, Path)) and Path(source).exists():
            with open(source, 'r') as f:
                data = json.load(f)
        else:
            data = json.loads(source if isinstance(source, str) else source.decode())

        # Extract using JSONPath if provided
        if 'jsonpath' in query:
            data = await self._jsonpath_extract(data, query['jsonpath'])

        # Apply filter if provided
        if 'filter' in query:
            data = self._apply_filter(data, query['filter'])

        # Flatten if requested
        if query.get('flatten', False):
            data = self._flatten_dict(data)

        # Format output
        output_format = query.get('output_format', 'dict')
        if output_format == 'csv':
            return self._to_csv(data)

        return data

    async def _jsonpath_extract(self, data: Any, jsonpath: str) -> Any:
        """Extract using JSONPath"""
        jsonpath_expr = jsonpath_parse(jsonpath)
        matches = [match.value for match in jsonpath_expr.find(data)]

        # Return single item if only one match
        if len(matches) == 1:
            return matches[0]

        return matches

    def _apply_filter(self, data: Any, filter_func: callable) -> Any:
        """Apply filter function to data"""
        if isinstance(data, list):
            return [item for item in data if filter_func(item)]
        elif isinstance(data, dict):
            return {k: v for k, v in data.items() if filter_func(v)}
        return data

    def _flatten_dict(self, data: Dict[str, Any],
                     parent_key: str = '',
                     separator: str = '.') -> Dict[str, Any]:
        """Flatten nested dictionary"""
        items = []

        for k, v in data.items():
            new_key = f"{parent_key}{separator}{k}" if parent_key else k

            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, separator).items())
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        items.extend(
                            self._flatten_dict(item, f"{new_key}[{i}]", separator).items()
                        )
                    else:
                        items.append((f"{new_key}[{i}]", item))
            else:
                items.append((new_key, v))

        return dict(items)

    def _to_csv(self, data: Any) -> str:
        """Convert data to CSV format"""
        import csv
        import io

        output = io.StringIO()

        if isinstance(data, list) and len(data) > 0:
            if isinstance(data[0], dict):
                # List of dictionaries
                writer = csv.DictWriter(output, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
            else:
                # List of values
                writer = csv.writer(output)
                for item in data:
                    writer.writerow([item])
        elif isinstance(data, dict):
            # Single dictionary
            writer = csv.DictWriter(output, fieldnames=data.keys())
            writer.writeheader()
            writer.writerow(data)

        return output.getvalue()

    async def extract_nested(self, source: Union[str, Path],
                            path: str) -> Any:
        """Extract deeply nested value"""
        data = await self.extract(source)

        keys = path.split('.')
        for key in keys:
            if '[' in key and ']' in key:
                # Handle array index: data[0]
                name, index = key.split('[')
                index = int(index.rstrip(']'))
                data = data[name][index]
            else:
                data = data[key]

        return data

    async def extract_jsonl(self, source: Union[str, Path],
                           query: Optional[Dict[str, Any]] = None) -> List[Any]:
        """Extract from JSON Lines format"""
        results = []

        with open(source, 'r') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)

                    if query and 'filter' in query:
                        if query['filter'](data):
                            results.append(data)
                    else:
                        results.append(data)

        return results

    async def validate_json_schema(self, source: Union[str, Path],
                                   schema: Dict[str, Any]) -> bool:
        """Validate JSON against schema"""
        try:
            import jsonschema

            data = await self.extract(source)
            jsonschema.validate(instance=data, schema=schema)
            return True
        except Exception as e:
            logger.error("JSON schema validation failed", error=str(e))
            return False
