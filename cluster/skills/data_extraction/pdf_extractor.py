"""
PDF Extractor Agent - Specialized in PDF text extraction
"""

import PyPDF2
from pdfminer.high_level import extract_text, extract_pages
from pdfminer.layout import LTTextBox, LTTextLine, LTChar
from typing import Dict, Any, List, Optional, Union
import structlog
from pathlib import Path

from .base_extractor import BaseExtractorAgent

logger = structlog.get_logger()


class PDFExtractorAgent(BaseExtractorAgent):
    """
    Specialized agent for PDF extraction

    Capabilities:
    - Extract text from PDF
    - Extract by page
    - Extract with layout
    - Extract metadata
    - Extract tables (basic)
    - Extract images (basic)
    - Password-protected PDFs
    """

    def _define_capabilities(self) -> List[str]:
        return [
            "extract_text",
            "extract_by_page",
            "extract_layout",
            "extract_metadata",
            "extract_tables",
            "handle_encrypted",
            "page_count"
        ]

    def _get_supported_formats(self) -> List[str]:
        return [".pdf"]

    async def validate(self, source: Any) -> bool:
        """Validate if source is valid PDF"""
        try:
            if isinstance(source, (str, Path)):
                with open(source, 'rb') as f:
                    PyPDF2.PdfReader(f)
            return True
        except Exception as e:
            logger.error("PDF validation failed", error=str(e))
            return False

    async def extract(self, source: Union[str, Path],
                     query: Optional[Dict[str, Any]] = None) -> Any:
        """
        Extract data from PDF

        Args:
            source: PDF file path
            query: {
                'pages': [0, 1, 2] | 'all',  # Specific pages or all
                'password': 'secret',  # For encrypted PDFs
                'with_layout': True | False,
                'output_format': 'text' | 'dict'
            }

        Returns:
            Extracted text
        """
        query = query or {}

        pages = query.get('pages', 'all')
        password = query.get('password', None)
        with_layout = query.get('with_layout', False)
        output_format = query.get('output_format', 'text')

        if with_layout:
            return await self._extract_with_layout(source, pages)

        # Simple text extraction
        if pages == 'all':
            text = extract_text(str(source), password=password)
        else:
            # Extract specific pages
            text = await self._extract_pages(source, pages, password)

        if output_format == 'dict':
            return {
                'text': text,
                'num_chars': len(text),
                'num_words': len(text.split()),
                'num_lines': len(text.splitlines())
            }

        return text

    async def _extract_pages(self, source: Union[str, Path],
                            pages: List[int],
                            password: Optional[str] = None) -> str:
        """Extract text from specific pages"""
        with open(source, 'rb') as f:
            reader = PyPDF2.PdfReader(f)

            if reader.is_encrypted and password:
                reader.decrypt(password)

            texts = []
            for page_num in pages:
                if 0 <= page_num < len(reader.pages):
                    page = reader.pages[page_num]
                    texts.append(page.extract_text())

            return '\n\n'.join(texts)

    async def _extract_with_layout(self, source: Union[str, Path],
                                   pages: Union[str, List[int]]) -> Dict[str, Any]:
        """Extract text with layout information"""
        result = {
            'pages': []
        }

        for page_layout in extract_pages(str(source)):
            page_data = {
                'page_num': len(result['pages']),
                'width': page_layout.width,
                'height': page_layout.height,
                'elements': []
            }

            for element in page_layout:
                if isinstance(element, (LTTextBox, LTTextLine)):
                    page_data['elements'].append({
                        'type': 'text',
                        'text': element.get_text().strip(),
                        'bbox': element.bbox,
                        'x0': element.x0,
                        'y0': element.y0,
                        'x1': element.x1,
                        'y1': element.y1
                    })

            result['pages'].append(page_data)

            # If specific pages requested, stop when done
            if pages != 'all' and len(result['pages']) >= len(pages):
                break

        return result

    async def extract_text(self, source: Union[str, Path]) -> str:
        """Extract all text from PDF"""
        return await self.extract(source, {'output_format': 'text'})

    async def extract_page(self, source: Union[str, Path],
                          page_num: int) -> str:
        """Extract text from specific page"""
        return await self.extract(source, {
            'pages': [page_num],
            'output_format': 'text'
        })

    async def get_metadata(self, source: Union[str, Path]) -> Dict[str, Any]:
        """Extract PDF metadata"""
        with open(source, 'rb') as f:
            reader = PyPDF2.PdfReader(f)

            metadata = reader.metadata if reader.metadata else {}

            return {
                'title': metadata.get('/Title', ''),
                'author': metadata.get('/Author', ''),
                'subject': metadata.get('/Subject', ''),
                'creator': metadata.get('/Creator', ''),
                'producer': metadata.get('/Producer', ''),
                'creation_date': metadata.get('/CreationDate', ''),
                'modification_date': metadata.get('/ModDate', ''),
                'num_pages': len(reader.pages),
                'is_encrypted': reader.is_encrypted
            }

    async def get_page_count(self, source: Union[str, Path]) -> int:
        """Get number of pages in PDF"""
        with open(source, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            return len(reader.pages)

    async def search_text(self, source: Union[str, Path],
                         search_term: str) -> List[Dict[str, Any]]:
        """Search for text in PDF"""
        with open(source, 'rb') as f:
            reader = PyPDF2.PdfReader(f)

            results = []
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if search_term in text:
                    # Find line containing search term
                    lines = text.split('\n')
                    for line_num, line in enumerate(lines):
                        if search_term in line:
                            results.append({
                                'page': page_num,
                                'line': line_num,
                                'text': line.strip(),
                                'context': lines[max(0, line_num-1):line_num+2]
                            })

            return results

    async def extract_page_range(self, source: Union[str, Path],
                                 start_page: int,
                                 end_page: int) -> str:
        """Extract text from page range"""
        pages = list(range(start_page, end_page + 1))
        return await self.extract(source, {'pages': pages})

    async def is_searchable(self, source: Union[str, Path]) -> bool:
        """Check if PDF is searchable (has extractable text)"""
        text = await self.extract_text(source)
        return len(text.strip()) > 0
