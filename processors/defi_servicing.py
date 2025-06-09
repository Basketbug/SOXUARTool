# =============================================================================
# processors/defi_servicing.py - Defi Servicing processor
# =============================================================================

from typing import List, Dict, Any, Tuple, Optional

from core.base_processor import BaseUserProcessor
from core.models import UserRecord, LookupMethod


class DefiServicingProcessor(BaseUserProcessor):
    """Defi Servicing processor with SFSE prefix handling"""

    # Column mappings
    APPLICATION_USER_ID = 'Application User ID'
    APPLICATION_USER_LOGIN_ORG_ID = 'Application User Login Org Id'
    APPLICATION_USER_FIRST_NAME = 'Application User First Name'
    APPLICATION_USER_LAST_NAME = 'Application User Last Name'
    USER_STATUS_CODE = 'User Status Code'
    USER_CREATE_DATE = 'User Create Date'
    USER_DISABLE_DATE = 'User Disable Date'
    USER_DISABLED_BY_USERID = 'User Disabled By UserId'
    MASTER_ROLE_ID = 'Master Role Id'
    SERVICER_ID = 'Servicer Id'
    MASTER_ROLE_DESC = 'Master Role Desc'
    SERVICER_ID_2 = 'servicer_id'
    CLIENT_ID = 'client_id'

    def get_identifiers_for_lookup(self, row: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        """Primary: Application User ID with SFSE prefix stripped, No backup"""
        raw_user_id = row.get(self.APPLICATION_USER_ID, '').strip()

        # Strip SFSE prefix if present
        if raw_user_id.startswith('SFSE.'):
            primary = raw_user_id[5:]  # Remove 'SFSE.' prefix
        elif raw_user_id.startswith('SFSE'):
            primary = raw_user_id[4:]  # Remove 'SFSE' prefix without dot
        else:
            self.logger.warning(f"Application User ID '{raw_user_id}' does not start with SFSE prefix")
            primary = raw_user_id

        return primary, None  # No backup for this processor

    def should_skip_row(self, row: Dict[str, Any]) -> bool:
        """Skip rows with empty Application User ID"""
        return not row.get(self.APPLICATION_USER_ID, '').strip()

    def apply_filters(self, csv_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out User Status Code = 'DELETED' or 'DISABLED'"""
        excluded_statuses = ['DELETED', 'DISABLED']
        original_count = len(csv_data)

        filtered_data = [
            row for row in csv_data
            if row.get(self.USER_STATUS_CODE, '').strip() not in excluded_statuses
        ]

        self.logger.info(f"Filtered to {len(filtered_data)} enabled records from {original_count} total records")
        return filtered_data

    def perform_backup_lookup(self, identifier: str) -> Dict[str, Any]:
        """No backup lookup for this processor"""
        return {}

    def create_user_record(self, csv_row: Dict[str, Any], username: str,
                           ad_data: Dict[str, Any], lookup_method: LookupMethod,
                           original_identifier: str) -> UserRecord:
        """Create UserRecord with Defi Servicing specific CSV data"""
        csv_data = {
            'application_user_login_org_id': csv_row.get(self.APPLICATION_USER_LOGIN_ORG_ID, ''),
            'application_user_first_name': csv_row.get(self.APPLICATION_USER_FIRST_NAME, ''),
            'application_user_last_name': csv_row.get(self.APPLICATION_USER_LAST_NAME, ''),
            'user_status_code': csv_row.get(self.USER_STATUS_CODE, ''),
            'user_create_date': csv_row.get(self.USER_CREATE_DATE, ''),
            'user_disable_date': csv_row.get(self.USER_DISABLE_DATE, ''),
            'user_disabled_by_userid': csv_row.get(self.USER_DISABLED_BY_USERID, ''),
            'master_role_id': csv_row.get(self.MASTER_ROLE_ID, ''),
            'servicer_id': csv_row.get(self.SERVICER_ID, ''),
            'master_role_desc': csv_row.get(self.MASTER_ROLE_DESC, ''),
            'servicer_id_2': csv_row.get(self.SERVICER_ID_2, ''),
            'client_id': csv_row.get(self.CLIENT_ID, '')
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
        """Get fieldnames for Defi Servicing CSV output"""
        return [
            'username', 'email', 'full_name', 'department', 'title', 'is_active',
            'lookup_method', 'original_identifier', 'application_user_login_org_id',
            'application_user_first_name', 'application_user_last_name', 'user_status_code',
            'user_create_date', 'user_disable_date', 'user_disabled_by_userid',
            'master_role_id', 'servicer_id', 'master_role_desc', 'servicer_id_2', 'client_id'
        ]