# =============================================================================
# utils/config.py - Configuration management
# =============================================================================

import os
from typing import Optional, List
from dotenv import load_dotenv


class Config:
    """Configuration management"""

    def __init__(self):
        load_dotenv()

    @property
    def ad_server(self) -> Optional[str]:
        return os.getenv("AD_SERVER")

    @property
    def ad_username(self) -> Optional[str]:
        return os.getenv("AD_USERNAME")

    @property
    def ad_password(self) -> Optional[str]:
        return os.getenv("AD_PASSWORD")

    @property
    def base_dn(self) -> Optional[str]:
        return os.getenv("BASE_DN")

    def validate_ad_config(self) -> bool:
        """Validate that all required AD configuration is present"""
        required = [self.ad_server, self.ad_username, self.ad_password, self.base_dn]
        return all(required)

    def get_missing_ad_vars(self) -> List[str]:
        """Get list of missing AD configuration variables"""
        vars_and_names = [
            (self.ad_server, "AD_SERVER"),
            (self.ad_username, "AD_USERNAME"),
            (self.ad_password, "AD_PASSWORD"),
            (self.base_dn, "BASE_DN")
        ]
        return [name for var, name in vars_and_names if not var]