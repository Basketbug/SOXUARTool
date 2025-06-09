# =============================================================================
# processors/defi_xlos.py - Defi XLOS processor
# =============================================================================

from typing import List, Dict, Any, Tuple, Optional

from core.base_processor import BaseUserProcessor
from core.models import UserRecord, LookupMethod


class DefiXLOSProcessor(BaseUserProcessor):
    """Defi XLOS processor with fallback to email lookup"""

    # Column mappings
    USERID_COLUMN = 'UserId'
    USERGUID_COLUMN = 'UserGuid'
    FULLNAME_COLUMN = 'FullName'
    STATUS_COLUMN = 'Status'
    EMAIL_COLUMN = 'Email'
    LASTLOGIN_COLUMN = 'LastLoginDate'
    CREATEDATE_COLUMN = 'CreateDate'

    def get_identifiers_for_lookup(self, row: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        """Primary: UserId, Backup: Email column"""
        primary = row.get(self.USERID_COLUMN, '').strip()
        backup = row.get(self.EMAIL_COLUMN, '').strip()
        return primary, backup if backup else None

    def should_skip_row(self, row: Dict[str, Any]) -> bool:
        """Skip rows with empty UserId"""
        return not row.get(self.USERID_COLUMN, '').strip()

    def apply_filters(self, csv_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out Status = 'Disabled'"""
        original_count = len(csv_data)
        filtered_data = [
            row for row in csv_data
            if row.get(self.STATUS_COLUMN, '').strip() != 'Disabled'
        ]

        self.logger.info(f"Filtered to {len(filtered_data)} enabled records from {original_count} total records")
        return filtered_data

    def create_user_record(self, csv_row: Dict[str, Any], username: str,
                           ad_data: Dict[str, Any], lookup_method: LookupMethod,
                           original_identifier: str) -> UserRecord:
        """Create UserRecord with Defi XLOS specific CSV data"""
        csv_data = {
            'user_guid': csv_row.get(self.USERGUID_COLUMN, ''),
            'csv_full_name': csv_row.get(self.FULLNAME_COLUMN, ''),
            'csv_status': csv_row.get(self.STATUS_COLUMN, ''),
            'csv_email': csv_row.get(self.EMAIL_COLUMN, ''),
            'last_login_date': csv_row.get(self.LASTLOGIN_COLUMN, ''),
            'create_date': csv_row.get(self.CREATEDATE_COLUMN, '')
        }

        return UserRecord(
            username=username,
            email=ad_data.get('email', ''),
            full_name=ad_data.get('full_name', ''),
            department=ad_data.get('department', ''),
            title=ad_data.get('title', ''),
            is_active=ad_data.get('is_active', False),
            lookup_method=lookup_method,
            original_identifier=original_identifier,
            csv_data=csv_data
        )

    def get_output_fieldnames(self) -> List[str]:
        """Get fieldnames for Defi XLOS CSV output"""
        return [
            'username', 'email', 'full_name', 'department', 'title', 'is_active',
            'lookup_method', 'original_identifier', 'user_guid', 'csv_full_name',
            'csv_status', 'csv_email', 'last_login_date', 'create_date'
        ]