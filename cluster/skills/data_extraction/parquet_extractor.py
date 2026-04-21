"""
Parquet Extractor Agent - Specialized in Parquet file extraction
"""

import pyarrow.parquet as pq
import pyarrow as pa
import pandas as pd
from typing import Dict, Any, List, Optional, Union
import structlog
from pathlib import Path

from .base_extractor import BaseExtractorAgent

logger = structlog.get_logger()


class ParquetExtractorAgent(BaseExtractorAgent):
    """
    Specialized agent for Parquet extraction

    Capabilities:
    - Read Parquet files efficiently
    - Column projection
    - Row filtering (predicate pushdown)
    - Schema extraction
    - Partition handling
    - Convert to other formats
    - Handle large files (memory efficient)
    """

    def _define_capabilities(self) -> List[str]:
        return [
            "read_parquet",
            "column_projection",
            "predicate_pushdown",
            "extract_schema",
            "handle_partitions",
            "convert_formats",
            "efficient_memory",
            "batch_processing"
        ]

    def _get_supported_formats(self) -> List[str]:
        return [".parquet", ".parq"]

    async def validate(self, source: Any) -> bool:
        """Validate if source is valid Parquet"""
        try:
            if isinstance(source, (str, Path)):
                pq.read_metadata(str(source))
            return True
        except Exception as e:
            logger.error("Parquet validation failed", error=str(e))
            return False

    async def extract(self, source: Union[str, Path],
                     query: Optional[Dict[str, Any]] = None) -> Any:
        """
        Extract data from Parquet

        Args:
            source: Parquet file path
            query: {
                'columns': ['col1', 'col2'],  # Column projection
                'filters': [('column', '>', 10)],  # Predicate pushdown
                'batch_size': 1000,  # For large files
                'output_format': 'dict' | 'dataframe' | 'arrow'
            }

        Returns:
            Extracted data
        """
        query = query or {}

        columns = query.get('columns', None)
        filters = query.get('filters', None)
        batch_size = query.get('batch_size', None)
        output_format = query.get('output_format', 'dict')

        # Read Parquet with optimizations
        if batch_size:
            # Read in batches for large files
            table = pq.read_table(
                source,
                columns=columns,
                filters=filters,
                use_threads=True,
                batch_size=batch_size
            )
        else:
            # Normal reading
            table = pq.read_table(
                source,
                columns=columns,
                filters=filters,
                use_threads=True
            )

        # Format output
        if output_format == 'arrow':
            return table
        elif output_format == 'dataframe':
            return table.to_pandas()
        elif output_format == 'dict':
            return table.to_pandas().to_dict(orient='records')
        else:
            return table.to_pandas().to_dict(orient='records')

    async def get_schema(self, source: Union[str, Path]) -> Dict[str, Any]:
        """Extract Parquet schema"""
        parquet_file = pq.ParquetFile(source)
        schema = parquet_file.schema_arrow

        return {
            'columns': [
                {
                    'name': field.name,
                    'type': str(field.type),
                    'nullable': field.nullable
                }
                for field in schema
            ],
            'num_row_groups': parquet_file.num_row_groups,
            'metadata': parquet_file.metadata.metadata
        }

    async def get_metadata(self, source: Union[str, Path]) -> Dict[str, Any]:
        """Get Parquet file metadata"""
        parquet_file = pq.ParquetFile(source)
        metadata = parquet_file.metadata

        return {
            'num_rows': metadata.num_rows,
            'num_columns': metadata.num_columns,
            'num_row_groups': metadata.num_row_groups,
            'serialized_size': metadata.serialized_size,
            'created_by': metadata.created_by,
            'format_version': metadata.format_version
        }

    async def extract_columns(self, source: Union[str, Path],
                             columns: List[str]) -> List[Dict[str, Any]]:
        """Extract specific columns (efficient column projection)"""
        return await self.extract(source, {
            'columns': columns,
            'output_format': 'dict'
        })

    async def filter_rows(self, source: Union[str, Path],
                         filters: List[tuple]) -> List[Dict[str, Any]]:
        """
        Filter rows using predicate pushdown (very efficient)

        Args:
            filters: List of tuples (column, operator, value)
                    e.g., [('age', '>', 18), ('status', '==', 'active')]
        """
        return await self.extract(source, {
            'filters': filters,
            'output_format': 'dict'
        })

    async def read_partitioned(self, path: Union[str, Path],
                              partition_columns: Optional[List[str]] = None) -> pd.DataFrame:
        """Read partitioned Parquet dataset"""
        dataset = pq.ParquetDataset(
            path,
            partitioning=partition_columns
        )

        table = dataset.read()
        return table.to_pandas()

    async def convert_to_csv(self, source: Union[str, Path],
                            output_path: str,
                            columns: Optional[List[str]] = None):
        """Convert Parquet to CSV"""
        df = await self.extract(source, {
            'columns': columns,
            'output_format': 'dataframe'
        })

        df.to_csv(output_path, index=False)
        logger.info(f"Converted {source} to {output_path}")

    async def convert_to_json(self, source: Union[str, Path],
                             output_path: str,
                             columns: Optional[List[str]] = None):
        """Convert Parquet to JSON"""
        df = await self.extract(source, {
            'columns': columns,
            'output_format': 'dataframe'
        })

        df.to_json(output_path, orient='records', indent=2)
        logger.info(f"Converted {source} to {output_path}")

    async def get_row_group_info(self, source: Union[str, Path]) -> List[Dict[str, Any]]:
        """Get information about row groups"""
        parquet_file = pq.ParquetFile(source)

        row_groups = []
        for i in range(parquet_file.num_row_groups):
            rg_metadata = parquet_file.metadata.row_group(i)

            row_groups.append({
                'index': i,
                'num_rows': rg_metadata.num_rows,
                'total_byte_size': rg_metadata.total_byte_size,
                'num_columns': rg_metadata.num_columns
            })

        return row_groups

    async def extract_statistics(self, source: Union[str, Path],
                                 column: str) -> Dict[str, Any]:
        """Extract column statistics from Parquet metadata"""
        parquet_file = pq.ParquetFile(source)

        # Get column index
        column_index = parquet_file.schema_arrow.get_field_index(column)

        # Aggregate statistics from all row groups
        stats = {
            'min': None,
            'max': None,
            'null_count': 0,
            'distinct_count': 0
        }

        for i in range(parquet_file.num_row_groups):
            rg_metadata = parquet_file.metadata.row_group(i)
            col_metadata = rg_metadata.column(column_index)

            if col_metadata.statistics:
                col_stats = col_metadata.statistics

                if stats['min'] is None or col_stats.min < stats['min']:
                    stats['min'] = col_stats.min

                if stats['max'] is None or col_stats.max > stats['max']:
                    stats['max'] = col_stats.max

                stats['null_count'] += col_stats.null_count
                stats['distinct_count'] += col_stats.distinct_count

        return stats
