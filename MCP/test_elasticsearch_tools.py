#!/usr/bin/env python3
"""
Elasticsearch MCP Tool Tester

This script tests the field-specific search tools by making requests to the MCP server.
It simulates how an LLM would query the system, including using wildcards and
different search patterns.
"""
import requests
import json
import time
from datetime import datetime
import sys
import argparse
from typing import Dict, List, Any, Optional, Union
from dotenv import load_dotenv
import os

# Prefer the repo root .env (one level up from MCP). Fall back to two levels if necessary.
repo_env_candidate = os.path.join(os.path.dirname(__file__), '..', '.env')
repo_env_candidate = os.path.abspath(repo_env_candidate)
if not os.path.exists(repo_env_candidate):
    # fallback (older layout in some forks)
    repo_env_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
load_dotenv(dotenv_path=repo_env_candidate, override=True)

# Read MCP_PORT from .env, require it and validate as integer
MCP_PORT = os.environ.get("MCP_PORT")
if not MCP_PORT:
    raise RuntimeError("MCP_PORT environment variable is required for MCP_SERVER_URL")
try:
    MCP_PORT_INT = int(MCP_PORT)
except ValueError:
    raise RuntimeError(f"Invalid MCP_PORT value: {MCP_PORT}")
DEFAULT_MCP_URL = f"http://localhost:{MCP_PORT_INT}"
print(f"[DEBUG] DEFAULT_MCP_URL = {DEFAULT_MCP_URL}", file=sys.stderr)
TIMEOUT = 30  # Request timeout in seconds

# Global variables for field names
DIAS_ENTREVISTA = "dias_para_atender_entrevistas"
HORARIOS_ENTREVISTA = "horarios_disponibles_para_entrevistar"

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def print_colored(text: str, color: str = Colors.BLUE, bold: bool = False):
    """Print colored text to terminal"""
    format_start = color + (Colors.BOLD if bold else "")
    format_end = Colors.END
    print(f"{format_start}{text}{format_end}")

def call_tool(mcp_url: str, tool_name: str, params: Dict[str, Any]) -> Dict:
    """Call an MCP tool endpoint and return the response"""
    url = f"{mcp_url}/mcp/tool/{tool_name}"
    try:
        print_colored(f"→ Calling tool: {tool_name} with params: {json.dumps(params)}", Colors.CYAN)
        response = requests.post(url, json=params, timeout=TIMEOUT)
        response.raise_for_status()
        try:
            # Try to parse as JSON
            result = response.json() if response.text.strip() else {}
            return result
        except json.JSONDecodeError:
            # If it's not JSON, return the raw text
            return {"raw_text": response.text[:500]}  # Limit to first 500 chars
    except requests.RequestException as e:
        print_colored(f"Request error: {str(e)}", Colors.RED, True)
        return {"error": str(e)}

