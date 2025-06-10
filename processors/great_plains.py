# =============================================================================
# processors/great_plains.py - Great Plains specific processor
# =============================================================================

from typing import List, Dict, Any, Tuple, Optional

from core.base_processor import BaseUserProcessor
from core.models import UserRecord, LookupMethod, RoleRecord


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

    def extract_roles_with_ad_data(self, csv_data: List[Dict[str, Any]],
                                   processed_users: List[UserRecord]) -> List[RoleRecord]:
        """Extract roles from Great Plains data based on security role ID"""
        # Create lookup dict for AD users
        ad_user_dict = {user.username: user for user in processed_users
                        if user.lookup_method in [LookupMethod.DISPLAYNAME, LookupMethod.NAME_COMPONENTS]}

        role_records = []

        for row in csv_data:
            primary_id, _ = self.get_identifiers_for_lookup(row)
            if not primary_id:
                continue

            # Get AD user data
            ad_user = ad_user_dict.get(primary_id)

            # Get department and title from AD or CSV fallback
            if ad_user:
                department = ad_user.department or row.get(self.DEPARTMENT_COLUMN, '') or "Great Plains"
                title = ad_user.title or row.get(self.TITLE_COLUMN, '') or ad_user.full_name or primary_id
                username_to_use = ad_user.username
            else:
                department = row.get(self.DEPARTMENT_COLUMN, '') or "Great Plains"
                title = row.get(self.TITLE_COLUMN, '') or primary_id
                username_to_use = primary_id

            # Extract role from security role ID
            security_role_id = row.get(self.SECURITYROLEID_COLUMN, '').strip()

            if security_role_id:
                # Clean up role name and normalize
                role_name = self.clean_security_role_name(security_role_id)
                role_name = self.normalize_role_data(role_name)  # Add normalization

                role_records.append(RoleRecord(
                    username=self.normalize_role_data(username_to_use),
                    department=self.normalize_role_data(department),
                    title=self.normalize_role_data(title),
                    assigned_roles=role_name
                ))
            else:
                # No role assigned
                role_records.append(RoleRecord(
                    username=self.normalize_role_data(username_to_use),
                    department=self.normalize_role_data(department),
                    title=self.normalize_role_data(title),
                    assigned_roles='no roles'
                ))

        return role_records

    def clean_security_role_name(self, role_id: str) -> str:
        """Clean up security role ID for better readability"""
        if not role_id:
            return 'No Roles'

        # Remove common prefixes/suffixes and clean up
        cleaned = role_id.replace('_', ' ').replace('-', ' ').strip()

        # Convert to title case and fix common abbreviations
        words = cleaned.split()
        title_words = []

        for word in words:
            if word.upper() in ['ID', 'GP', 'ERP', 'HR', 'IT', 'AP', 'AR', 'GL', 'FA']:
                title_words.append(word.upper())
            elif word.lower() in ['admin', 'administrator']:
                title_words.append('Admin')
            elif word.lower() in ['mgr', 'manager']:
                title_words.append('Manager')
            elif word.lower() == 'analyst':
                title_words.append('Analyst')
            elif word.lower() == 'user':
                title_words.append('User')
            else:
                title_words.append(word.title())

        return ' '.join(title_words)