# =============================================================================
# core/base_processor.py - Abstract base processor
# =============================================================================

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional
import logging

from core.models import UserRecord, ProcessingStats, LookupMethod
from core.ad_client import ActiveDirectoryClient
from utils.csv_utils import CSVHandler


class BaseUserProcessor(ABC):
    """Abstract base class for user processors"""

    def __init__(self, ad_client: ActiveDirectoryClient):
        self.ad_client = ad_client
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def get_identifiers_for_lookup(self, row: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        """Extract primary and backup identifiers from CSV row"""
        pass

    @abstractmethod
    def should_skip_row(self, row: Dict[str, Any]) -> bool:
        """Determine if row should be skipped"""
        pass

    @abstractmethod
    def create_user_record(self, csv_row: Dict[str, Any], username: str,
                           ad_data: Dict[str, Any], lookup_method: LookupMethod,
                           original_identifier: str) -> UserRecord:
        """Create UserRecord from CSV and AD data"""
        pass

    @abstractmethod
    def get_output_fieldnames(self) -> List[str]:
        """Get fieldnames for CSV output"""
        pass

    def should_use_backup(self, primary_result: Dict[str, Any]) -> bool:
        """Determine if backup lookup should be used"""
        if not primary_result:
            return True

        meaningful_fields = ['email', 'full_name', 'department']
        has_meaningful_data = any(primary_result.get(field) for field in meaningful_fields)
        return not has_meaningful_data

    def process_users(self, input_csv: str, output_csv: str,
                      apply_filters: bool = True) -> ProcessingStats:
        """Main processing workflow"""
        self.logger.info(f"Starting {self.__class__.__name__} processing workflow")

        try:
            # Read CSV
            csv_data, headers = CSVHandler.read_csv(input_csv)
            self.logger.info(f"Read {len(csv_data)} records from {input_csv}")

            # Apply filters if needed
            if apply_filters:
                csv_data = self.apply_filters(csv_data)
                self.logger.info(f"After filtering: {len(csv_data)} records")

            # Process users
            processed_users = self.lookup_users(csv_data)

            # Convert to output format and write
            output_data = [self.user_record_to_dict(user) for user in processed_users]
            CSVHandler.write_csv(output_data, output_csv, self.get_output_fieldnames())

            # Generate statistics
            stats = self.calculate_stats(processed_users)
            self.log_statistics(stats)

            return stats

        except Exception as e:
            self.logger.error(f"Processing failed: {e}")
            raise

    def apply_filters(self, csv_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply processor-specific filters to CSV data"""
        # Default implementation - can be overridden
        return csv_data

    def lookup_users(self, csv_data: List[Dict[str, Any]]) -> List[UserRecord]:
        """Lookup users with fallback logic"""
        processed_users = []

        for row in csv_data:
            if self.should_skip_row(row):
                continue

            primary_id, backup_id = self.get_identifiers_for_lookup(row)

            if not primary_id:
                self.logger.warning("Skipping row with empty primary identifier")
                continue

            user_record = self.lookup_single_user(row, primary_id, backup_id)
            if user_record:
                processed_users.append(user_record)

        return processed_users

    def lookup_single_user(self, row: Dict[str, Any], primary_id: str,
                           backup_id: Optional[str]) -> Optional[UserRecord]:
        """Lookup a single user with fallback logic"""
        try:
            # Try primary lookup
            ad_data = self.perform_primary_lookup(primary_id)

            if ad_data and not self.should_use_backup(ad_data):
                return self.create_user_record(
                    row, primary_id, ad_data, LookupMethod.PRIMARY, primary_id
                )

            # Try backup if available
            if backup_id:
                backup_ad_data = self.perform_backup_lookup(backup_id)
                if backup_ad_data:
                    return self.create_user_record(
                        row, backup_id, backup_ad_data, LookupMethod.BACKUP,
                        f"{primary_id} -> {backup_id}"
                    )

            # Both failed
            return self.create_user_record(
                row, primary_id, {}, LookupMethod.FAILED,
                f"{primary_id}" + (f" (backup: {backup_id})" if backup_id else "")
            )

        except Exception as e:
            self.logger.error(f"Error during lookup for {primary_id}: {e}")
            return self.create_user_record(
                row, primary_id, {}, LookupMethod.ERROR, primary_id
            )

    def perform_primary_lookup(self, identifier: str) -> Dict[str, Any]:
        """Perform primary AD lookup - default is sAMAccountName"""
        return self.ad_client.query_user_by_samaccountname(identifier)

    def perform_backup_lookup(self, identifier: str) -> Dict[str, Any]:
        """Perform backup AD lookup - default is email"""
        return self.ad_client.query_user_by_email(identifier)

    def user_record_to_dict(self, user: UserRecord) -> Dict[str, Any]:
        """Convert UserRecord to dictionary for CSV output"""
        base_dict = {
            'username': user.username,
            'email': user.email,
            'full_name': user.full_name,
            'department': user.department,
            'title': user.title,
            'is_active': user.is_active,
            'lookup_method': user.lookup_method.value,
            'original_identifier': user.original_identifier
        }
        base_dict.update(user.csv_data)
        return base_dict

    def calculate_stats(self, processed_users: List[UserRecord]) -> ProcessingStats:
        """Calculate processing statistics"""
        stats = ProcessingStats()
        stats.total_records = len(processed_users)

        for user in processed_users:
            method = user.lookup_method
            stats.lookup_method_counts[method] = stats.lookup_method_counts.get(method, 0) + 1

            if method in [LookupMethod.PRIMARY, LookupMethod.BACKUP,
                          LookupMethod.DISPLAYNAME, LookupMethod.NAME_COMPONENTS,
                          LookupMethod.EMAIL]:
                stats.successful_lookups += 1
            elif method == LookupMethod.FAILED:
                stats.failed_lookups += 1
            elif method == LookupMethod.ERROR:
                stats.error_lookups += 1

        return stats

    def log_statistics(self, stats: ProcessingStats) -> None:
        """Log processing statistics"""
        method_counts = {method.value: count for method, count in stats.lookup_method_counts.items()}
        self.logger.info(f"Lookup summary: {method_counts}")
        self.logger.info(f"Success rate: {stats.success_rate:.1f}% ({stats.successful_lookups}/{stats.total_records})")