def test_search_tool(mcp_url: str, tool_name: str, params: Dict[str, Any], description: str = "") -> bool:
    """Test a search tool and display the results"""
    print_colored(f"\n{'='*80}", Colors.HEADER)
    print_colored(f"TESTING: {tool_name}", Colors.HEADER, True)
    if description:
        print_colored(f"Description: {description}", Colors.BLUE)
    print_colored(f"{'='*80}", Colors.HEADER)
    
    start_time = time.time()
    try:
        result = call_tool(mcp_url, tool_name, params)
        elapsed = time.time() - start_time

        # Special handling for get_available_options tool
        if tool_name == "get_available_options":
            return test_get_available_options_result(result, elapsed)

        # Handle paginated responses with "results" key
        if isinstance(result, dict) and "results" in result and isinstance(result["results"], list):
            result_list = result["results"]
            # Show pagination info if available
            if "total" in result:
                print_colored(f"✅ Found {len(result_list)} results in {elapsed:.2f}s (Page: {result.get('offset', 0)//result.get('limit', 10) + 1}, Total: {result['total']})", Colors.GREEN, True)
                if result.get("has_more"):
                    print_colored(f"📄 Pagination: {result.get('instruction', 'More results available')}", Colors.YELLOW)
            else:
                print_colored(f"✅ Found {len(result_list)} results in {elapsed:.2f}s", Colors.GREEN, True)
        else:
            result_list = result

        if isinstance(result, dict) and "error" in result:
            print_colored(f"❌ ERROR: {result['error']}", Colors.RED, True)
            return False
        
        if isinstance(result, dict) and "raw_text" in result:
            print_colored(f"Raw response (first 500 chars):", Colors.YELLOW)
            print(result["raw_text"])
            return False  # Raw text indicates an error condition
        
        # Handle both list and dict responses
        if isinstance(result_list, list):
            if not isinstance(result, dict) or "total" not in result:
                print_colored(f"✅ Found {len(result_list)} results in {elapsed:.2f}s", Colors.GREEN, True)
            
            if result_list:
                # Print summary of first result
                first_result = result_list[0]
                print_colored("\nFirst result:", Colors.BLUE, True)
                
                # Print important fields if they exist
                important_fields = ["id_vacante", "Nombre_de_la_vacante", "Nombre_de_vacante", "Empresa", 
                                   "disponible", "Objetivo_del_puesto"]
                for field in important_fields:
                    if field in first_result:
                        print_colored(f"  {field}: {first_result[field]}", Colors.GREEN)
                
                # Check for interview scheduling information
                interview_fields = [DIAS_ENTREVISTA, 
                                   HORARIOS_ENTREVISTA,
                                   "Tiempo_maximo_de_contratacion"]
                
                found_interview_info = False
                for field in interview_fields:
                    if field in first_result and first_result[field]:
                        if not found_interview_info:
                            print_colored("\nInterview Scheduling Information:", Colors.BLUE, True)
                            found_interview_info = True
                        print_colored(f"  {field}: {first_result[field]}", Colors.CYAN)
                
                # For detail level requests, show more comprehensive information
                if params.get("detail_level") == "detail":
                    print_colored("\nAdditional Detail Fields:", Colors.BLUE, True)
                    detail_fields = ["Funciones_del_puesto", "Actividades_principales", "Departamento", 
                                   "Comunicacion_externa", "Jornada_Laboral", "Sueldo_Max", "Sueldo_Neto_Min",
                                   "Edad_minima", "Edad_maxima", "Estado_Civil", "Oficinas", "Area_de_trabajo",
                                   "Formacion"]
                    for field in detail_fields:
                        if field in first_result and first_result[field] and first_result[field] != "-":
                            print_colored(f"  {field}: {first_result[field]}", Colors.CYAN)
            
        elif isinstance(result, dict):
            print_colored(f"✅ Got result in {elapsed:.2f}s", Colors.GREEN, True)
            
            # Special handling for search_by_id_vacante - show ALL fields
            if tool_name == "search_by_id_vacante":
                print_colored(f"\nAll Fields Returned ({len(result)} total):", Colors.BLUE, True)
                for field in sorted(result.keys()):
                    print_colored(f"  {field}: {result[field]}", Colors.GREEN)
            else:
                # Print important fields if they exist
                important_fields = ["id_vacante", "Nombre_de_la_vacante", "Nombre_de_vacante", "Empresa", 
                                  "tipo_de_perfil", "Objetivo_del_puesto"]
                print_colored("\nResult Details:", Colors.BLUE, True)
                for field in important_fields:
                    if field in result:
                        print_colored(f"  {field}: {result[field]}", Colors.GREEN)
                
                # Check for interview scheduling information
                interview_fields = [DIAS_ENTREVISTA, 
                                   HORARIOS_ENTREVISTA,
                                   "Tiempo_maximo_de_contratacion"]
                
                found_interview_info = False
                for field in interview_fields:
                    if field in result and result[field]:
                        if not found_interview_info:
                            print_colored("\nInterview Scheduling Information:", Colors.BLUE, True)
                            found_interview_info = True
                        print_colored(f"  {field}: {result[field]}", Colors.CYAN)
            
            # For detail level requests, show more comprehensive information
            if params.get("detail_level") == "detail":
                print_colored("\nAdditional Detail Fields:", Colors.BLUE, True)
                detail_fields = ["Funciones_del_puesto", "Actividades_principales", "Departamento", 
                               "Comunicacion_externa", "Jornada_Laboral", "Sueldo_Max", "Sueldo_Neto_Min",
                               "Edad_minima", "Edad_maxima", "Estado_Civil", "Oficinas", "Area_de_trabajo",
                               "Formacion"]
                for field in detail_fields:
                    if field in result and result[field] and result[field] != "-":
                        print_colored(f"  {field}: {result[field]}", Colors.CYAN)
                        
                # Show total field count for detailed responses
                total_fields = len([k for k, v in result.items() if v and v != "-"])
                print_colored(f"\nTotal fields with data: {total_fields}", Colors.YELLOW)
        else:
            print_colored(f"❌ Unexpected result type: {type(result)}", Colors.RED, True)
            return False
        
        return True
        
    except Exception as e:
        print_colored(f"❌ Error testing {tool_name}: {str(e)}", Colors.RED, True)
        return False

