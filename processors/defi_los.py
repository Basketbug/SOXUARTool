# =============================================================================
# processors/defi_los.py - Defi LOS processor with role extraction
# =============================================================================

from typing import List, Dict, Any, Tuple, Optional
import re

from core.base_processor import BaseUserProcessor
from core.models import UserRecord, LookupMethod, RoleRecord
from utils.csv_utils import CSVHandler


class DefiLOSProcessor(BaseUserProcessor):
    """Defi LOS processor with fallback logic and role extraction"""

    # Column mappings
    USERNAME_COLUMN = 'User Name'
    EMAIL_COLUMN_INDEX = 9  # Column J (0-indexed)
    ACTIVE_COLUMN_INDEX = 10  # Column K

    # Metadata columns that are not roles
    METADATA_COLUMNS = {
        'user name', 'first name', 'last name', 'phone number', 'cell phone number',
        'extension', 'fax number', 'employee id', 'region', 'email', 'active?', 'lastlogin?'
    }

    def __init__(self, ad_client, extract_roles: bool = False):
        super().__init__(ad_client)
        self.extract_roles = extract_roles
        self.role_columns = []
        self.headers = []

    def get_identifiers_for_lookup(self, row: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        """Primary: User Name column, Backup: username from email in column J"""
        primary = row.get(self.USERNAME_COLUMN, '').strip()

        # Get backup from email column
        backup = None
        if len(self.headers) > self.EMAIL_COLUMN_INDEX:
            email_col_name = self.headers[self.EMAIL_COLUMN_INDEX]
            email = row.get(email_col_name, '').strip()
            if email and '@' in email:
                backup = email.split('@')[0].strip()

        return primary, backup

    def should_skip_row(self, row: Dict[str, Any]) -> bool:
        """Skip rows with empty User Name or SFS.Funding emails after failed lookups"""
        primary = row.get(self.USERNAME_COLUMN, '').strip()
        if not primary:
            return True

        # Check for SFS.Funding email (will be handled in lookup logic)
        return False

    def apply_filters(self, csv_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter for Active = 'Yes' in column K"""
        if len(self.headers) <= self.ACTIVE_COLUMN_INDEX:
            self.logger.warning(f"Column K (index {self.ACTIVE_COLUMN_INDEX}) not available - no filtering applied")
            return csv_data

        active_column_name = self.headers[self.ACTIVE_COLUMN_INDEX]
        original_count = len(csv_data)
        filtered_data = [
            row for row in csv_data
            if row.get(active_column_name, '').strip().lower() == 'yes'
        ]

        self.logger.info(f"Filtered to {len(filtered_data)} active records from {original_count} total records")
        return filtered_data

    def lookup_single_user(self, row: Dict[str, Any], primary_id: str,
                           backup_id: Optional[str]) -> Optional[UserRecord]:
        """Custom lookup with SFS.Funding exclusion logic"""
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

            # Both failed - check for SFS.Funding exclusion
            email_from_csv = ""
            if len(self.headers) > self.EMAIL_COLUMN_INDEX:
                email_col_name = self.headers[self.EMAIL_COLUMN_INDEX]
                email_from_csv = row.get(email_col_name, '').strip()

            if 'SFS.Funding' in email_from_csv or 'sfs.funding' in email_from_csv:
                self.logger.info(f"Skipping user {primary_id} - email contains SFS.Funding: {email_from_csv}")
                return None  # Skip this user entirely

            # Regular failure
            return self.create_user_record(
                row, primary_id, {}, LookupMethod.FAILED,
                f"{primary_id}" + (f" (backup: {backup_id})" if backup_id else "")
            )

        except Exception as e:
            self.logger.error(f"Error during lookup for {primary_id}: {e}")
            return self.create_user_record(
                row, primary_id, {}, LookupMethod.ERROR, primary_id
            )

    def create_user_record(self, csv_row: Dict[str, Any], username: str,
                           ad_data: Dict[str, Any], lookup_method: LookupMethod,
                           original_identifier: str) -> UserRecord:
        """Create UserRecord with minimal CSV data"""
        return UserRecord(
            username=username,
            email=ad_data.get('email', ''),
            full_name=ad_data.get('full_name', ''),
            department=ad_data.get('department', ''),
            title=ad_data.get('title', ''),
            is_active=ad_data.get('is_active', False),
            lookup_method=lookup_method,
            original_identifier=original_identifier,
            csv_data={}  # Minimal for this processor
        )

    def get_output_fieldnames(self) -> List[str]:
        """Get fieldnames for Defi LOS CSV output"""
        return [
            'username', 'email', 'full_name', 'department', 'title', 'is_active',
            'lookup_method', 'original_identifier'
        ]

    def process_users(self, input_csv: str, output_csv: str,
                      apply_filters: bool = True, role_output_csv: Optional[str] = None) -> Any:
        """Extended processing with role extraction capability"""
        # Read CSV and store headers for role processing
        csv_data, self.headers = CSVHandler.read_csv(input_csv)

        # Identify role columns
        if self.extract_roles or role_output_csv:
            clean_headers = [header.strip().lower() for header in self.headers]
            self.role_columns = [
                self.headers[i] for i, header in enumerate(clean_headers)
                if header not in self.METADATA_COLUMNS
            ]
            self.logger.info(f"Identified {len(self.role_columns)} role columns")

        # Continue with normal processing
        self.logger.info(f"Read {len(csv_data)} records from {input_csv}")

        if apply_filters:
            csv_data = self.apply_filters(csv_data)
            self.logger.info(f"After filtering: {len(csv_data)} records")

        # Process users for AD lookup
        processed_users = self.lookup_users(csv_data)

        # Write AD review output
        output_data = [self.user_record_to_dict(user) for user in processed_users]
        CSVHandler.write_csv(output_data, output_csv, self.get_output_fieldnames())

        # Process roles if requested
        if role_output_csv:
            role_records = self.extract_roles_with_ad_data(csv_data, processed_users)
            role_output_data = [self.role_record_to_dict(role) for role in role_records]
            CSVHandler.write_csv(role_output_data, role_output_csv,
                                 ['username', 'department', 'title', 'assigned_roles'])
            self.logger.info(f"Successfully wrote {len(role_records)} role records to {role_output_csv}")

        # Generate statistics
        stats = self.calculate_stats(processed_users)
        self.log_statistics(stats)

        return stats

    def extract_roles_with_ad_data(self, csv_data: List[Dict[str, Any]],
                                   processed_users: List[UserRecord]) -> List[RoleRecord]:
        """Extract roles and enrich with AD data"""
        # Create lookup dict for AD users
        ad_user_dict = {user.username: user for user in processed_users
                        if user.lookup_method in [LookupMethod.PRIMARY, LookupMethod.BACKUP]}

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
                department = ad_user.department or "Defi LOS"
                title = ad_user.title or ad_user.full_name or username_to_use
            else:
                department = "Defi LOS"
                title = username_to_use

            # Extract roles
            assigned_roles = []
            for role_col in self.role_columns:
                role_value = row.get(role_col, '').strip().lower()
                if role_value in ['yes', 'y', 'true', '1']:
                    clean_role = self.clean_role_name(role_col)
                    assigned_roles.append(clean_role)

            # Create role records
            if assigned_roles:
                for role in assigned_roles:
                    role_records.append(RoleRecord(
                        username=username_to_use,
                        department=department,
                        title=title,
                        assigned_roles=role
                    ))
            else:
                role_records.append(RoleRecord(
                    username=username_to_use,
                    department=department,
                    title=title,
                    assigned_roles='No Roles'
                ))

        return role_records

    def clean_role_name(self, role_col: str) -> str:
        """Clean up role column names for better readability"""
        cleaned = role_col.replace('?', '').strip()

        # Convert to title case and fix common abbreviations
        words = cleaned.split()
        title_words = []

        for word in words:
            if word.lower() in ['admin', 'mgr', 'sr', 'jr', 'ii', 'iii', 'iv']:
                title_words.append(word.upper())
            elif word.lower() == 'administrator':
                title_words.append('Admin')
            elif word.lower() == 'manager':
                title_words.append('Manager')
            elif word.lower() == 'analyst':
                title_words.append('Analyst')
            elif word.lower() == 'director':
                title_words.append('Director')
            elif word.lower() == 'processor':
                title_words.append('Processor')
            elif word.lower() == 'representative':
                title_words.append('Rep')
            else:
                title_words.append(word.title())

        return ' '.join(title_words)

    def role_record_to_dict(self, role: RoleRecord) -> Dict[str, Any]:
        """Convert RoleRecord to dictionary"""
        return {
            'username': role.username,
            'department': role.department,
            'title': role.title,
            'assigned_roles': role.assigned_roles
        }