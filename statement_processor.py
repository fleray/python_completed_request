import json
import logging
from typing import List, Set
import os
import re
import argparse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.formatting.rule import ColorScaleRule

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def create_template(query):
    """Create a template by replacing values in the query with placeholders."""
    template = query
    scalar_value_counter = 1
    array_value_counter = 1
    new_template = ""
    last_end = 0
    
    # Match field and operator pattern
    # This pattern matches:
    # field = value
    # field == value
    # field > value
    # field < value
    # field >= value
    # field <= value
    # field IN (value1, value2, ...)
    # field IN [value1, value2, ...]
    # field IN [ 'val1', 'val2' ]
    # field IN ['val1','val2']
    
    # Simple value pattern: 'value' or "value" or value
    # For quoted values, can contain spaces: 'my value' or "my value"
    # For unquoted values, no spaces allowed: myvalue
    simple_value = r'(?:[\'"][^\'"]*[\'"]|[^\'",\s]+)'
    # Array pattern: [value1, value2, ...] with optional spaces
    array_value = r'\[(?:[^\]]*)\]'
    # List pattern: (value1, value2, ...)
    list_value = r'\([^)]+\)'
    
    operator_pattern = f'([a-zA-Z0-9_.]+)\\s*(=|==|>|<|>=|<=| in )\\s*({simple_value}|{array_value}|{list_value})'
    
    # Find all matches
    matches = list(re.finditer(operator_pattern, query, re.IGNORECASE))
    
    # Process matches in order
    for match in matches:
        field = match.group(1)
        operator = match.group(2)
        value = match.group(3).strip()
        
        # Add the text before the match
        new_template += query[last_end:match.start()]
        
        if value.startswith("$"): # already "named" or "positional" parametrized value
            new_template += f"{field} {operator} {value}"
            # Update the last end position
            last_end = match.end()
            continue
        
        # Handle IN operator specially
        if operator.lower() == ' in ':
            orignal_value_str_len = len(str(value))
            # For IN operator, we need to find the complete array or list
            if value.startswith('['):
                # Find the complete array including all nested content
                array_match = re.search(array_value, query[match.start():])
                if array_match:
                    value = array_match.group(0)
            elif value.startswith('('):
                # Find the complete list including all nested content
                list_match = re.search(list_value, query[match.start():])
                if list_match:
                    value = list_match.group(0)
            
            # Add the field, operator and placeholder
            new_template += f"{field} IN [?, ?, ...]"
            array_value_counter += 1
            
            # Update the last end position
            last_end = match.end()
            last_end = last_end + len(str(value)) - orignal_value_str_len
        else:
            # Remove quotes if present
            if value.startswith(("'", '"')) and value.endswith(("'", '"')):
                value = value[1:-1]
            
            # Add the field, operator and placeholder
            new_template += f"{field} {operator} ?"
            scalar_value_counter += 1
        
            # Update the last end position
            last_end = match.end()
    
    # Add any remaining text after the last match
    new_template += query[last_end:]
    
    return new_template

def process_positional_args(statement: str, positional_args: List) -> str:
    """
    Process the SQL statement by replacing numbered placeholders ($1, $2, etc.) with values from positional_args.
    """
    def replace_arg(match):
        try:
            index = int(match.group(1)) - 1  # Convert to 0-based index
            if 0 <= index < len(positional_args):
                value = positional_args[index]
                # Wrap string values with single quotes
                if isinstance(value, str):
                    return f"'{value}'"
                return str(value)
            else:
                logging.warning(f"Positional argument index {index + 1} out of range")
                return match.group(0)
        except ValueError:
            logging.error(f"Invalid positional argument format: {match.group(0)}")
            return match.group(0)
    
    # Replace all occurrences of $n with corresponding positional arguments
    pattern = r'\$(\d+)'
    return re.sub(pattern, replace_arg, statement)