def run_all_tests(mcp_url: str) -> None:
    """Run all test cases"""
    successful_tests = 0
    total_tests = 0
    
    print_colored("\n🔍 Starting Elasticsearch MCP Tool Tests", Colors.HEADER, True)
    
    # Test server status
    print_colored("\nChecking server status...", Colors.BLUE)
    try:
        response = requests.get(f"{mcp_url}/status", timeout=10)
        response.raise_for_status()
        status = response.json()
        if status.get("status") == "healthy":
            print_colored(f"✅ Server is healthy - ES version: {status.get('details', {}).get('es_version', 'unknown')}", Colors.GREEN, True)
            if "available_tools" in status.get("details", {}):
                print_colored("Available tools:", Colors.BLUE)
                for tool in status["details"]["available_tools"]:
                    print_colored(f"  - {tool}", Colors.CYAN)
        else:
            print_colored(f"⚠️ Server status: {status.get('status', 'unknown')}", Colors.YELLOW, True)
    except Exception as e:
        print_colored(f"❌ Error checking server status: {str(e)}", Colors.RED, True)
        print_colored("Tests may fail if server is not running correctly", Colors.YELLOW)
        return  # Exit early if server is not responding
    
    # Define test cases
    test_cases = [
        # NEW TESTS FOR get_available_options tool
        # {
        #     "tool": "get_available_options",
        #     "params": {},
        #     "description": "Test get_available_options with no parameters (should return all available options)"
        # },
        
        # Test search_available_vacancies with pagination (first page, limit 1)
        {
            "tool": "search_available_vacancies",
            "params": {"detail_level": "summary", "offset": 0, "limit": 1},
            "description": "Test pagination - first page with 1 result"
        },
        
        # # Test pagination on search_available_vacancies (try second page to see if it exists)
        # {
        #     "tool": "search_available_vacancies", 
        #     "params": {"detail_level": "summary", "offset": 1, "limit": 1},
        #     "description": "Test pagination - second page"
        # },
        
        # # Test with larger limit to get all available results
        # {
        #     "tool": "search_available_vacancies",
        #     "params": {"detail_level": "summary", "offset": 0, "limit": 10},
        #     "description": "Test larger limit for available vacancies"
        # },
        
        # # Test empty params (fallback behavior) - should be equivalent to above
        # {
        #     "tool": "search_available_vacancies",
        #     "params": {},
        #     "description": "Test fallback behavior with empty params"
        # },
        
        # Test search_by_id_vacante with known ID (Operador de camioneta)
        {
            "tool": "search_by_id_vacante",
            "params": {"id_vacante": "47"},
            "description": "Test search by ID - Operador de camioneta (id_vacante: 47)"
        },
        
        # # Test search_by_id_vacante with another known ID
        # {
        #     "tool": "search_by_id_vacante",
        #     "params": {"id_vacante": "11"},
        #     "description": "Test search by ID - another vacancy"
        # },
        
        # # Test get_interview_schedule
        # {
        #     "tool": "get_interview_schedule",
        #     "params": {"id_puesto": "36"},
        #     "description": "Test interview schedule retrieval"
        # },
        
        # # Test search by exact puesto name
        # {
        #     "tool": "search_by_puesto",
        #     "params": {"puesto": "Custodio 1°"},
        #     "description": "Test search by exact job title"
        # },
        
        # # Test search by partial puesto name (wildcard-like search)
        # {
        #     "tool": "search_by_puesto",
        #     "params": {"puesto": "*Custodio*"},
        #     "description": "Test search by partial job title"
        # },
        
        # # Test search by empresa
        # {
        #     "tool": "search_by_empresa",
        #     "params": {"empresa": "SNIPER"},
        #     "description": "Test search by company name"
        # },
        
        # # Test search by departamento
        # {
        #     "tool": "search_by_departamento",
        #     "params": {"departamento": "Sniper"},
        #     "description": "Test search by department"
        # },
        
        # # Test search by jornada (work schedule) - MISSING TEST ADDED
        # {
        #     "tool": "search_by_jornada",
        #     "params": {"jornada": "Horarios rotativos"},
        #     "description": "Test search by work schedule - rotating shifts"
        # },
        
        # # Test search by jornada with another schedule type
        # {
        #     "tool": "search_by_jornada",
        #     "params": {"jornada": "Lunes a viernes"},
        #     "description": "Test search by work schedule - Monday to Friday"
        # },
        
        # # Add debug test for jornada with exact case
        # {
        #     "tool": "search_by_jornada",
        #     "params": {"jornada": "Lunes a viernes", "detail_level": "detail"},
        #     "description": "DEBUG: Test search by work schedule - exact case Monday to Friday with detail"
        # },
        
        # # Test search by area_de_trabajo (renamed)
        # {
        #     "tool": "search_by_area_de_trabajo",
        #     "params": {"area": "campo"},
        #     "description": "Test search by work area - campo"
        # },
        
        # # Add a more specific test to debug the area search
        # {
        #     "tool": "search_by_area_de_trabajo", 
        #     "params": {"area": "oficina"},
        #     "description": "Test search by work area - oficina"
        # },

        # # Test search by profile type
        # {
        #     "tool": "search_by_tipo_de_perfil",
        #     "params": {"tipo": "Administrativo"},
        #     "description": "Test search by profile type - Administrativo"
        # },
        
        # # Test search by profile type
        # {
        #     "tool": "search_by_tipo_de_perfil",
        #     "params": {"tipo": "Dentista"},
        #     "description": "Test search by profile type - Dentista (should find nothing)"
        # },
        
        # # Test search by salary range
        # {
        #     "tool": "search_by_sueldo",
        #     "params": {"min_sueldo": "9000", "max_sueldo": "10000"},
        #     "description": "Test search by salary range"
        # },
        
        # # Test search by age range (young adults)
        # {
        #     "tool": "search_by_edad",
        #     "params": {"min_edad": "18", "max_edad": "30"},
        #     "description": "Test search by age range - young adults"
        # },
        
        # # Test search by age range (experienced workers)
        # {
        #     "tool": "search_by_edad",
        #     "params": {"min_edad": "30", "max_edad": "50"},
        #     "description": "Test search by age range - experienced workers"
        # },
        
        # # Test search by age range with pagination
        # {
        #     "tool": "search_by_edad",
        #     "params": {"min_edad": "20", "max_edad": "60", "detail_level": "detail", "offset": 0, "limit": 2},
        #     "description": "Test search by age range with pagination"
        # },

        # # Test search by location
        # {
        #     "tool": "search_by_ubicacion",
        #     "params": {"ubicacion": "Madd"},
        #     "description": "Test search by location"
        # },
        
        # # Test search by keyword (wildcard across multiple fields)
        # {
        #     "tool": "search_by_keyword",
        #     "params": {"keyword": "custodia"},
        #     "description": "Test search by keyword - custodia"
        # },
        
        # # Test search by education level (renamed)
        # {
        #     "tool": "search_by_educacion",
        #     "params": {"nivel": "secundaria"},
        #     "description": "Test search by education level"
        # },
        
        # # Test search by años de experiencia (renamed for clarity)
        # {
        #     "tool": "search_by_anios_de_experiencia",
        #     "params": {"anios": "1"},
        #     "description": "Test search by experience years - 1 year"
        # },
        # {
        #     "tool": "search_by_anios_de_experiencia",
        #     "params": {"anios": "5"},
        #     "description": "Test search by experience years - 5 years"
        # },
        
        # # Test search by skills (renamed)
        # {
        #     "tool": "search_by_habilidades",
        #     "params": {"skills": "comunicación"},
        #     "description": "Test search by skills"
        # },
        
        # # Test search_combined_criteria with multiple criteria
        # {
        #     "tool": "search_combined_criteria",
        #     "params": {
        #         "departamento": "Sniper",
        #         "empresa": "SNIPER", 
        #         "jornada": "Horarios rotativos",
        #         "area": "oficina",
        #         "ubicacion": "Madd",
        #         "min_experiencia": "1",
        #         "detail_level": "summary",
        #         "offset": 0,
        #         "limit": 10
        #     },
        #     "description": "Test search_combined_criteria with multiple criteria"
        # },
        
        # # Test search_combined_criteria with single criterion
        # {
        #     "tool": "search_combined_criteria",
        #     "params": {
        #         "departamento": "Sniper"
        #     },
        #     "description": "Test search_combined_criteria with single criterion"
        # },
        
        # # Test select_interview_date_by_number
        # {
        #     "tool": "select_interview_date_by_number",
        #     "params": {"id_puesto": "36", "date_number": 0},
        #     "description": "Test select_interview_date_by_number with valid date_number (0-indexed)"
        # },
        
        # # Test select_interview_date_by_number with invalid date_number
        # {
        #     "tool": "select_interview_date_by_number",
        #     "params": {"id_puesto": "36", "date_number": 99},
        #     "description": "Test select_interview_date_by_number with invalid date_number"
        # },
        
        # # Test select_interview_time_by_number
        # {
        #     "tool": "select_interview_time_by_number",
        #     "params": {"id_puesto": "36", "time_number": 0},
        #     "description": "Test select_interview_time_by_number with valid time_number (0-indexed)"
        # },
        
        # # Test select_interview_time_by_number with invalid time_number
        # {
        #     "tool": "select_interview_time_by_number",
        #     "params": {"id_puesto": "36", "time_number": 99},
        #     "description": "Test select_interview_time_by_number with invalid time_number"
        # },
        {
            "tool": "search_by_ad_id",
            "params": {"ad_id": "120228908704830333", "detail_level": "summary"},
            "description": "Test search by ad_id - Scientific Data Vacancy (ad_id: 120228908704830333)"
        }
    ]
    
    # Run the tests
    for test in test_cases:
        total_tests += 1
        success = test_search_tool(mcp_url, test["tool"], test["params"], test["description"])
        if success:
            successful_tests += 1
    
    # Print summary
    print_colored("\n" + "="*80, Colors.HEADER)
    print_colored("TEST SUMMARY", Colors.HEADER, True)
    print_colored("="*80, Colors.HEADER)
    print_colored(f"Total tests: {total_tests}", Colors.BLUE, True)
    print_colored(f"Successful: {successful_tests}", Colors.GREEN, True)
    failed = total_tests - successful_tests
    if failed > 0:
        print_colored(f"Failed: {failed}", Colors.RED, True)
    else:
        print_colored(f"Failed: {failed}", Colors.GREEN, True)
    
    success_rate = (successful_tests / total_tests) * 100 if total_tests > 0 else 0
    print_colored(f"Success rate: {success_rate:.1f}%", 
                  Colors.GREEN if success_rate > 80 else Colors.YELLOW if success_rate > 60 else Colors.RED,
                  True)

