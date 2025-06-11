#!/usr/bin/env python3
"""
Access Review Analyzer
Automatically identifies standard vs. ad-hoc role assignments based on department and title patterns.

Usage:
    python access_review.py input.csv [--threshold 70] [--output report.txt] [--csv-export recommendations.csv]

6/11/2025 Bug Fix - Access Review Analyzer
Key fixes:
1. Count unique users per department/title combination (not role assignments)
2. Fixed percentage calculation to use unique user count
3. Improved role parsing to handle multiple roles per user properly
4. Added debug logging to verify counts
"""

import csv
import argparse
import sys
from collections import defaultdict
from typing import Dict, List, Tuple
import json


class AccessReviewAnalyzer:
    def __init__(self, threshold: int = 70):
        """
        Initialize the analyzer with a threshold percentage for standard roles.

        Args:
            threshold: Percentage threshold for considering a role "standard" (default: 70)
        """
        self.threshold = threshold
        self.data = []
        self.analysis = []

    def load_csv(self, file_path: str) -> bool:
        """
        Load user access data from CSV file.

        Args:
            file_path: Path to the CSV file

        Returns:
            bool: True if successful, False otherwise
        """
        required_columns = ['username', 'department', 'title', 'assigned_roles']

        try:
            # Try UTF-8 with BOM first, then fallback to UTF-8
            encodings = ['utf-8-sig', 'utf-8', 'latin-1']
            csvfile = None

            for encoding in encodings:
                try:
                    csvfile = open(file_path, 'r', newline='', encoding=encoding)
                    # Test read a small sample
                    sample = csvfile.read(1024)
                    csvfile.seek(0)
                    break
                except UnicodeDecodeError:
                    if csvfile:
                        csvfile.close()
                    continue

            if not csvfile:
                print("Error: Could not decode CSV file with any supported encoding")
                return False

            try:
                # Detect delimiter
                sniffer = csv.Sniffer()
                delimiter = sniffer.sniff(sample).delimiter

                reader = csv.DictReader(csvfile, delimiter=delimiter)

                # Clean and validate headers - remove BOM and normalize
                raw_fieldnames = list(reader.fieldnames)

                # Handle case where entire header is in one field (CSV parsing issue)
                if len(raw_fieldnames) == 1 and ',' in raw_fieldnames[0]:
                    print("Debug - Detected single field with commas, splitting manually...")
                    # Split the single field by commas
                    split_headers = raw_fieldnames[0].split(',')
                    fieldnames = [field.strip().lower().lstrip('\ufeff\ufffe') for field in split_headers]

                    # Re-create the reader with proper headers
                    csvfile.seek(0)
                    # Skip the header line since we'll handle it manually
                    next(csvfile)
                    reader = csv.reader(csvfile, delimiter=delimiter)
                    manual_headers = True
                else:
                    fieldnames = []
                    for field in raw_fieldnames:
                        # Remove BOM, whitespace, and normalize case
                        clean_field = field.strip().lower()
                        # Remove any remaining BOM characters
                        clean_field = clean_field.lstrip('\ufeff\ufffe')
                        fieldnames.append(clean_field)
                    manual_headers = False

                print(f"Debug - Raw headers: {raw_fieldnames}")
                print(f"Debug - Cleaned headers: {fieldnames}")

                # Check for required columns
                missing_columns = [col for col in required_columns if col not in fieldnames]
                if missing_columns:
                    print(f"Error: Missing required columns: {', '.join(missing_columns)}")
                    print(f"Found columns: {', '.join(fieldnames)}")
                    print(f"Original headers: {', '.join(raw_fieldnames)}")

                    # Try to suggest column mapping
                    print(f"\nTrying to match columns...")
                    for req_col in required_columns:
                        matches = [col for col in fieldnames if
                                   req_col.replace('_', ' ') in col or req_col.replace('_', '') in col.replace(' ', '')]
                        if matches:
                            print(f"  Possible match for '{req_col}': {matches}")

                    return False

                # Read raw data first
                raw_data = []
                if manual_headers:
                    # Handle manually split headers - need to split data rows too
                    print("Debug - Processing data rows with manual splitting...")
                    for row_num, line in enumerate(csvfile, start=2):
                        line = line.strip()
                        if not line:
                            continue

                        # Split the line by commas, handling quoted fields
                        try:
                            # Use csv.reader on a single line to handle quoted fields properly
                            import io
                            line_reader = csv.reader(io.StringIO(line), delimiter=delimiter)
                            row = next(line_reader)
                        except:
                            # Fallback to simple split if csv.reader fails
                            row = line.split(delimiter)

                        if len(row) >= len(fieldnames):
                            cleaned_row = {}
                            for i, field_name in enumerate(fieldnames):
                                value = row[i].strip().strip('"') if i < len(row) and row[i] else ''
                                cleaned_row[field_name] = value

                            # Validate required fields
                            if all(cleaned_row.get(col) for col in required_columns):
                                raw_data.append(cleaned_row)
                            else:
                                missing_fields = [col for col in required_columns if not cleaned_row.get(col)]
                                print(
                                    f"Warning: Skipping row {row_num} - missing data for: {', '.join(missing_fields)}")
                        else:
                            print(
                                f"Warning: Skipping row {row_num} - insufficient columns (got {len(row)}, need {len(fieldnames)})")
                else:
                    # Standard DictReader processing
                    for row_num, row in enumerate(reader, start=2):
                        # Clean row data and map to clean fieldnames
                        cleaned_row = {}
                        for original_key, clean_key in zip(raw_fieldnames, fieldnames):
                            value = row.get(original_key, '').strip() if row.get(original_key) else ''
                            cleaned_row[clean_key] = value

                        # Validate required fields
                        if all(cleaned_row.get(col) for col in required_columns):
                            raw_data.append(cleaned_row)
                        else:
                            missing_fields = [col for col in required_columns if not cleaned_row.get(col)]
                            print(f"Warning: Skipping row {row_num} - missing data for: {', '.join(missing_fields)}")

                # CRITICAL FIX: Aggregate roles per user
                print(f"Debug - Raw data loaded: {len(raw_data)} records")

                # Group by user key (username + department + title)
                user_roles = defaultdict(set)
                user_info = {}

                for row in raw_data:
                    user_key = f"{row['username']}|{row['department']}|{row['title']}"

                    # Store user info (same for all rows of this user)
                    if user_key not in user_info:
                        user_info[user_key] = {
                            'username': row['username'],
                            'department': row['department'],
                            'title': row['title']
                        }

                    # Add role to user's set of roles
                    role = row['assigned_roles'].strip()
                    if role:
                        user_roles[user_key].add(role)
                    else:
                        # Handle users with no roles
                        user_roles[user_key].add('no roles')

                # Convert back to the expected format (one row per user with comma-separated roles)
                self.data = []
                for user_key, roles in user_roles.items():
                    user_record = user_info[user_key].copy()
                    user_record['assigned_roles'] = ', '.join(sorted(roles))
                    self.data.append(user_record)

                print(f"Debug - After aggregation: {len(self.data)} unique users")

                # Show example of aggregated data
                if self.data:
                    sample_user = self.data[0]
                    print(
                        f"Debug - Sample aggregated user: {sample_user['username']} has roles: {sample_user['assigned_roles']}")

                if not self.data:
                    print("Error: No valid data found in CSV file")
                    return False

                print(f"Successfully loaded {len(self.data)} user records")
                return True

            finally:
                if csvfile:
                    csvfile.close()

        except FileNotFoundError:
            print(f"Error: File '{file_path}' not found")
            return False
        except Exception as e:
            print(f"Error reading CSV file: {str(e)}")
            return False

    def analyze_access(self) -> List[Dict]:
        """
        FIXED: Analyze user access patterns and identify standard vs. ad-hoc roles.
        Key fix: Count unique users per department/title, not role assignments.

        Returns:
            List of analysis results for each department/title group
        """
        if not self.data:
            print("Error: No data loaded. Please load a CSV file first.")
            return []

        # Group users by department and title - KEY FIX: Track unique users and role frequency
        groups = defaultdict(lambda: {
            'unique_users': set(),  # FIX: Track unique users
            'user_roles': defaultdict(set),  # Track which roles each user has
            'role_frequency': defaultdict(int)
        })

        for user in self.data:
            group_key = f"{user['department']}|{user['title']}"
            username = user['username']

            # FIX: Add user to unique set
            groups[group_key]['unique_users'].add(username)

            # Parse roles (handle comma-separated values)
            roles_str = user['assigned_roles']
            roles = [role.strip() for role in roles_str.split(',') if role.strip()]

            for role in roles:
                # FIX: Only count each user once per role
                if role not in groups[group_key]['user_roles'][username]:
                    groups[group_key]['user_roles'][username].add(role)
                    groups[group_key]['role_frequency'][role] += 1

        # Analyze each group
        self.analysis = []

        for group_key, group_data in groups.items():
            department, title = group_key.split('|', 1)
            total_users = len(group_data['unique_users'])  # FIX: Use unique user count

            role_analysis = []
            standard_roles = []
            adhoc_roles = []

            for role, count in group_data['role_frequency'].items():
                percentage = (count / total_users) * 100  # FIX: Use unique user count
                is_standard = percentage >= self.threshold

                role_info = {
                    'role': role,
                    'count': count,
                    'percentage': percentage,
                    'is_standard': is_standard
                }

                role_analysis.append(role_info)

                if is_standard:
                    standard_roles.append(role_info)
                else:
                    adhoc_roles.append(role_info)

            # Sort roles by percentage (descending)
            role_analysis.sort(key=lambda x: x['percentage'], reverse=True)
            standard_roles.sort(key=lambda x: x['percentage'], reverse=True)
            adhoc_roles.sort(key=lambda x: x['percentage'], reverse=True)

            # FIX: Convert users list properly
            users_list = []
            for username in group_data['unique_users']:
                # Find the original user record to get all info
                user_record = next((u for u in self.data if u['username'] == username and
                                    u['department'] == department and u['title'] == title), None)
                if user_record:
                    users_list.append(user_record)

            group_analysis = {
                'department': department,
                'title': title,
                'total_users': total_users,
                'role_analysis': role_analysis,
                'standard_roles': standard_roles,
                'adhoc_roles': adhoc_roles,
                'has_adhoc_assignments': len(adhoc_roles) > 0,
                'users': users_list
            }

            self.analysis.append(group_analysis)

        # Sort groups by department, then title
        self.analysis.sort(key=lambda x: (x['department'], x['title']))

        print(f"Analysis complete. Found {len(self.analysis)} department/title groups.")
        return self.analysis

    def get_summary_stats(self) -> Dict:
        """
        Get summary statistics from the analysis.

        Returns:
            Dictionary with summary statistics
        """
        if not self.analysis:
            return {}

        total_groups = len(self.analysis)
        groups_with_adhoc = sum(1 for group in self.analysis if group['has_adhoc_assignments'])
        total_standard_roles = sum(len(group['standard_roles']) for group in self.analysis)
        total_adhoc_roles = sum(len(group['adhoc_roles']) for group in self.analysis)
        total_users = sum(group['total_users'] for group in self.analysis)

        return {
            'total_groups': total_groups,
            'groups_with_adhoc': groups_with_adhoc,
            'groups_standard_only': total_groups - groups_with_adhoc,
            'total_standard_roles': total_standard_roles,
            'total_adhoc_roles': total_adhoc_roles,
            'total_users': total_users,
            'compliance_rate': ((total_groups - groups_with_adhoc) / total_groups * 100) if total_groups > 0 else 0
        }

    def print_summary(self):
        """Print a summary of the analysis results to console."""
        if not self.analysis:
            print("No analysis results available.")
            return

        stats = self.get_summary_stats()

        print("\n" + "=" * 80)
        print("ACCESS REVIEW ANALYSIS SUMMARY")
        print("=" * 80)
        print(f"Threshold for standard roles: {self.threshold}%")
        print(f"Total users analyzed: {stats['total_users']}")
        print(f"Total department/title groups: {stats['total_groups']}")
        print(f"Groups with standard roles only: {stats['groups_standard_only']}")
        print(f"Groups requiring review (have ad-hoc roles): {stats['groups_with_adhoc']}")
        print(f"Compliance rate: {stats['compliance_rate']:.1f}%")
        print(f"Total standard role assignments: {stats['total_standard_roles']}")
        print(f"Total ad-hoc role assignments: {stats['total_adhoc_roles']}")
        print("=" * 80)

    def print_detailed_analysis(self):
        """Print detailed analysis results to console."""
        if not self.analysis:
            print("No analysis results available.")
            return

        for group in self.analysis:
            print(f"\n{'=' * 60}")
            print(f"DEPARTMENT: {group['department']} | TITLE: {group['title']}")
            print(f"{'=' * 60}")
            print(f"Total users: {group['total_users']}")

            if group['has_adhoc_assignments']:
                print("⚠️  STATUS: REQUIRES REVIEW (has ad-hoc role assignments)")
            else:
                print("✅ STATUS: COMPLIANT (standard roles only)")

            # Standard Roles
            print(f"\n🟢 STANDARD ROLES (≥{self.threshold}%):")
            if group['standard_roles']:
                for role in group['standard_roles']:
                    print(
                        f"   • {role['role']:.<40} {role['count']:>3}/{group['total_users']:<3} ({role['percentage']:>5.1f}%)")
                print(f"\n   📝 RECOMMENDATION: Apply these {len(group['standard_roles'])} roles to ALL")
                print(f"      {group['title']}s in {group['department']} department")
            else:
                print("   (No standard roles identified)")

            # Ad-hoc Roles
            print(f"\n🟡 AD-HOC ROLES (<{self.threshold}%):")
            if group['adhoc_roles']:
                for role in group['adhoc_roles']:
                    print(
                        f"   • {role['role']:.<40} {role['count']:>3}/{group['total_users']:<3} ({role['percentage']:>5.1f}%)")
                print(f"\n   ⚠️  ACTION REQUIRED: Review {len(group['adhoc_roles'])} ad-hoc role assignments")
                print("      Consider role removal or document business justification")
            else:
                print("   (No ad-hoc roles found)")

    def export_csv_recommendations(self, output_file: str):
        """
        Export recommendations to CSV file.

        Args:
            output_file: Path to output CSV file
        """
        if not self.analysis:
            print("No analysis results to export.")
            return

        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['department', 'title', 'role', 'user_count', 'total_users',
                              'percentage', 'status', 'recommendation']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                for group in self.analysis:
                    for role in group['role_analysis']:
                        status = 'Standard' if role['is_standard'] else 'Ad-hoc'
                        recommendation = (
                            f"Apply to all {group['title']}s in {group['department']}"
                            if role['is_standard']
                            else "Review individual assignments - consider removal or document justification"
                        )

                        writer.writerow({
                            'department': group['department'],
                            'title': group['title'],
                            'role': role['role'],
                            'user_count': role['count'],
                            'total_users': group['total_users'],
                            'percentage': f"{role['percentage']:.1f}",
                            'status': status,
                            'recommendation': recommendation
                        })

            print(f"✅ CSV recommendations exported to: {output_file}")

        except Exception as e:
            print(f"Error exporting CSV: {str(e)}")

    def export_actionable_csv(self, output_file: str):
        """
        Export actionable CSV for IAM teams to implement recommendations.

        Args:
            output_file: Path to output actionable CSV file
        """
        if not self.analysis:
            print("No analysis results to export.")
            return

        print(f"Creating actionable CSV with {len(self.analysis)} groups...")

        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'action_type', 'priority', 'department', 'title', 'role', 'username',
                    'current_status', 'recommended_action', 'business_justification_required',
                    'percentage_compliance', 'affected_users', 'implementation_notes'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                total_actions = 0

                for group in self.analysis:
                    dept = group['department']
                    title = group['title']
                    total_users = group['total_users']

                    print(f"Processing group: {dept} - {title} ({total_users} users)")

                    # Create actions for standard roles (GRANT access)
                    for role_info in group['standard_roles']:
                        role = role_info['role']

                        # Find users who DON'T have this standard role
                        users_with_role = set()
                        for user in group['users']:
                            user_roles = [r.strip() for r in user['assigned_roles'].split(',') if r.strip()]

                            # DEBUG: Print role comparison for troubleshooting
                            if 'jodi' in user['username'].lower():
                                print(f"    DEBUG - Checking if Jodi has role '{role}':")
                                print(f"      Jodi's roles: {user_roles}")
                                print(f"      Looking for: '{role}'")
                                print(f"      Match found: {role in user_roles}")

                            if role in user_roles:
                                users_with_role.add(user['username'])

                        users_without_role = [u for u in group['users'] if u['username'] not in users_with_role]

                        print(f"  Standard role '{role}': {len(users_without_role)} users need access")

                        # Only create GRANT actions if there are actually users missing the role
                        if len(users_without_role) > 0:
                            for user in users_without_role:
                                writer.writerow({
                                    'action_type': 'GRANT_ACCESS',
                                    'priority': 'HIGH',
                                    'department': dept,
                                    'title': title,
                                    'role': role,
                                    'username': user['username'],
                                    'current_status': 'MISSING_STANDARD_ROLE',
                                    'recommended_action': f'Grant {role} access',
                                    'business_justification_required': 'NO',
                                    'percentage_compliance': f"{role_info['percentage']:.1f}%",
                                    'affected_users': f"{len(users_without_role)} of {total_users}",
                                    'implementation_notes': f'Standard role for {title}s in {dept} - {role_info["count"]}/{total_users} currently have this role'
                                })
                                total_actions += 1

                    # Create actions for ad-hoc roles (REVIEW/REMOVE access)
                    for role_info in group['adhoc_roles']:
                        role = role_info['role']

                        # Find users who DO have this ad-hoc role
                        users_with_adhoc_role = []
                        for user in group['users']:
                            user_roles = [r.strip() for r in user['assigned_roles'].split(',') if r.strip()]
                            if role in user_roles:
                                users_with_adhoc_role.append(user)

                        priority = 'MEDIUM' if role_info['percentage'] >= 25 else 'LOW'

                        print(f"  Ad-hoc role '{role}': {len(users_with_adhoc_role)} users need review")

                        for user in users_with_adhoc_role:
                            writer.writerow({
                                'action_type': 'REVIEW_ACCESS',
                                'priority': priority,
                                'department': dept,
                                'title': title,
                                'role': role,
                                'username': user['username'],
                                'current_status': 'HAS_ADHOC_ROLE',
                                'recommended_action': 'Review and document business justification OR remove access',
                                'business_justification_required': 'YES',
                                'percentage_compliance': f"{role_info['percentage']:.1f}%",
                                'affected_users': f"{role_info['count']} of {total_users}",
                                'implementation_notes': f'Ad-hoc role - only {role_info["count"]}/{total_users} {title}s have this role. Verify business need.'
                            })
                            total_actions += 1

                    # Create summary action for groups with perfect compliance
                    if not group['has_adhoc_assignments'] and group['standard_roles']:
                        print(f"  Group is compliant - no actions needed")
                        writer.writerow({
                            'action_type': 'NO_ACTION',
                            'priority': 'INFO',
                            'department': dept,
                            'title': title,
                            'role': 'ALL_ROLES',
                            'username': 'N/A',
                            'current_status': 'COMPLIANT',
                            'recommended_action': 'No action required - group is fully compliant',
                            'business_justification_required': 'NO',
                            'percentage_compliance': '100.0%',
                            'affected_users': f"All {total_users} users",
                            'implementation_notes': f'This group has proper role standardization with {len(group["standard_roles"])} standard roles'
                        })
                        total_actions += 1
                    elif not group['standard_roles'] and not group['adhoc_roles']:
                        print(f"  Group has no roles defined")
                        writer.writerow({
                            'action_type': 'INVESTIGATE',
                            'priority': 'MEDIUM',
                            'department': dept,
                            'title': title,
                            'role': 'NO_ROLES',
                            'username': 'N/A',
                            'current_status': 'NO_ROLES_DEFINED',
                            'recommended_action': 'Investigate - group has no role assignments',
                            'business_justification_required': 'YES',
                            'percentage_compliance': '0.0%',
                            'affected_users': f"All {total_users} users",
                            'implementation_notes': f'No users in this group have any roles assigned - verify if this is correct'
                        })
                        total_actions += 1

            print(f"✅ Actionable CSV for IAM team exported to: {output_file}")
            print(f"   📊 Total actions created: {total_actions}")

            if total_actions == 0:
                print("   ⚠️  No actions were generated - all groups may be perfectly compliant")

        except Exception as e:
            print(f"Error exporting actionable CSV: {str(e)}")
            import traceback
            traceback.print_exc()

    def _get_action_summary(self) -> Dict:
        """Get summary of actions that would be created."""
        grant_actions = 0
        review_actions = 0
        compliant_groups = 0

        for group in self.analysis:
            # Count users missing standard roles
            for role_info in group['standard_roles']:
                role = role_info['role']
                users_with_role = 0
                for user in group['users']:
                    user_roles = [r.strip() for r in user['assigned_roles'].split(',') if r.strip()]
                    if role in user_roles:
                        users_with_role += 1
                grant_actions += group['total_users'] - users_with_role

            # Count users with ad-hoc roles
            for role_info in group['adhoc_roles']:
                review_actions += role_info['count']

            # Count compliant groups
            if not group['has_adhoc_assignments'] and group['standard_roles']:
                compliant_groups += 1

        return {
            'total_actions': grant_actions + review_actions + compliant_groups,
            'grant_actions': grant_actions,
            'review_actions': review_actions,
            'compliant_groups': compliant_groups
        }

    def export_text_report(self, output_file: str):
        """
        Export detailed analysis report to text file.

        Args:
            output_file: Path to output text file
        """
        if not self.analysis:
            print("No analysis results to export.")
            return

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                # Redirect print to file
                import sys
                original_stdout = sys.stdout
                sys.stdout = f

                self.print_summary()
                self.print_detailed_analysis()

                # Restore stdout
                sys.stdout = original_stdout

            print(f"✅ Detailed report exported to: {output_file}")

        except Exception as e:
            print(f"Error exporting report: {str(e)}")


