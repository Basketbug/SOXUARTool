# User Access Processor

A comprehensive Python tool for automating user access reviews and compliance auditing across multiple business applications. This tool correlates application user data with Active Directory records to identify security risks, orphaned accounts, and access discrepancies.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code Style: PEP 8](https://img.shields.io/badge/code%20style-PEP%208-orange.svg)](https://www.python.org/dev/peps/pep-0008/)

## 🎯 Purpose

This tool is designed for:
- **Compliance Teams**: Automate SOX, PCI DSS, and SOC 2 user access reviews
- **Security Analysts**: Identify orphaned accounts and access anomalies
- **IT Auditors**: Generate audit evidence and access correlation reports
- **System Administrators**: Streamline user lifecycle management

## 🏗️ Architecture

The tool follows a modular, extensible architecture:

```
user_access_processor/
├── core/
│   ├── ad_client.py          # Active Directory integration
│   ├── models.py             # Data models and enums
│   └── base_processor.py     # Abstract base processor
├── processors/
│   ├── great_plains.py       # ERP system processor
│   ├── defi_los.py          # Loan origination system
│   ├── defi_servicing.py    # Loan servicing system
│   ├── defi_xlos.py         # Extended LOS system
│   └── datascan.py          # Excel-based access reviews
├── utils/
│   ├── csv_utils.py         # CSV handling utilities
│   └── config.py            # Configuration management
├── input/                   # Input data files
├── output/                  # Generated reports
├── logs/                    # Processing logs
└── main.py                  # CLI entry point
```

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- Access to Active Directory (LDAP/LDAPS)
- Network connectivity to domain controllers

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd user-access-processor
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your Active Directory settings
   ```

### Configuration

Create a `.env` file with your Active Directory configuration:

```bash
# Active Directory Configuration
AD_SERVER=ldaps://dc.company.com:636
AD_USERNAME=svc_audit_readonly
AD_PASSWORD=your_service_account_password
BASE_DN=DC=company,DC=com
```

## 📋 Usage

### Command Line Interface

The tool provides a unified CLI for all supported applications:

```bash
# General syntax
python main.py <processor> <input_file> <output_file> [options]
```

### Supported Processors

#### 1. Great Plains (ERP System)
```bash
python main.py great_plains input/GreatPlains.csv output/GreatPlains_processed.csv
```
- **Features**: Display name lookup with name component fallback
- **Input**: CSV with username, title, department, security role ID
- **Lookup**: `displayName` → `givenName`+`sn` fallback

#### 2. Defi LOS (Loan Origination)
```bash
# Standard AD review
python main.py defi_los input/DefiLOS.csv output/DefiLOS_processed.csv

# With role extraction
python main.py defi_los input/DefiLOS.csv output/ad_review.csv --role-output output/role_analysis.csv
```
- **Features**: User Name → email username fallback, role extraction, SFS.Funding exclusion
- **Input**: CSV with User Name, email column (J), active status (K), role columns
- **Special**: Generates both AD review and role analysis outputs

#### 3. Defi Servicing (Loan Servicing)
```bash
python main.py defi_servicing input/DefiServicing.csv output/DefiServicing_processed.csv
```
- **Features**: SFSE prefix handling, status filtering
- **Input**: CSV with Application User ID (SFSE prefixed), status codes
- **Lookup**: sAMAccountName only (no backup)

#### 4. Defi XLOS (Extended LOS)
```bash
python main.py defi_xlos input/DefiXLOS.csv output/DefiXLOS_processed.csv
```
- **Features**: UserID → Email address fallback
- **Input**: CSV with UserId, Email, Status, metadata
- **Lookup**: `sAMAccountName` → `mail` attribute fallback

#### 5. Datascan (Excel Access Reviews)
```bash
python main.py datascan input/AccessReview.xlsx output/ProcessedReport.xlsx --sheet-name "Access Data"
```
- **Features**: Excel processing, permission matrix analysis, comprehensive reporting
- **Input**: Excel file with hierarchical permission structure
- **Output**: Multi-sheet Excel workbook with detailed analysis

### Advanced Options

```bash
# Disable filtering (process all records regardless of status)
python main.py defi_servicing input.csv output.csv --no-filters

# Debug logging
python main.py great_plains input.csv output.csv --log-level DEBUG

# Specify Excel sheet
python main.py datascan input.xlsx output.xlsx --sheet-name "Sheet2"
```

## 📊 Output Formats

### Standard CSV Output

All processors generate standardized CSV output with these core columns:

| Column | Description | Source |
|--------|-------------|---------|
| `username` | Resolved AD username | AD sAMAccountName |
| `email` | User email address | AD mail attribute |
| `full_name` | Display name | AD displayName |
| `department` | Business unit | AD department |
| `title` | Job title | AD title |
| `is_active` | Account status | AD userAccountControl |
| `lookup_method` | How user was found | Processing logic |
| `original_identifier` | Source identifier | Input data |

Plus application-specific columns preserving original metadata.

### Lookup Methods

| Method | Description | Confidence |
|--------|-------------|------------|
| `primary` | Direct identifier match | High |
| `backup` | Fallback lookup successful | Medium |
| `displayname` | Display name exact match | High |
| `name_components` | Name parsing successful | Medium |
| `failed` | No AD record found | N/A |
| `error` | Processing exception | N/A |

### Processing Statistics

Every execution generates comprehensive statistics:
```
Lookup Summary: {'primary': 1420, 'backup': 89, 'failed': 15}
Success Rate: 93.8% (1509/1524)
Processing Time: 2.3 minutes
Records Processed: 1524
```

## 🔧 Development

### Adding New Processors

To add support for a new application:

1. **Create processor class** in `processors/`:
   ```python
   from ..core.base_processor import BaseUserProcessor
   from ..core.models import UserRecord, LookupMethod
   
   class NewAppProcessor(BaseUserProcessor):
       def get_identifiers_for_lookup(self, row):
           # Extract primary/backup identifiers
           pass
           
       def should_skip_row(self, row):
           # Define skip criteria
           pass
           
       def create_user_record(self, csv_row, username, ad_data, lookup_method, original_identifier):
           # Create UserRecord with app-specific data
           pass
           
       def get_output_fieldnames(self):
           # Define output columns
           pass
   ```

2. **Update main.py** to include the new processor in the CLI.

3. **Add tests** for the new processor functionality.

### Code Style

This project follows PEP 8 guidelines:
- Line length: 100 characters
- Import organization: standard library, third-party, local imports
- Type hints: Required for all public methods
- Docstrings: Required for all classes and public methods

### Testing

```bash
# Run unit tests
python -m pytest tests/

# Run with coverage
python -m pytest tests/ --cov=user_access_processor

# Run specific processor tests
python -m pytest tests/test_great_plains.py
```

## 🔒 Security Considerations

### Active Directory Access
- Use dedicated read-only service account
- Implement least-privilege access principles
- Rotate service account passwords quarterly
- Monitor failed authentication attempts

### Data Protection
- Process data on secure, internal networks only
- Implement file system encryption for temporary files
- Use LDAPS (encrypted LDAP) for all AD communications
- Automatically clean up temporary processing files

### Access Controls
- Restrict tool access to authorized personnel only
- Implement role-based access to different functions
- Log all processing activities for audit trail
- Secure credential storage (environment variables)

## 📝 Logging

The tool implements comprehensive logging:

### Log Levels
- **DEBUG**: Detailed processing steps, AD queries
- **INFO**: Processing milestones, statistics
- **WARNING**: Data quality issues, backup lookups
- **ERROR**: Processing failures, connection issues

### Log Output
- **Console**: User-specified level (default: INFO)
- **File**: Always DEBUG level in `logs/` directory
- **Format**: Date-stamped files (`user_access_processor_YYYYMMDD_HHMMSS.log`)

### Audit Trail
Each execution logs:
- Command line arguments
- Configuration details (sanitized)
- Input file information
- Processing statistics
- Success/failure rates
- Error details with resolution guidance

## 🚨 Troubleshooting

### Common Issues

#### AD Connection Failures
```
ERROR - Failed to connect to AD: [Errno 11001] getaddrinfo failed
```
**Resolution**: Verify AD_SERVER hostname and network connectivity

#### Authentication Errors
```
ERROR - Failed to connect to AD: invalidCredentials
```
**Resolution**: Check AD_USERNAME and AD_PASSWORD in .env file

#### File Format Issues
```
ERROR - Required columns not found in CSV: ['User Name']
```
**Resolution**: Verify input file has required headers for the processor

#### Permission Errors
```
ERROR - Input file not found: input/data.csv
```
**Resolution**: Check file path and ensure file exists

### Getting Help

1. **Check logs**: Review the detailed log file in `logs/` directory
2. **Verify configuration**: Ensure all required environment variables are set
3. **Test connectivity**: Verify network access to domain controllers
4. **Validate input**: Check file format matches processor requirements

## 📋 Requirements

### System Requirements
- Python 3.8+
- Windows 10/11, Linux, or macOS
- 4GB RAM minimum (8GB recommended for large datasets)
- Network access to Active Directory domain controllers

### Python Dependencies
```
ldap3>=2.9.1
pandas>=1.3.0
python-dotenv>=0.19.0
openpyxl>=3.0.9
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/new-processor`
3. Implement changes following PEP 8 guidelines
4. Add comprehensive tests
5. Update documentation
6. Submit a pull request

### Development Setup

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Run code quality checks
flake8 user_access_processor/
black user_access_processor/
mypy user_access_processor/
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Support

For questions, issues, or feature requests:
- **Internal Users**: Contact IT Security Team
- **Issues**: Use the GitHub issue tracker
- **Documentation**: See `docs/` directory for detailed guides

## 🔄 Version History

### v2.0.0 (Current)
- Refactored architecture with modular processors
- Added comprehensive logging and audit trail
- Implemented standardized output formats
- Enhanced error handling and validation
- Added support for Excel files (Datascan)

### v1.x (Legacy)
- Individual scripts per application
- Basic CSV processing
- Limited error handling

---

**⚠️ Important**: This tool processes sensitive user data. Ensure compliance with your organization's data handling policies and applicable regulations (SOX, PCI DSS, GDPR, etc.) before use.