def test_get_available_options_result(result: Dict, elapsed: float) -> bool:
    """Special test handler for get_available_options tool"""
    
    if isinstance(result, dict) and "error" in result:
        print_colored(f"❌ ERROR: {result['error']}", Colors.RED, True)
        return False
    
    if not isinstance(result, dict):
        print_colored(f"❌ Expected dict response, got {type(result)}", Colors.RED, True)
        return False
    
    print_colored(f"✅ Got available options in {elapsed:.2f}s", Colors.GREEN, True)
    
    # Expected categories in the response
    expected_categories = [
        "departamentos", "empresas", "jornadas_laborales", 
        "areas_trabajo", "ubicaciones", "rangos_experiencia", "tipos_perfil"
    ]
    
    print_colored("\nAvailable Options Analysis:", Colors.BLUE, True)
    
    total_options = 0
    categories_with_data = 0
    
    for category in expected_categories:
        if category in result:
            options = result[category]
            if isinstance(options, list):
                option_count = len(options)
                total_options += option_count
                
                if option_count > 0:
                    categories_with_data += 1
                    print_colored(f"  ✅ {category}: {option_count} options", Colors.GREEN)
                    
                    # Show first few options for verification
                    if option_count <= 5:
                        for opt in options:
                            print_colored(f"    - {opt}", Colors.CYAN)
                    else:
                        for opt in options[:3]:
                            print_colored(f"    - {opt}", Colors.CYAN)
                        print_colored(f"    ... and {option_count - 3} more", Colors.CYAN)
                else:
                    print_colored(f"  ⚠️  {category}: No options available", Colors.YELLOW)
            else:
                print_colored(f"  ❌ {category}: Invalid format (expected list, got {type(options)})", Colors.RED)
        else:
            print_colored(f"  ❌ Missing category: {category}", Colors.RED)
    
    # Summary statistics
    print_colored(f"\nSummary:", Colors.BLUE, True)
    print_colored(f"  Total categories: {len(expected_categories)}", Colors.BLUE)
    print_colored(f"  Categories with data: {categories_with_data}", Colors.GREEN if categories_with_data > 0 else Colors.RED)
    print_colored(f"  Total options available: {total_options}", Colors.GREEN if total_options > 0 else Colors.RED)
    
    # Test evaluation criteria
    success_criteria = [
        categories_with_data >= 3,  # At least 3 categories should have data
        total_options >= 5,         # At least 5 total options across all categories
        "departamentos" in result,  # Critical categories must be present
        "empresas" in result,
        "jornadas_laborales" in result
    ]
    
    passed_criteria = sum(success_criteria)
    total_criteria = len(success_criteria)
    
    print_colored(f"\nTest Criteria: {passed_criteria}/{total_criteria} passed", 
                  Colors.GREEN if passed_criteria == total_criteria else Colors.YELLOW)
    
    # Final assessment
    if passed_criteria >= total_criteria * 0.8:  # 80% success rate
        print_colored(f"\n🎉 get_available_options test PASSED!", Colors.GREEN, True)
        return True
    else:
        print_colored(f"\n❌ get_available_options test FAILED!", Colors.RED, True)
        print_colored(f"Only {passed_criteria}/{total_criteria} criteria met", Colors.RED)
        return False

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Test Elasticsearch MCP Tools")
    parser.add_argument("--url", default=DEFAULT_MCP_URL,
                        help=f"URL of the MCP server (default: {DEFAULT_MCP_URL})")
    parser.add_argument("--test-options-only", action="store_true",
                        help="Run only the get_available_options tests")
    args = parser.parse_args()
    
    if args.test_options_only:
        run_options_tests_only(args.url)
    else:
        run_all_tests(args.url)

