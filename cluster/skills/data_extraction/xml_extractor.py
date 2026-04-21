"""
XML Extractor Agent - Specialized in XML parsing and extraction
"""

import xml.etree.ElementTree as ET
from lxml import etree
from typing import Dict, Any, List, Optional, Union
import structlog
from pathlib import Path

from .base_extractor import BaseExtractorAgent

logger = structlog.get_logger()


class XMLExtractorAgent(BaseExtractorAgent):
    """
    Specialized agent for XML extraction

    Capabilities:
    - Parse XML from file or string
    - Extract using XPath
    - Convert XML to dict
    - Validate XML against schema
    - Handle namespaces
    - Extract attributes
    """

    def _define_capabilities(self) -> List[str]:
        return [
            "parse_xml",
            "xpath_query",
            "extract_elements",
            "extract_attributes",
            "xml_to_dict",
            "validate_schema",
            "handle_namespaces"
        ]

    def _get_supported_formats(self) -> List[str]:
        return [".xml", ".xsd", ".xsl"]

    async def validate(self, source: Any) -> bool:
        """Validate if source is valid XML"""
        try:
            if isinstance(source, (str, Path)):
                tree = etree.parse(str(source))
            else:
                tree = etree.fromstring(source)
            return True
        except Exception as e:
            logger.error("XML validation failed", error=str(e))
            return False

    async def extract(self, source: Union[str, Path],
                     query: Optional[Dict[str, Any]] = None) -> Any:
        """
        Extract data from XML

        Args:
            source: XML file path or string
            query: {
                'xpath': '//element[@attr="value"]',
                'namespaces': {'ns': 'http://example.com'},
                'output_format': 'dict' | 'list' | 'text',
                'extract_attributes': True | False
            }

        Returns:
            Extracted data in requested format
        """
        query = query or {}

        # Parse XML
        if isinstance(source, (str, Path)) and Path(source).exists():
            tree = etree.parse(str(source))
            root = tree.getroot()
        else:
            root = etree.fromstring(source if isinstance(source, bytes) else source.encode())

        # Extract using XPath if provided
        if 'xpath' in query:
            return await self._xpath_extract(root, query)

        # Default: convert to dict
        return self._xml_to_dict(root)

    async def _xpath_extract(self, root: etree.Element,
                            query: Dict[str, Any]) -> Any:
        """Extract using XPath"""
        xpath = query['xpath']
        namespaces = query.get('namespaces', {})
        output_format = query.get('output_format', 'list')
        extract_attrs = query.get('extract_attributes', False)

        # Execute XPath
        results = root.xpath(xpath, namespaces=namespaces)

        # Format output
        if output_format == 'text':
            return [self._element_to_text(r) for r in results]

        elif output_format == 'dict':
            return [self._element_to_dict(r, extract_attrs) for r in results]

        else:  # list
            return results

    def _element_to_text(self, element: etree.Element) -> str:
        """Convert element to text"""
        if isinstance(element, str):
            return element
        return etree.tostring(element, encoding='unicode', method='text').strip()

    def _element_to_dict(self, element: etree.Element,
                        extract_attrs: bool = True) -> Dict[str, Any]:
        """Convert element to dictionary"""
        result = {}

        # Extract attributes
        if extract_attrs and element.attrib:
            result['@attributes'] = dict(element.attrib)

        # Extract text content
        if element.text and element.text.strip():
            result['text'] = element.text.strip()

        # Extract children
        for child in element:
            child_dict = self._element_to_dict(child, extract_attrs)

            # Handle multiple children with same tag
            if child.tag in result:
                if not isinstance(result[child.tag], list):
                    result[child.tag] = [result[child.tag]]
                result[child.tag].append(child_dict)
            else:
                result[child.tag] = child_dict

        return result

    def _xml_to_dict(self, root: etree.Element) -> Dict[str, Any]:
        """Convert entire XML to dictionary"""
        return {root.tag: self._element_to_dict(root, extract_attrs=True)}

    async def extract_all_elements(self, source: Union[str, Path],
                                   tag_name: str) -> List[Dict[str, Any]]:
        """Extract all elements with specific tag"""
        return await self.extract(source, {
            'xpath': f'.//{tag_name}',
            'output_format': 'dict'
        })

    async def extract_by_attribute(self, source: Union[str, Path],
                                   tag_name: str,
                                   attr_name: str,
                                   attr_value: str) -> List[Dict[str, Any]]:
        """Extract elements by attribute value"""
        return await self.extract(source, {
            'xpath': f'.//{tag_name}[@{attr_name}="{attr_value}"]',
            'output_format': 'dict'
        })

    async def validate_against_schema(self, source: Union[str, Path],
                                     schema_path: str) -> bool:
        """Validate XML against XSD schema"""
        try:
            schema = etree.XMLSchema(etree.parse(schema_path))

            if isinstance(source, (str, Path)) and Path(source).exists():
                doc = etree.parse(str(source))
            else:
                doc = etree.fromstring(source if isinstance(source, bytes) else source.encode())

            return schema.validate(doc)
        except Exception as e:
            logger.error("Schema validation failed", error=str(e))
            return False
