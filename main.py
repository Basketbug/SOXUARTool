# =============================================================================
# main.py - CLI entry point
# =============================================================================

import argparse
import logging
import sys
from pathlib import Path

from core.ad_client import ActiveDirectoryClient
from processors.great_plains import GreatPlainsProcessor
from processors.defi_los import DefiLOSProcessor
from processors.defi_servicing import DefiServicingProcessor
from processors.defi_xlos import DefiXLOSProcessor
from processors.datascan import DatascanProcessor
from utils.config import Config


def setup_logging(level: str = "INFO") -> None:
    """Setup logging configuration with both console and file output"""
    from datetime import datetime
    import os

    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Generate date-stamped filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = log_dir / f"user_access_processor_{timestamp}.log"

    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)  # Always log DEBUG to file
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Log the setup
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized - Console: {level.upper()}, File: DEBUG")
    logger.info(f"Log file: {log_filename}")

    return str(log_filename)


def handle_csv_processors(args, config):
    """Handle CSV-based processors (great_plains, defi_los, defi_servicing, defi_xlos)"""
    logger = logging.getLogger(__name__)

    with ActiveDirectoryClient(
            config.ad_server, config.ad_username,
            config.ad_password, config.base_dn
    ) as ad_client:

        # Select processor based on type
        processor_map = {
            'great_plains': GreatPlainsProcessor,
            'defi_los': DefiLOSProcessor,
            'defi_servicing': DefiServicingProcessor,
            'defi_xlos': DefiXLOSProcessor,
        }

        processor_class = processor_map[args.processor]

        # Handle special case for defi_los with role extraction
        if args.processor == 'defi_los' and hasattr(args, 'role_output') and args.role_output:
            processor = processor_class(ad_client, extract_roles=True)
            stats = processor.process_users(
                args.input_csv,
                args.output_csv,
                apply_filters=not args.no_filters,
                role_output_csv=args.role_output
            )
        else:
            processor = processor_class(ad_client)
            stats = processor.process_users(
                args.input_csv,
                args.output_csv,
                apply_filters=not args.no_filters
            )

        logger.info("Processing completed successfully!")
        logger.info(f"Final success rate: {stats.success_rate:.1f}%")


def handle_datascan_processor(args, config):
    """Handle Excel-based Datascan processor"""
    logger = logging.getLogger(__name__)

    with ActiveDirectoryClient(
            config.ad_server, config.ad_username,
            config.ad_password, config.base_dn
    ) as ad_client:
        processor = DatascanProcessor(ad_client, args.input_file, args.sheet_name)

        # Load and process the data
        raw_data = processor.load_data()
        logger.info(f"Loaded {len(raw_data)} rows from Excel file")

        processed_data = processor.process_permissions()
        logger.info(f"Processed data contains {len(processed_data)} permission entries")

        # Export all processed data to Excel
        processor.export_processed_data(args.output_file)
        logger.info(f"Exported processed data to {args.output_file}")


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description="User Access Processor")
    subparsers = parser.add_subparsers(dest='processor', help='Processor type')

    # Common arguments for CSV processors
    csv_processors = ['great_plains', 'defi_los', 'defi_servicing', 'defi_xlos']

    for proc_name in csv_processors:
        proc_parser = subparsers.add_parser(proc_name, help=f'{proc_name.replace("_", " ").title()} processor')
        proc_parser.add_argument('input_csv', help='Input CSV file path')
        proc_parser.add_argument('output_csv', help='Output CSV file path')
        proc_parser.add_argument('--no-filters', action='store_true', help='Disable filtering')

        # Special case for defi_los role extraction
        if proc_name == 'defi_los':
            proc_parser.add_argument('--role-output', help='Output CSV file for role analysis')

    # Datascan processor (Excel-based)
    datascan_parser = subparsers.add_parser('datascan', help='Datascan Excel processor')
    datascan_parser.add_argument('input_file', help='Input Excel file path')
    datascan_parser.add_argument('output_file', help='Output Excel file path')
    datascan_parser.add_argument('--sheet-name', help='Excel sheet name (optional)')

    # Global arguments
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level')

    args = parser.parse_args()

    if not args.processor:
        parser.print_help()
        sys.exit(1)

    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    # Load configuration
    config = Config()
    if not config.validate_ad_config():
        missing_vars = config.get_missing_ad_vars()
        logger.error(f"Missing required environment variables: {missing_vars}")
        sys.exit(1)

    # Validate input file exists
    input_file = args.input_csv if hasattr(args, 'input_csv') else args.input_file
    if not Path(input_file).exists():
        logger.error(f"Input file not found: {input_file}")
        sys.exit(1)

    try:
        if args.processor in ['great_plains', 'defi_los', 'defi_servicing', 'defi_xlos']:
            handle_csv_processors(args, config)
        elif args.processor == 'datascan':
            handle_datascan_processor(args, config)
        else:
            logger.error(f"Unknown processor: {args.processor}")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Processing failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()