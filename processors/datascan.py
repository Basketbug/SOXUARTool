# =============================================================================
# processors/datascan.py - Datascan Excel processor
# =============================================================================

import logging
from typing import Dict, Optional

import pandas as pd

from core.ad_client import ActiveDirectoryClient


class DatascanProcessor:
    """
    Datascan processor for Excel files with hierarchical structure.
    This processor is different from others as it works with Excel files
    and has more complex processing requirements.
    """

    def __init__(self, ad_client: ActiveDirectoryClient, file_path: str, sheet_name: Optional[str] = None):
        self.ad_client = ad_client
        self.file_path = file_path
        self.sheet_name = sheet_name
        self.raw_data = None
        self.processed_data = None
        self.ad_users_cache = {}
        self.logger = logging.getLogger(self.__class__.__name__)

    def normalize_name(self, name: str) -> str:
        """Normalize a name by removing extra spaces and standardizing format"""
        if not name or pd.isna(name):
            return ""
        return ' '.join(name.strip().split())

    def search_ad_user(self, display_name: str) -> Optional[Dict]:
        """Search for a user in Active Directory with multiple strategies"""
        normalized_name = self.normalize_name(display_name)

        # Check cache first
        if normalized_name in self.ad_users_cache:
            return self.ad_users_cache[normalized_name]

        try:
            # Try multiple search strategies
            search_methods = [
                ('displayName', lambda name: self.ad_client.query_user_by_displayname(name)),
                ('email', lambda name: self.ad_client.query_user_by_email(name) if '@' in name else {}),
            ]

            # If name contains space, also try name components
            if ' ' in normalized_name:
                parts = normalized_name.split()
                if len(parts) >= 2:
                    firstname, lastname = parts[0], parts[-1]
                    search_methods.append(
                        ('name_components', lambda _: self.ad_client.query_user_by_name_components(firstname, lastname))
                    )

            user_found = None
            for method_name, search_func in search_methods:
                try:
                    ad_result = search_func(normalized_name)
                    if ad_result:
                        user_found = ad_result
                        self.logger.debug(f"Found user with method: {method_name}")
                        break
                except Exception as e:
                    self.logger.debug(f"Search method {method_name} failed: {e}")
                    continue

            if user_found:
                user_info = {
                    'found': True,
                    'original_search_name': display_name,
                    'normalized_search_name': normalized_name,
                    'displayName': user_found.get('full_name', ''),
                    'sAMAccountName': user_found.get('samaccountname', ''),
                    'email': user_found.get('email', ''),
                    'department': user_found.get('department', ''),
                    'title': user_found.get('title', ''),
                    'account_disabled': not user_found.get('is_active', True),
                }
            else:
                user_info = {
                    'found': False,
                    'original_search_name': display_name,
                    'normalized_search_name': normalized_name
                }

            self.ad_users_cache[normalized_name] = user_info
            return user_info

        except Exception as e:
            self.logger.error(f"Error searching for user '{display_name}': {e}")
            return {
                'found': False,
                'original_search_name': display_name,
                'normalized_search_name': normalized_name,
                'error': str(e)
            }

    def load_data(self) -> pd.DataFrame:
        """Load the Excel file with proper handling of merged cells"""
        if self.sheet_name:
            self.raw_data = pd.read_excel(self.file_path, sheet_name=self.sheet_name)
        else:
            self.raw_data = pd.read_excel(self.file_path)

        # Clean column names
        self.raw_data.columns = self.raw_data.columns.str.strip()

        # Forward fill merged cells
        if 'User Name' in self.raw_data.columns:
            self.raw_data['User Name'] = self.raw_data['User Name'].fillna(method='ffill')
        if 'User Role(s)' in self.raw_data.columns:
            self.raw_data['User Role(s)'] = self.raw_data['User Role(s)'].fillna(method='ffill')

        # Remove empty rows
        self.raw_data = self.raw_data.dropna(how='all')

        return self.raw_data

    def process_permissions(self) -> pd.DataFrame:
        """Process the raw data to create clean permission structure"""
        if self.raw_data is None:
            self.load_data()

        df = self.raw_data.copy()

        # Convert X markers to boolean flags
        permission_columns = ['View', 'Add/Edit', 'Delete']
        for col in permission_columns:
            if col in df.columns:
                df[col] = df[col].notna() & (df[col].astype(str).str.upper() == 'X')
            else:
                df[col] = False

        # Remove rows with no permissions
        df = df[df[permission_columns].any(axis=1)]

        # Clean text columns
        text_columns = ['User Name', 'User Role(s)', 'Functional Area', 'Feature', 'Function']
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace('nan', '')

        self.processed_data = df
        return df

    def validate_users_against_ad(self) -> pd.DataFrame:
        """Validate all users against Active Directory"""
        if self.processed_data is None:
            self.process_permissions()

        unique_users = self.processed_data['User Name'].unique()
        validation_results = []

        self.logger.info(f"Validating {len(unique_users)} users against Active Directory...")

        for user_name in unique_users:
            if pd.isna(user_name) or str(user_name).strip() == '':
                continue

            ad_result = self.search_ad_user(str(user_name))

            if ad_result:
                validation_results.append({
                    'User_Name_From_Report': user_name,
                    'Normalized_Name': ad_result.get('normalized_search_name', ''),
                    'Found_In_AD': ad_result.get('found', False),
                    'AD_DisplayName': ad_result.get('displayName', ''),
                    'AD_Username': ad_result.get('sAMAccountName', ''),
                    'AD_Email': ad_result.get('email', ''),
                    'AD_Department': ad_result.get('department', ''),
                    'AD_Title': ad_result.get('title', ''),
                    'Account_Disabled': ad_result.get('account_disabled', False),
                    'Search_Error': ad_result.get('error', '')
                })

        validation_df = pd.DataFrame(validation_results)

        if not validation_df.empty:
            found_count = validation_df['Found_In_AD'].sum()
            disabled_count = validation_df['Account_Disabled'].sum()

            self.logger.info(f"AD Validation Summary:")
            self.logger.info(f"  - Users found in AD: {found_count}/{len(validation_df)}")
            self.logger.info(f"  - Disabled accounts: {disabled_count}")
            self.logger.info(f"  - Users not found: {len(validation_df) - found_count}")

        return validation_df

    def get_orphaned_access_report(self) -> pd.DataFrame:
        """Generate report of access for users not found in AD or disabled"""
        validation_df = self.validate_users_against_ad()

        problematic_users = validation_df[
            (validation_df['Found_In_AD'] == False) |
            (validation_df['Account_Disabled'] == True)
            ]['User_Name_From_Report'].tolist()

        if not problematic_users:
            return pd.DataFrame()

        orphaned_access = self.processed_data[
            self.processed_data['User Name'].isin(problematic_users)
        ].copy()

        # Add AD validation info
        orphaned_access = orphaned_access.merge(
            validation_df[['User_Name_From_Report', 'Found_In_AD', 'Account_Disabled', 'AD_Username']],
            left_on='User Name',
            right_on='User_Name_From_Report',
            how='left'
        )

        # Create risk assessment
        def assess_risk(row):
            if not row['Found_In_AD']:
                return 'High - User not found in AD'
            elif row['Account_Disabled']:
                return 'High - Account disabled in AD'
            else:
                return 'Low'

        orphaned_access['Risk_Level'] = orphaned_access.apply(assess_risk, axis=1)

        return orphaned_access[['User Name', 'User Role(s)', 'Functional Area', 'Feature',
                                'Function', 'View', 'Add/Edit', 'Delete', 'Found_In_AD',
                                'Account_Disabled', 'AD_Username', 'Risk_Level']]

    def get_user_summary(self) -> pd.DataFrame:
        """Create summary of users and their roles"""
        if self.processed_data is None:
            self.process_permissions()

        user_summary = (self.processed_data
                        .groupby(['User Name', 'User Role(s)'])
                        .agg({
            'Functional Area': lambda x: list(x.dropna().unique()),
            'View': 'sum',
            'Add/Edit': 'sum',
            'Delete': 'sum'
        })
                        .reset_index())

        return user_summary

    def get_permission_matrix(self) -> pd.DataFrame:
        """Create detailed permission matrix"""
        if self.processed_data is None:
            self.process_permissions()

        def get_permission_level(row):
            permissions = []
            if row['View']:
                permissions.append('View')
            if row['Add/Edit']:
                permissions.append('Add/Edit')
            if row['Delete']:
                permissions.append('Delete')
            return ', '.join(permissions) if permissions else 'No Access'

        matrix = self.processed_data.copy()
        matrix['Permission_Level'] = matrix.apply(get_permission_level, axis=1)

        return matrix[['User Name', 'User Role(s)', 'Functional Area',
                       'Feature', 'Function', 'Permission_Level']]

    def identify_high_risk_users(self, delete_threshold: int = 5) -> pd.DataFrame:
        """Identify users with extensive delete permissions"""
        if self.processed_data is None:
            self.process_permissions()

        user_delete_count = (self.processed_data
                             .groupby(['User Name', 'User Role(s)'])
                             .agg({'Delete': 'sum'})
                             .reset_index())

        high_risk = user_delete_count[user_delete_count['Delete'] >= delete_threshold]
        return high_risk.sort_values('Delete', ascending=False)

    def export_processed_data(self, output_path: str):
        """Export all processed data to Excel file with multiple sheets"""
        if self.processed_data is None:
            self.process_permissions()

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Raw processed data
            self.processed_data.to_excel(writer, sheet_name='Processed_Data', index=False)

            # User summary
            user_summary = self.get_user_summary()
            user_summary.to_excel(writer, sheet_name='User_Summary', index=False)

            # Permission matrix
            permission_matrix = self.get_permission_matrix()
            permission_matrix.to_excel(writer, sheet_name='Permission_Matrix', index=False)

            # High-risk users
            high_risk = self.identify_high_risk_users()
            high_risk.to_excel(writer, sheet_name='High_Risk_Users', index=False)

            # AD validation results
            try:
                ad_validation = self.validate_users_against_ad()
                if not ad_validation.empty:
                    ad_validation.to_excel(writer, sheet_name='AD_Validation', index=False)

                # Orphaned access report
                orphaned_access = self.get_orphaned_access_report()
                if not orphaned_access.empty:
                    orphaned_access.to_excel(writer, sheet_name='Orphaned_Access', index=False)

            except Exception as e:
                self.logger.warning(f"Could not generate AD validation reports: {e}")