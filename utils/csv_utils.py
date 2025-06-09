# =============================================================================
# utils/csv_utils.py - CSV utilities
# =============================================================================

import csv
from typing import List, Dict, Any, Optional
import logging


class CSVHandler:
    """Utilities for reading and writing CSV files"""

    @staticmethod
    def read_csv(file_path: str, encoding: str = 'utf-8-sig',
                 delimiter: str = ',') -> List[Dict[str, Any]]:
        """Read CSV file and return list of dictionaries"""
        logger = logging.getLogger(__name__)

        try:
            with open(file_path, 'r', newline='', encoding=encoding) as file:
                # Read headers first for validation
                reader = csv.reader(file, delimiter=delimiter)
                headers = next(reader)

                logger.info(f"CSV Headers: {headers[:10]}...")  # First 10 headers
                logger.info(f"Total columns: {len(headers)}")

                # Reset and read with DictReader
                file.seek(0)
                dict_reader = csv.DictReader(file, delimiter=delimiter)
                data = list(dict_reader)

                logger.info(f"Successfully read {len(data)} records from {file_path}")
                return data, headers

        except FileNotFoundError:
            logger.error(f"Input file {file_path} not found")
            raise
        except Exception as e:
            logger.error(f"Error reading CSV: {e}")
            raise

    @staticmethod
    def write_csv(data: List[Dict[str, Any]], output_path: str,
                  fieldnames: Optional[List[str]] = None) -> None:
        """Write data to CSV file"""
        logger = logging.getLogger(__name__)

        if not data:
            logger.warning("No data to write")
            return

        if fieldnames is None:
            fieldnames = list(data[0].keys())

        try:
            with open(output_path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)

            logger.info(f"Successfully wrote {len(data)} records to {output_path}")

        except Exception as e:
            logger.error(f"Error writing CSV: {e}")
            raise