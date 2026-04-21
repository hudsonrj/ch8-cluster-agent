"""
XPath Extractor Agent - Specialized in XPath queries for XML/HTML
"""

from lxml import etree, html
from typing import Dict, Any, List, Optional, Union
import structlog
from pathlib import Path
import requests

from .base_extractor import BaseExtractorAgent

logger = structlog.get_logger()


class XPathExtractorAgent(BaseExtractorAgent):
    """
    Specialized agent for XPath extraction

    Capabilities:
    - Execute complex XPath queries
    - Extract from XML and HTML
    - Handle namespaces
    - Extract text, attributes, elements
    - Web scraping support
    - Multiple extraction patterns
    """

    def _define_capabilities(self) -> List[str]:
        return [
            "xpath_query",
            "extract_from_xml",
            "extract_from_html",
            "handle_namespaces",
            "extract_text",
            "extract_attributes",
            "web_scraping",
            "batch_extraction"
        ]

    def _get_supported_formats(self) -> List[str]:
        return [".xml", ".html", ".xhtml"]

    async def validate(self, source: Any) -> bool:
        """Validate if source can be parsed"""
        try:
            if isinstance(source, str) and source.startswith('http'):
                response = requests.get(source)
                content = response.content
            elif isinstance(source, (str, Path)) and Path(source).exists():
                with open(source, 'rb') as f:
                    content = f.read()
            else:
                content = source if isinstance(source, bytes) else source.encode()

            etree.fromstring(content)
            return True
        except:
            try:
                html.fromstring(content)
                return True
            except Exception as e:
                logger.error("XPath validation failed", error=str(e))
                return False

    async def extract(self, source: Union[str, Path],
                     query: Optional[Dict[str, Any]] = None) -> Any:
        """
        Extract data using XPath

        Args:
            source: File path, URL, or content string
            query: {
                'xpath': '//div[@class="item"]/text()',
                'xpath_list': ['//title/text()', '//meta/@content'],
                'namespaces': {'ns': 'http://example.com'},
                'content_type': 'xml' | 'html',
                'output_format': 'text' | 'element' | 'dict'
            }

        Returns:
            Extracted data
        """
        query = query or {}

        # Parse content
        tree = await self._parse_content(source, query.get('content_type', 'xml'))

        # Execute single XPath
        if 'xpath' in query:
            return await self._execute_xpath(
                tree,
                query['xpath'],
                query.get('namespaces', {}),
                query.get('output_format', 'text')
            )

        # Execute multiple XPaths
        elif 'xpath_list' in query:
            results = {}
            for xpath_expr in query['xpath_list']:
                results[xpath_expr] = await self._execute_xpath(
                    tree,
                    xpath_expr,
                    query.get('namespaces', {}),
                    query.get('output_format', 'text')
                )
            return results

        # No XPath provided, return parsed tree
        return tree

    async def _parse_content(self, source: Union[str, Path],
                            content_type: str) -> etree.Element:
        """Parse content into tree"""
        # Get content
        if isinstance(source, str) and source.startswith('http'):
            # URL
            response = requests.get(source)
            content = response.content
        elif isinstance(source, (str, Path)) and Path(source).exists():
            # File
            with open(source, 'rb') as f:
                content = f.read()
        else:
            # String content
            content = source if isinstance(source, bytes) else source.encode()

        # Parse
        if content_type == 'html':
            return html.fromstring(content)
        else:
            return etree.fromstring(content)

    async def _execute_xpath(self, tree: etree.Element,
                            xpath: str,
                            namespaces: Dict[str, str],
                            output_format: str) -> Any:
        """Execute XPath query"""
        results = tree.xpath(xpath, namespaces=namespaces)

        if output_format == 'text':
            return [self._to_text(r) for r in results]
        elif output_format == 'element':
            return results
        elif output_format == 'dict':
            return [self._element_to_dict(r) for r in results if isinstance(r, etree._Element)]
        else:
            return results

    def _to_text(self, item: Any) -> str:
        """Convert item to text"""
        if isinstance(item, str):
            return item
        elif isinstance(item, etree._Element):
            return etree.tostring(item, encoding='unicode', method='text').strip()
        else:
            return str(item)

    def _element_to_dict(self, element: etree._Element) -> Dict[str, Any]:
        """Convert element to dictionary"""
        result = {
            'tag': element.tag,
            'attributes': dict(element.attrib)
        }

        if element.text and element.text.strip():
            result['text'] = element.text.strip()

        children = list(element)
        if children:
            result['children'] = [self._element_to_dict(child) for child in children]

        return result

    async def extract_all_text(self, source: Union[str, Path],
                              xpath: str = '//text()') -> List[str]:
        """Extract all text from elements matching XPath"""
        return await self.extract(source, {
            'xpath': xpath,
            'output_format': 'text'
        })

    async def extract_attributes(self, source: Union[str, Path],
                                xpath: str,
                                attribute: str) -> List[str]:
        """Extract specific attribute from elements"""
        full_xpath = f"{xpath}/@{attribute}"
        return await self.extract(source, {
            'xpath': full_xpath,
            'output_format': 'text'
        })

    async def extract_links(self, source: Union[str, Path],
                           base_url: Optional[str] = None) -> List[str]:
        """Extract all links from HTML/XML"""
        links = await self.extract(source, {
            'xpath': '//a/@href | //link/@href',
            'content_type': 'html',
            'output_format': 'text'
        })

        # Make absolute URLs if base_url provided
        if base_url:
            from urllib.parse import urljoin
            links = [urljoin(base_url, link) for link in links]

        return links

    async def extract_tables(self, source: Union[str, Path]) -> List[List[List[str]]]:
        """Extract all tables from HTML"""
        tree = await self._parse_content(source, 'html')
        tables = tree.xpath('//table')

        result = []
        for table in tables:
            rows = []
            for tr in table.xpath('.//tr'):
                cells = [
                    self._to_text(cell)
                    for cell in tr.xpath('.//td | .//th')
                ]
                rows.append(cells)
            result.append(rows)

        return result

    async def extract_with_patterns(self, source: Union[str, Path],
                                   patterns: Dict[str, str]) -> Dict[str, Any]:
        """
        Extract multiple patterns

        Args:
            patterns: {
                'title': '//title/text()',
                'description': '//meta[@name="description"]/@content',
                'links': '//a/@href'
            }

        Returns:
            Dictionary with extracted values
        """
        tree = await self._parse_content(source, 'html')

        results = {}
        for key, xpath in patterns.items():
            results[key] = tree.xpath(xpath)

        return results

    async def scrape_website(self, url: str,
                            patterns: Dict[str, str]) -> Dict[str, Any]:
        """
        Scrape website using XPath patterns

        Example:
            patterns = {
                'title': '//h1/text()',
                'price': '//span[@class="price"]/text()',
                'description': '//div[@class="desc"]/text()'
            }
        """
        return await self.extract_with_patterns(url, patterns)

    async def extract_with_conditions(self, source: Union[str, Path],
                                     element: str,
                                     conditions: List[tuple]) -> List[etree._Element]:
        """
        Extract elements with multiple conditions

        Args:
            element: Element name (e.g., 'div', 'span')
            conditions: [('@class', 'item'), ('text()', 'contains', 'search')]
        """
        xpath_conditions = []
        for condition in conditions:
            if len(condition) == 2:
                attr, value = condition
                xpath_conditions.append(f"{attr}='{value}'")
            elif len(condition) == 3:
                attr, op, value = condition
                if op == 'contains':
                    xpath_conditions.append(f"contains({attr}, '{value}')")

        xpath = f"//{element}[{' and '.join(xpath_conditions)}]"

        return await self.extract(source, {
            'xpath': xpath,
            'output_format': 'element'
        })