def main():
    """Main function to handle command line arguments and run the analyzer."""
    parser = argparse.ArgumentParser(
        description='Analyze user access patterns and identify standard vs. ad-hoc role assignments',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python access_review.py users.csv
  python access_review.py users.csv --threshold 80
  python access_review.py users.csv --output report.txt --actionable-csv iam_actions.csv
  python access_review.py users.csv -t 75 -o detailed_report.txt --actionable-csv tasks.csv
  python access_review.py users.csv --actionable-csv iam_workqueue.csv --csv-export summary.csv

CSV Format:
  Required columns: username, department, title, assigned_roles
  Example:
    username,department,title,assigned_roles
    john.doe,Collections,Collector,"Collector,Report Viewer"
    jane.smith,Finance,Analyst,"Budget Reader,Report Viewer"
        """
    )

    parser.add_argument('csv_file', help='Path to CSV file containing user access data')
    parser.add_argument('-t', '--threshold', type=int, default=70,
                        help='Percentage threshold for standard roles (default: 70)')
    parser.add_argument('-o', '--output', help='Export detailed report to text file')
    parser.add_argument('-c', '--csv-export', help='Export recommendations to CSV file')
    parser.add_argument('--actionable-csv', help='Export actionable CSV for IAM team implementation')
    parser.add_argument('--json', help='Export analysis results to JSON file')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Suppress console output (only show summary)')

    args = parser.parse_args()

    # Validate threshold
    if not 1 <= args.threshold <= 100:
        print("Error: Threshold must be between 1 and 100")
        sys.exit(1)

    # Initialize analyzer
    analyzer = AccessReviewAnalyzer(threshold=args.threshold)

    # Load and analyze data
    if not analyzer.load_csv(args.csv_file):
        sys.exit(1)

    analyzer.analyze_access()

    # Display results
    if not args.quiet:
        analyzer.print_summary()
        analyzer.print_detailed_analysis()
    else:
        analyzer.print_summary()

    # Export results
    if args.output:
        analyzer.export_text_report(args.output)

    if args.csv_export:
        analyzer.export_csv_recommendations(args.csv_export)

    if args.actionable_csv:
        analyzer.export_actionable_csv(args.actionable_csv)

    if args.json:
        try:
            with open(args.json, 'w', encoding='utf-8') as f:
                json.dump({
                    'summary': analyzer.get_summary_stats(),
                    'analysis': analyzer.analysis,
                    'threshold': args.threshold
                }, f, indent=2, ensure_ascii=False)
            print(f"✅ JSON analysis exported to: {args.json}")
        except Exception as e:
            print(f"Error exporting JSON: {str(e)}")

    # Summary message
    stats = analyzer.get_summary_stats()
    if stats['groups_with_adhoc'] > 0:
        print(f"\n⚠️  ATTENTION: {stats['groups_with_adhoc']} groups require review for ad-hoc role assignments")
    else:
        print(f"\n✅ ALL GROUPS COMPLIANT: No ad-hoc role assignments found")


if __name__ == "__main__":
    main()