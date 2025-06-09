# =============================================================================
# core/ad_client.py - Unified Active Directory client
# =============================================================================

import logging
from typing import Dict, Any, Optional
from ldap3 import Server, Connection, ALL
from core.models import LookupMethod


class ActiveDirectoryClient:
    """Unified Active Directory client with multiple lookup strategies"""

    def __init__(self, server_url: str, username: str, password: str, base_dn: str):
        self.server_url = server_url
        self.username = username
        self.password = password
        self.base_dn = base_dn
        self.connection: Optional[Connection] = None
        self.logger = logging.getLogger(__name__)

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()

    def connect(self) -> bool:
        """Establish connection to Active Directory"""
        try:
            server = Server(self.server_url, get_info=ALL)
            self.connection = Connection(
                server,
                user=self.username,
                password=self.password,
                auto_bind=True
            )
            self.logger.info("Successfully connected to Active Directory")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to AD: {e}")
            return False

    def disconnect(self) -> None:
        """Close Active Directory connection"""
        if self.connection:
            self.connection.unbind()
            self.connection = None
            self.logger.info("Disconnected from Active Directory")

    def query_user_by_samaccountname(self, samaccountname: str) -> Dict[str, Any]:
        """Query user by sAMAccountName"""
        return self._query_user(f"(sAMAccountName={samaccountname})", samaccountname)

    def query_user_by_email(self, email: str) -> Dict[str, Any]:
        """Query user by email address"""
        return self._query_user(f"(mail={email})", email)

    def query_user_by_displayname(self, display_name: str) -> Dict[str, Any]:
        """Query user by display name"""
        return self._query_user(f"(displayName={display_name})", display_name)

    def query_user_by_name_components(self, firstname: str, lastname: str) -> Dict[str, Any]:
        """Query user by first and last name components"""
        search_filter = f"(&(givenName={firstname})(sn={lastname}))"
        return self._query_user(search_filter, f"{firstname} {lastname}")

    def _query_user(self, search_filter: str, identifier: str) -> Dict[str, Any]:
        """Internal method to perform AD query"""
        if not self.connection:
            raise ConnectionError("Not connected to Active Directory")

        try:
            attributes = [
                'mail', 'displayName', 'department', 'userAccountControl',
                'sAMAccountName', 'title', 'givenName', 'sn'
            ]

            self.connection.search(
                search_base=self.base_dn,
                search_filter=search_filter,
                attributes=attributes
            )

            if self.connection.entries:
                if len(self.connection.entries) > 1:
                    self.logger.warning(f"Multiple users found for {identifier}, using first match")

                entry = self.connection.entries[0]
                result = {
                    'email': str(entry.mail) if entry.mail else "",
                    'full_name': str(entry.displayName) if entry.displayName else "",
                    'department': str(entry.department) if entry.department else "",
                    'title': str(entry.title) if entry.title else "",
                    'is_active': self._is_account_active(
                        entry.userAccountControl.value if entry.userAccountControl else 0
                    ),
                    'samaccountname': str(entry.sAMAccountName) if entry.sAMAccountName else "",
                    'given_name': str(entry.givenName) if entry.givenName else "",
                    'surname': str(entry.sn) if entry.sn else ""
                }
                self.logger.debug(f"Found user {identifier} in AD")
                return result
            else:
                self.logger.debug(f"User {identifier} not found in AD")
                return {}

        except Exception as e:
            self.logger.error(f"Error querying user {identifier}: {e}")
            return {}

    def _is_account_active(self, user_account_control: int) -> bool:
        """Check if user account is active based on userAccountControl flags"""
        # 0x2 = ACCOUNTDISABLE flag
        return not bool(user_account_control & 0x2)