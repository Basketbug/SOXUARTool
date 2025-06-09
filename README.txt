# Project Structure:
#
# user_access_processor/
# ├── __init__.py
# ├── core/
# │   ├── __init__.py
# │   ├── ad_client.py          # Active Directory operations
# │   ├── models.py             # Data classes and models
# │   └── base_processor.py     # Abstract base processor
# ├── processors/
# │   ├── __init__.py
# │   ├── great_plains.py       # Great Plains specific logic
# │   ├── defi_los.py          # Defi LOS specific logic
# │   ├── defi_servicing.py    # Defi Servicing specific logic
# │   ├── defi_xlos.py         # Defi XLOS specific logic
# │   └── datascan.py          # Datascan specific logic
# ├── utils/
# │   ├── __init__.py
# │   ├── csv_utils.py         # CSV reading/writing utilities
# │   └── config.py            # Configuration management
# └── main.py                  # Entry point with CLI