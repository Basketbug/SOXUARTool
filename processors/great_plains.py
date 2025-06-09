# =============================================================================
# processors/great_plains.py - Great Plains specific processor
# =============================================================================

from typing import List, Dict, Any, Tuple, Optional

from core.base_processor import BaseUserProcessor
from core.models import UserRecord, LookupMethod


class GreatPlainsProcessor(BaseUserProcessor):
    """Great Plains specific processor with displayName and name component lookup"""

    # Column mappings
    USERNAME_COLUMN = 'username'
    TITLE_COLUMN = 'title'
    DEPARTMENT_COLUMN = 'department'
    SECURITYROLEID_COLUMN = 'SECURITYROLEID'

    def get_identifiers_for_lookup(self, row: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        """For Great Plains: primary is full name from username column"""
        full_name = row.get(self.USERNAME_COLUMN, '').strip()
        return full_name, None  # No backup identifier for this processor

    def should_skip_row(self, row: Dict[str, Any]) -> bool:
        """Skip rows with empty username"""
        return not row.get(self.USERNAME_COLUMN, '').strip()

    def perform_primary_lookup(self, identifier: str) -> Dict[str, Any]:
        """Try displayName lookup first"""
        return self.ad_client.query_user_by_displayname(identifier)

    def lookup_single_user(self, row: Dict[str, Any], primary_id: str,
                           backup_id: Optional[str]) -> Optional[UserRecord]:
        """Custom lookup logic for Great Plains with name component fallback"""
        try:
            # Try displayName lookup first
            ad_data = self.ad_client.query_user_by_displayname(primary_id)

            if ad_data:
                return self.create_user_record(
                    row, primary_id, ad_data, LookupMethod.DISPLAYNAME, primary_id
                )

            # Try name component lookup
            name_parts = primary_id.split()
            if len(name_parts) >= 2:
                firstname = name_parts[0]
                lastname = ' '.join(name_parts[1:])

                name_ad_data = self.ad_client.query_user_by_name_components(firstname, lastname)
                if name_ad_data:
                    return self.create_user_record(
                        row, primary_id, name_ad_data, LookupMethod.NAME_COMPONENTS,
                        f"{primary_id} -> {firstname}+{lastname}"
                    )

            # Both lookups failed
            return self.create_user_record(
                row, primary_id, {}, LookupMethod.FAILED,
                f"{primary_id} (cannot split name)" if len(name_parts) < 2 else primary_id
            )

        except Exception as e:
            self.logger.error(f"Error during lookup for {primary_id}: {e}")
            return self.create_user_record(
                row, primary_id, {}, LookupMethod.ERROR, primary_id
            )

    def create_user_record(self, csv_row: Dict[str, Any], username: str,
                           ad_data: Dict[str, Any], lookup_method: LookupMethod,
                           original_identifier: str) -> UserRecord:
        """Create UserRecord with Great Plains specific CSV data"""
        csv_data = {
            'csv_title': csv_row.get(self.TITLE_COLUMN, ''),
            'csv_department': csv_row.get(self.DEPARTMENT_COLUMN, ''),
            'security_role_id': csv_row.get(self.SECURITYROLEID_COLUMN, '')
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
        """Get fieldnames for Great Plains CSV output"""
        return [
            'username', 'email', 'full_name', 'department', 'title', 'is_active',
            'lookup_method', 'original_identifier', 'csv_title', 'csv_department',
            'security_role_id'
        ]