def run_options_tests_only(mcp_url: str) -> None:
    """Run only the get_available_options tests with multiple scenarios"""
    print_colored("\n🔍 Testing get_available_options Tool Only", Colors.HEADER, True)
    
    # Check server status first
    try:
        response = requests.get(f"{mcp_url}/status", timeout=10)
        response.raise_for_status()
        status = response.json()
        if status.get("status") == "healthy":
            print_colored(f"✅ Server is healthy", Colors.GREEN, True)
        else:
            print_colored(f"⚠️ Server status: {status.get('status', 'unknown')}", Colors.YELLOW, True)
    except Exception as e:
        print_colored(f"❌ Error checking server status: {str(e)}", Colors.RED, True)
        return
    
    # Multiple test scenarios for get_available_options
    option_test_cases = [
        {
            "name": "Basic Options Test",
            "params": {},
            "description": "Test basic functionality with no parameters"
        },
        {
            "name": "Empty Context Test", 
            "params": {},
            "description": "Test how tool handles potential empty data scenarios"
        }
    ]
    
    successful_tests = 0
    total_tests = len(option_test_cases)
    
    for i, test_case in enumerate(option_test_cases, 1):
        print_colored(f"\n" + "="*60, Colors.HEADER)
        print_colored(f"OPTIONS TEST {i}/{total_tests}: {test_case['name']}", Colors.HEADER, True)
        print_colored(f"Description: {test_case['description']}", Colors.BLUE)
        print_colored("="*60, Colors.HEADER)
        
        success = test_search_tool(mcp_url, "get_available_options", test_case["params"], test_case["description"])
        if success:
            successful_tests += 1
    
    # Print summary
    print_colored("\n" + "="*60, Colors.HEADER)
    print_colored("OPTIONS TEST SUMMARY", Colors.HEADER, True)
    print_colored("="*60, Colors.HEADER)
    print_colored(f"Total tests: {total_tests}", Colors.BLUE, True)
    print_colored(f"Successful: {successful_tests}", Colors.GREEN, True)
    failed = total_tests - successful_tests
    if failed > 0:
        print_colored(f"Failed: {failed}", Colors.RED, True)
    else:
        print_colored(f"Failed: {failed}", Colors.GREEN, True)
    
    success_rate = (successful_tests / total_tests) * 100 if total_tests > 0 else 0
    print_colored(f"Success rate: {success_rate:.1f}%", 
                  Colors.GREEN if success_rate > 80 else Colors.YELLOW if success_rate > 60 else Colors.RED,
                  True)