def process_named_args(statement: str, named_args: dict) -> str:
    """
    Process the SQL statement by replacing named placeholders ($keyword) with values from named_args.
    Example: 
    - statement: "SELECT * FROM users WHERE name = $name AND age > $age"
    - named_args: {"$name": "John", "$age": 18}
    - result: "SELECT * FROM users WHERE name = 'John' AND age > 18"
    """
    def replace_arg(match):
        try:
            placeholder = match.group(0)  # Get the full match including $ (e.g., "$name")
            if placeholder in named_args:
                value = named_args[placeholder]
                # Wrap string values with single quotes
                if isinstance(value, str):
                    return f"'{value}'"
                return str(value)
            else:
                logging.warning(f"Named argument '{placeholder}' not found in provided arguments")
                return placeholder
        except Exception as e:
            logging.error(f"Error processing named argument: {str(e)}")
            return match.group(0)
    
    # Replace all occurrences of $keyword with corresponding named arguments
    pattern = r'\$\w+'
    return re.sub(pattern, replace_arg, statement)

def process_json_file(file_path: str, use_value_for_parameters: bool) -> List[dict]:
    """
    Read and process the JSON file containing SQL statements and their metadata.
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            
        processed_items = []
        
        # Check if data is a list
        if not isinstance(data, list):
            logging.error("Input JSON must be a list of objects")
            return []
            
        for completed_request in data:
            
            # Check if required fields are present
            if 'statement' not in completed_request:
                logging.warning(f"Skipping item missing required statement field: {completed_request}")
                continue
                
            # Process the statement and arguments (positional or named)
            statement = completed_request['statement']
            processed_statement = statement.replace('\n', ' ').replace('<ud>', '').replace('</ud>', '')

            if(use_value_for_parameters):
                positional_args = completed_request.get('positionalArgs', [])
                if(len(positional_args) > 0):
                    processed_statement = process_positional_args(
                        processed_statement, positional_args)
                    
                named_args = completed_request.get('namedArgs', [])
                if(len(named_args) > 0):
                    processed_statement = process_named_args(
                        processed_statement, named_args)
            
            # Create a new item with the processed statement
            processed_item = completed_request.copy()
            processed_item['statement'] = processed_statement

            processed_items.append(processed_item)
            
        return processed_items
        
    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
        return []
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON format in file: {file_path}")
        return []
    except Exception as e:
        logging.error(f"Error processing file: {str(e)}")
        return []

def convert_to_excel_value(value):
    """
    Convert a value to a format that can be written to Excel.
    """
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    if isinstance(value, str):
        value = value.replace('µs', 'us')
    return value

def convert_to_seconds(time_str):
    """Convert time string to seconds."""
    if not time_str:
        return 0
    try:
        if isinstance(time_str, (int, float)):
            return float(time_str)
        if 'us' in time_str:
            return float(time_str.replace('us', '')) / 1000000
        if 'µs' in time_str:
            return float(time_str.replace('µs', '')) / 1000000
        if 'ms' in time_str:
            return float(time_str.replace('ms', '')) / 1000
        if 's' in time_str:
            return float(time_str.replace('s', ''))
        if 'm' in time_str:
            return float(time_str.replace('m', '')) * 60
        if 'h' in time_str:
            return float(time_str.replace('h', '')) * 3600
        return float(time_str)
    except (ValueError, TypeError):
        return 0


def convert_to_micro_seconds(time_str):
    """Convert time string to micro seconds."""
    if not time_str:
        return 0
    try:
        if isinstance(time_str, (int, float)):
            return float(time_str)
        if 'us' in time_str:
            return float(time_str.replace('us', ''))
        if 'µs' in time_str:
            return float(time_str.replace('µs', ''))
        if 'ms' in time_str:
            return float(time_str.replace('ms', '')) * 1000
        if 's' in time_str:
            return float(time_str.replace('s', '')) * 100000
        return float(time_str)
    except (ValueError, TypeError):
        return 0



def create_excel_sheets(wb: Workbook, processed_items: List[dict], sheet_title: str) -> None:
    """
    Create and populate Excel sheets with processed data.
    
    Args:
        wb: Workbook object
        processed_items: List of processed items
        sheet_title: Title prefix for the sheets (e.g., "Raw" or "Aggregated")
    """
    # Define headers in the specified order
    headers = [
        'requestTime', 'statement', 'elapsedTime', 'cpuTime', 'resultCount',
        'resultSize', 'phaseCounts', 'phaseOperators', 'phaseTimes',
        'queryContext', 'remoteAddr', 'requestId', 'errorCount', 'errors',
        'namedArgs', 'n1qlFeatCtrl', 'clientContextID', 'scanConsistency',
        'serviceTime', 'state', 'statementType', 'useCBO', 'usedMemory',
        'userAgent', 'users', '~qualifier'
    ]
    
    # Style for headers
    header_font = Font(bold=True)
    header_fill = PatternFill(start_color='ADD8E6', end_color='ADD8E6', fill_type='solid')
    
    # Create and setup the first sheet (Raw Results)
    ws_raw = wb.active if sheet_title == "Raw" else wb.create_sheet(title=f"{sheet_title} Queries")
    
    # Write headers with styling
    for col_idx, header in enumerate(headers, 1):
        cell = ws_raw.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
    
    # Write data rows
    for row_idx, item in enumerate(processed_items, 2):
        for col_idx, header in enumerate(headers, 1):
            value = convert_to_excel_value(item.get(header, ''))
            ws_raw.cell(row=row_idx, column=col_idx, value=value)
    
    # Create and setup the second sheet (Aggregated Results)
    ws_agg = wb.create_sheet(title=f"{sheet_title} Queries (Aggregated)")
    
    # Define headers for aggregated sheet
    agg_headers = [
        'requestTime', 'statement', 'AVG elapsedTime (s)', 'TOTAL elapsedTime (s)', 'AVG cpuTime (µs)', 'AVG resultCount',
        'AVG resultSize (bytes)', 'AVG serviceTime (s)', 'TOTAL count'
    ]
    
    # Write headers with styling
    for col_idx, header in enumerate(agg_headers, 1):
        cell = ws_agg.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
    
    # Group by statement and calculate averages
    statement_groups = {}
    for item in processed_items:
        statement = item['statement']
        if statement not in statement_groups:
            statement_groups[statement] = {
                'requestTime': item['requestTime'],
                'statement': statement,
                'elapsedTime': [],
                'cpuTime': [],
                'resultCount': [],
                'resultSize': [],
                'serviceTime': [],
                'count': 0
            }
        
        # Add values to the group
        statement_groups[statement]['elapsedTime'].append(convert_to_seconds(item.get('elapsedTime', 0)))
        statement_groups[statement]['cpuTime'].append(convert_to_micro_seconds(item.get('cpuTime', 0)))
        statement_groups[statement]['resultCount'].append(float(item.get('resultCount', 0)))
        statement_groups[statement]['resultSize'].append(float(item.get('resultSize', 0)))
        statement_groups[statement]['serviceTime'].append(convert_to_seconds(item.get('serviceTime', 0)))
        statement_groups[statement]['count'] += 1
    
    # Sort statement_groups by total elapsedTime in descending order
    sorted_groups = sorted(
        statement_groups.items(),
        key=lambda x: sum(x[1]['elapsedTime']),
        reverse=True
    )
    
    # Write aggregated data
    for row_idx, (_, group) in enumerate(sorted_groups, 2):
        ws_agg.cell(row=row_idx, column=1, value=group['requestTime'])
        ws_agg.cell(row=row_idx, column=2, value=group['statement'])
        ws_agg.cell(row=row_idx, column=3, value=sum(group['elapsedTime']) / len(group['elapsedTime']))
        ws_agg.cell(row=row_idx, column=4, value=sum(group['elapsedTime']))
        ws_agg.cell(row=row_idx, column=5, value=sum(group['cpuTime']) / len(group['cpuTime']))
        ws_agg.cell(row=row_idx, column=6, value=sum(group['resultCount']) / len(group['resultCount']))
        ws_agg.cell(row=row_idx, column=7, value=sum(group['resultSize']) / len(group['resultSize']))
        ws_agg.cell(row=row_idx, column=8, value=sum(group['serviceTime']) / len(group['serviceTime']))
        ws_agg.cell(row=row_idx, column=9, value=group['count'])

    # Add color gradient to TOTAL elapsedTime column
    color_scale_rule = ColorScaleRule(
        start_type='min', start_color='FFFF00',
        mid_type='percentile', mid_value=50, mid_color='FFA500',
        end_type='max', end_color='FF0000'
    )
    ws_agg.conditional_formatting.add(
        f'D2:D{ws_agg.max_row}',
        color_scale_rule
    )
    
    # Create and setup the third sheet (Normalized Queries Aggregated)
    if sheet_title == "Param.":
        ws_normalized = wb.create_sheet(title=f"Normalized Queries (Aggregated)")
        
        # Write headers with styling
        for col_idx, header in enumerate(agg_headers, 1):
            cell = ws_normalized.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')
        
        # Group by template and calculate averages
        template_groups = {}
        for item in processed_items:
            statement = item['statement']
            template = create_template(statement)
            
            if template not in template_groups:
                template_groups[template] = {
                    'requestTime': item['requestTime'],
                    'statement': template,
                    'elapsedTime': [],
                    'cpuTime': [],
                    'resultCount': [],
                    'resultSize': [],
                    'serviceTime': [],
                    'count': 0
                }
            
            # Add values to the group
            template_groups[template]['elapsedTime'].append(convert_to_seconds(item.get('elapsedTime', 0)))
            template_groups[template]['cpuTime'].append(convert_to_seconds(item.get('cpuTime', 0)))
            template_groups[template]['resultCount'].append(float(item.get('resultCount', 0)))
            template_groups[template]['resultSize'].append(float(item.get('resultSize', 0)))
            template_groups[template]['serviceTime'].append(convert_to_seconds(item.get('serviceTime', 0)))
            template_groups[template]['count'] += 1
        
        # Sort template_groups by total elapsedTime in descending order
        sorted_templates = sorted(
            template_groups.items(),
            key=lambda x: sum(x[1]['elapsedTime']),
            reverse=True
        )
        
        # Write aggregated data
        for row_idx, (_, group) in enumerate(sorted_templates, 2):
            ws_normalized.cell(row=row_idx, column=1, value=group['requestTime'])
            ws_normalized.cell(row=row_idx, column=2, value=group['statement'])
            ws_normalized.cell(row=row_idx, column=3, value=sum(group['elapsedTime']) / len(group['elapsedTime']))
            ws_normalized.cell(row=row_idx, column=4, value=sum(group['elapsedTime']))
            ws_normalized.cell(row=row_idx, column=5, value=sum(group['cpuTime']) / len(group['cpuTime']))
            ws_normalized.cell(row=row_idx, column=6, value=sum(group['resultCount']) / len(group['resultCount']))
            ws_normalized.cell(row=row_idx, column=7, value=sum(group['resultSize']) / len(group['resultSize']))
            ws_normalized.cell(row=row_idx, column=8, value=sum(group['serviceTime']) / len(group['serviceTime']))
            ws_normalized.cell(row=row_idx, column=9, value=group['count'])
        
        # Add color gradient to TOTAL elapsedTime column
        ws_normalized.conditional_formatting.add(
            f'D2:D{ws_normalized.max_row}',
            color_scale_rule
        )
    
    # Adjust column widths for all sheets
    for ws in [ws_raw, ws_agg, ws_normalized if sheet_title == "Param." else None]:
        if ws:
            for col_idx, header in enumerate(ws[1], 1):
                max_length = len(str(header.value))
                for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_idx, max_col=col_idx):
                    if row[0].value:
                        max_length = max(max_length, len(str(row[0].value)))
                ws.column_dimensions[chr(64 + col_idx)].width = min(max_length + 2, 100)

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Process computed request statements from a JSON file and generate Excel report to help identify better slow queries.')
    parser.add_argument('input_file', help='Path to the input JSON file (output from computed request)')
    args = parser.parse_args()
    
    # Process the JSON file
    processed_items = process_json_file(args.input_file, False)
    
    if not processed_items:
        logging.error("No items to process")
        return
        
    # Create output filename
    input_filename = os.path.splitext(os.path.basename(args.input_file))[0]
    output_file = f"output_{input_filename}.xlsx"
    
    # Create a new workbook and remove the default sheet
    wb = Workbook()
    wb.remove(wb.active)  # Remove the default empty sheet
    
    # Create sheets for parametrized results
    create_excel_sheets(wb, processed_items, "Param.")
    
    # Process the JSON file with parameter replacement
    processed_items = process_json_file(args.input_file, True)
    
    # Create sheets for valued results
    create_excel_sheets(wb, processed_items, "Valued")
    
    # Save the workbook
    wb.save(output_file)
    logging.info(f"Results written to {output_file}")

if __name__ == "__main__":
    main() 