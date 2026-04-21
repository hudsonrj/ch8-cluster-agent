"""
CSV Extractor Agent - Specialized in CSV parsing and extraction
"""

import csv
import pandas as pd
from typing import Dict, Any, List, Optional, Union
import structlog
from pathlib import Path
import io

from .base_extractor import BaseExtractorAgent

logger = structlog.get_logger()


class CSVExtractorAgent(BaseExtractorAgent):
    """
    Specialized agent for CSV extraction

    Capabilities:
    - Parse CSV with various delimiters
    - Extract specific columns
    - Filter rows
    - Aggregate data
    - Handle large files (chunked reading)
    - Detect encoding
    - Handle malformed CSV
    """

    def _define_capabilities(self) -> List[str]:
        return [
            "parse_csv",
            "extract_columns",
            "filter_rows",
            "aggregate_data",
            "chunked_reading",
            "detect_encoding",
            "handle_malformed",
            "csv_to_dict",
            "csv_to_json"
        ]

    def _get_supported_formats(self) -> List[str]:
        return [".csv", ".tsv", ".txt"]

    async def validate(self, source: Any) -> bool:
        """Validate if source is valid CSV"""
        try:
            if isinstance(source, (str, Path)):
                df = pd.read_csv(source, nrows=1)
            else:
                df = pd.read_csv(io.StringIO(source), nrows=1)
            return len(df.columns) > 0
        except Exception as e:
            logger.error("CSV validation failed", error=str(e))
            return False

    async def extract(self, source: Union[str, Path],
                     query: Optional[Dict[str, Any]] = None) -> Any:
        """
        Extract data from CSV

        Args:
            source: CSV file path or string
            query: {
                'columns': ['col1', 'col2'],  # Specific columns
                'filter': lambda row: row['col'] > 10,  # Row filter
                'chunksize': 1000,  # For large files
                'delimiter': ',',  # CSV delimiter
                'encoding': 'utf-8',  # File encoding
                'output_format': 'dict' | 'list' | 'dataframe'
            }

        Returns:
            Extracted data
        """
        query = query or {}

        # Parse options
        columns = query.get('columns', None)
        delimiter = query.get('delimiter', ',')
        encoding = query.get('encoding', 'utf-8')
        chunksize = query.get('chunksize', None)
        output_format = query.get('output_format', 'dict')

        # Read CSV
        if chunksize:
            # Chunked reading for large files
            chunks = []
            for chunk in pd.read_csv(
                source,
                usecols=columns,
                delimiter=delimiter,
                encoding=encoding,
                chunksize=chunksize
            ):
                if 'filter' in query:
                    chunk = chunk[chunk.apply(query['filter'], axis=1)]
                chunks.append(chunk)

            df = pd.concat(chunks, ignore_index=True)
        else:
            # Normal reading
            df = pd.read_csv(
                source,
                usecols=columns,
                delimiter=delimiter,
                encoding=encoding
            )

            if 'filter' in query:
                df = df[df.apply(query['filter'], axis=1)]

        # Format output
        if output_format == 'dict':
            return df.to_dict(orient='records')
        elif output_format == 'list':
            return df.values.tolist()
        elif output_format == 'dataframe':
            return df
        else:
            return df.to_dict(orient='records')

    async def extract_columns(self, source: Union[str, Path],
                             columns: List[str]) -> List[Dict[str, Any]]:
        """Extract specific columns"""
        return await self.extract(source, {
            'columns': columns,
            'output_format': 'dict'
        })

    async def filter_rows(self, source: Union[str, Path],
                         filter_func: callable) -> List[Dict[str, Any]]:
        """Filter rows based on condition"""
        return await self.extract(source, {
            'filter': filter_func,
            'output_format': 'dict'
        })

    async def aggregate(self, source: Union[str, Path],
                       groupby: str,
                       aggregations: Dict[str, str]) -> pd.DataFrame:
        """
        Aggregate data

        Args:
            source: CSV file
            groupby: Column to group by
            aggregations: {'column': 'sum|mean|count|min|max'}

        Example:
            await extractor.aggregate(
                'sales.csv',
                groupby='region',
                aggregations={'sales': 'sum', 'orders': 'count'}
            )
        """
        df = await self.extract(source, {'output_format': 'dataframe'})

        return df.groupby(groupby).agg(aggregations)

    async def detect_delimiter(self, source: Union[str, Path]) -> str:
        """Auto-detect CSV delimiter"""
        with open(source, 'r') as f:
            sample = f.read(1024)
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter

        return delimiter

    async def detect_encoding(self, source: Union[str, Path]) -> str:
        """Detect file encoding"""
        import chardet

        with open(source, 'rb') as f:
            result = chardet.detect(f.read(10000))

        return result['encoding']

    async def extract_sample(self, source: Union[str, Path],
                            n_rows: int = 10) -> List[Dict[str, Any]]:
        """Extract first N rows as sample"""
        df = pd.read_csv(source, nrows=n_rows)
        return df.to_dict(orient='records')

    async def get_column_stats(self, source: Union[str, Path],
                               column: str) -> Dict[str, Any]:
        """Get statistics for a column"""
        df = pd.read_csv(source, usecols=[column])

        stats = {
            'count': int(df[column].count()),
            'null_count': int(df[column].isnull().sum()),
            'unique_count': int(df[column].nunique())
        }

        # Numeric stats
        if pd.api.types.is_numeric_dtype(df[column]):
            stats.update({
                'mean': float(df[column].mean()),
                'median': float(df[column].median()),
                'min': float(df[column].min()),
                'max': float(df[column].max()),
                'std': float(df[column].std())
            })

        return stats

    async def csv_to_json(self, source: Union[str, Path],
                         output_path: Optional[str] = None) -> Union[str, None]:
        """Convert CSV to JSON"""
        df = pd.read_csv(source)
        json_str = df.to_json(orient='records', indent=2)

        if output_path:
            with open(output_path, 'w') as f:
                f.write(json_str)
            return None

        return json_str