def run_all_tests(mcp_url: str) -> None:
    """Run all test cases"""
    successful_tests = 0
    total_tests = 0
    
    print_colored("\n🔍 Starting Elasticsearch MCP Tool Tests", Colors.HEADER, True)
    
    # Test server status
    print_colored("\nChecking server status...", Colors.BLUE)
    try:
        response = requests.get(f"{mcp_url}/status", timeout=10)
        response.raise_for_status()
        status = response.json()
        if status.get("status") == "healthy":
            print_colored(f"✅ Server is healthy - ES version: {status.get('details', {}).get('es_version', 'unknown')}", Colors.GREEN, True)
            if "available_tools" in status.get("details", {}):
                print_colored("Available tools:", Colors.BLUE)
                for tool in status["details"]["available_tools"]:
                    print_colored(f"  - {tool}", Colors.CYAN)
        else:
            print_colored(f"⚠️ Server status: {status.get('status', 'unknown')}", Colors.YELLOW, True)
    except Exception as e:
        print_colored(f"❌ Error checking server status: {str(e)}", Colors.RED, True)
        print_colored("Tests may fail if server is not running correctly", Colors.YELLOW)
        return  # Exit early if server is not responding
    
    # Define test cases
    test_cases = [
        # Test search_available_vacancies with pagination
        {
            "tool": "search_available_vacancies",
            "params": {"detail_level": "summary", "offset": 0, "limit": 1},
            "description": "Test pagination - first page with 1 result"
        },
        
        # Test search_by_id_vacante with known ID
        {
            "tool": "search_by_id_vacante",
            "params": {"id_vacante": "47"},
            "description": "Test search by ID - Operador de camioneta (id_vacante: 47)"
        },

        {
            "tool": "search_by_ad_id",
            "params": {"ad_id": "120228908704830333", "detail_level": "summary"},
            "description": "Test search by ad_id -  Operador de Camioneta (ad_id: 120228908704830333)"
        }
        
    ]
    
    # Run the tests
    for test in test_cases:
        total_tests += 1
        success = test_search_tool(mcp_url, test["tool"], test["params"], test["description"])
        if success:
            successful_tests += 1
    
    # Print summary
    print_colored("\n" + "="*80, Colors.HEADER)
    print_colored("TEST SUMMARY", Colors.HEADER, True)
    print_colored("="*80, Colors.HEADER)
    print_colored(f"Total tests: {total_tests}", Colors.BLUE, True)
    print_colored(f"Successful: {successful_tests}", Colors.GREEN, True)
    failed = total_tests - successful_tests
    if failed > 0:
        print_colored(f"Failed: {failed}", Colors.RED, True)
    else:
        print_colored(f"Failed: {failed}", Colors.GREEN, True)
    
    success_rate = (successful_tests / total_tests) * 100 if total_tests > 0 else 0
    print_colored(f"Success rate: {success_rate:.1f}%", 
                  Colors.GREEN if success_rate > 80 else Colors.YELLOW if success_rate > 60 else Colors.RED,
                  True)

