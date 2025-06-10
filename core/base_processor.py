# =============================================================================
# core/base_processor.py - Abstract base processor
# =============================================================================

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional
import logging

from core.models import UserRecord, ProcessingStats, LookupMethod, RoleRecord
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
                      apply_filters: bool = True, role_output_csv: Optional[str] = None) -> ProcessingStats:
        """Main processing workflow with optional role extraction"""
        self.logger.info(f"Starting {self.__class__.__name__} processing workflow")

        try:
            # Read CSV
            csv_data, headers = CSVHandler.read_csv(input_csv)
            self.logger.info(f"Read {len(csv_data)} records from {input_csv}")

            # Store headers for processors that need them
            if hasattr(self, 'headers'):
                self.headers = headers

            # Apply filters if needed
            if apply_filters:
                csv_data = self.apply_filters(csv_data)
                self.logger.info(f"After filtering: {len(csv_data)} records")

            # Process users
            processed_users = self.lookup_users(csv_data)

            # Convert to output format and write main CSV
            output_data = [self.user_record_to_dict(user) for user in processed_users]
            CSVHandler.write_csv(output_data, output_csv, self.get_output_fieldnames())

            # Generate role analysis if requested
            if role_output_csv:
                role_records = self.extract_roles_with_ad_data(csv_data, processed_users)
                if role_records:
                    role_output_data = [self.role_record_to_dict(role) for role in role_records]
                    CSVHandler.write_csv(role_output_data, role_output_csv,
                                         ['username', 'department', 'title', 'assigned_roles'])
                    self.logger.info(f"Successfully wrote {len(role_records)} role records to {role_output_csv}")
                else:
                    self.logger.warning("No role data extracted - role output file not created")

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

    def extract_roles_with_ad_data(self, csv_data: List[Dict[str, Any]],
                                   processed_users: List[UserRecord]) -> List[RoleRecord]:
        """
        Base implementation of role extraction - override in subclasses for specific logic.
        Default behavior: create one record per user with 'No Roles' assignment.
        """
        # Create lookup dict for AD users
        ad_user_dict = {user.username: user for user in processed_users
                        if user.lookup_method in [LookupMethod.PRIMARY, LookupMethod.BACKUP,
                                                  LookupMethod.DISPLAYNAME, LookupMethod.NAME_COMPONENTS,
                                                  LookupMethod.EMAIL]}

        role_records = []

        for row in csv_data:
            primary_id, backup_id = self.get_identifiers_for_lookup(row)
            if not primary_id:
                continue

            # Determine which username to use and get AD data
            username_to_use = primary_id
            ad_user = ad_user_dict.get(primary_id)

            if not ad_user and backup_id:
                ad_user = ad_user_dict.get(backup_id)
                if ad_user:
                    username_to_use = backup_id

            # Get department and title from AD or defaults
            if ad_user:
                department = ad_user.department or self._get_default_department()
                title = ad_user.title or ad_user.full_name or username_to_use
            else:
                department = self._get_default_department()
                title = username_to_use

            # Default implementation - no role extraction
            role_records.append(RoleRecord(
                username=self.normalize_role_data(username_to_use),
                department=self.normalize_role_data(department),
                title=self.normalize_role_data(title),
                assigned_roles='no roles'  # Normalized version
            ))

        return role_records

    def _get_default_department(self) -> str:
        """Get default department name for this processor"""
        # Extract department name from class name (e.g., GreatPlainsProcessor -> Great Plains)
        class_name = self.__class__.__name__.replace('Processor', '')
        # Convert CamelCase to spaced words
        import re
        return re.sub(r'([A-Z])', r' \1', class_name).strip()

    def role_record_to_dict(self, role: RoleRecord) -> Dict[str, Any]:
        """Convert RoleRecord to dictionary for CSV output"""
        return {
            'username': role.username,
            'department': role.department,
            'title': role.title,
            'assigned_roles': role.assigned_roles
        }

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

    def normalize_role_data(self, value: str) -> str:
        """
        Normalize role data by converting to lowercase, removing whitespace, and cleaning quotes.

        Args:
            value: Raw value to normalize

        Returns:
            Normalized string value
        """
        if not value:
            return ''

        # Convert to string and strip whitespace
        normalized = str(value).strip()

        # Remove trailing quotes/apostrophes
        normalized = normalized.rstrip("'\"")

        # Remove leading quotes/apostrophes
        normalized = normalized.lstrip("'\"")

        # Convert to lowercase
        normalized = normalized.lower()

        # Remove extra internal whitespace (multiple spaces become single space)
        normalized = ' '.join(normalized.split())

        return normalized