def run_options_tests_only(mcp_url: str) -> None:
    """Run only the get_available_options tests with multiple scenarios"""
    print_colored("\n🔍 Testing get_available_options Tool Only", Colors.HEADER, True)
    
    # Check server status first
    try:
        response = requests.get(f"{mcp_url}/status", timeout=10)
        response.raise_for_status()
        status = response.json()
        if status.get("status") == "healthy":
            print_colored(f"✅ Server is healthy", Colors.GREEN, True)
        else:
            print_colored(f"⚠️ Server status: {status.get('status', 'unknown')}", Colors.YELLOW, True)
    except Exception as e:
        print_colored(f"❌ Error checking server status: {str(e)}", Colors.RED, True)
        return
    
    # Multiple test scenarios for get_available_options
    option_test_cases = [
        {
            "name": "Basic Options Test",
            "params": {},
            "description": "Test basic functionality with no parameters"
        },
        {
            "name": "Empty Context Test", 
            "params": {},
            "description": "Test how tool handles potential empty data scenarios"
        }
    ]
    
    successful_tests = 0
    total_tests = len(option_test_cases)
    
    for i, test_case in enumerate(option_test_cases, 1):
        print_colored(f"\n" + "="*60, Colors.HEADER)
        print_colored(f"OPTIONS TEST {i}/{total_tests}: {test_case['name']}", Colors.HEADER, True)
        print_colored(f"Description: {test_case['description']}", Colors.BLUE)
        print_colored("="*60, Colors.HEADER)
        
        success = test_search_tool(mcp_url, "get_available_options", test_case["params"], test_case["description"])
        if success:
            successful_tests += 1
    
    # Print summary
    print_colored("\n" + "="*60, Colors.HEADER)
    print_colored("OPTIONS TEST SUMMARY", Colors.HEADER, True)
    print_colored("="*60, Colors.HEADER)
    print_colored(f"Total tests: {total_tests}", Colors.BLUE, True)
    print_colored(f"Successful: {successful_tests}", Colors.GREEN, True)
    failed = total_tests - successful_tests
    if failed > 0:
        print_colored(f"Failed: {failed}", Colors.RED, True)
    else:
        print_colored(f"Failed: {failed}", Colors.GREEN, True)
    
    success_rate = (successful_tests / total_tests) * 100 if total_tests > 0 else 0
    print_colored(f"Success rate: {success_rate:.1f}%", 
                  Colors.GREEN if success_rate > 80 else Colors.YELLOW if success_rate > 60 else Colors.RED,
                  True)

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Test Elasticsearch MCP Tools")
    parser.add_argument("--url", default=DEFAULT_MCP_URL,
                        help=f"URL of the MCP server (default: {DEFAULT_MCP_URL})")
    parser.add_argument("--test-options-only", action="store_true",
                        help="Run only the get_available_options tests")
    args = parser.parse_args()
    
    if args.test_options_only:
        run_options_tests_only(args.url)
    else:
        run_all_tests(args.url)

if __name__ == "__main__":
    main()
