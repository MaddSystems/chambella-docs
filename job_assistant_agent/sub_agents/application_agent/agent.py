from datetime import datetime, timedelta
import json
import calendar
import logging
import requests
import os

from google.adk.agents import Agent
from google.adk.tools.tool_context import ToolContext
from google.adk.tools import transfer_to_agent, mcp_tool
# Import centralized config
from config import APPLICATION_AGENT_MODEL

logger = logging.getLogger(__name__)

# MCP Configuration Constants
MCP_PORT = os.getenv("MCP_PORT")
if not MCP_PORT:
    raise RuntimeError("MCP_PORT environment variable is required for MCP_SERVER_URL")
try:
    MCP_PORT_INT = int(MCP_PORT)
except ValueError:
    raise RuntimeError(f"Invalid MCP_PORT value: {MCP_PORT}")
MCP_SERVER_URL = f"http://localhost:{MCP_PORT_INT}"  # Dynamic URL from env
MCP_CONNECTION_TIMEOUT = 30  # Timeout in seconds

# ADDED: EGO API Configuration from environment variables
EGO_API_URL = os.getenv("EGO_API_URL")
EGO_API_BEARER_TOKEN = os.getenv("EGO_API_BEARER_TOKEN")
EGO_API_CATALOG_ID = os.getenv("EGO_API_CATALOG_ID")

# Global variables for field names
DIAS_ENTREVISTA = "dias_para_atender_entrevistas"
HORARIOS_ENTREVISTA = "horarios_disponibles_para_entrevistar"

def is_mexican_holiday(date_obj: datetime) -> bool:
    """
    Check if a given date is a Mexican federal holiday.
    
    Args:
        date_obj: datetime object to check
        
    Returns:
        bool: True if it's a holiday, False otherwise
    """
    month = date_obj.month
    day = date_obj.day
    year = date_obj.year
    weekday = date_obj.weekday()  # Monday is 0, Sunday is 6
    
    # I. El 1o. de enero
    if month == 1 and day == 1:
        return True
    
    # II. El primer lunes de febrero en conmemoración del 5 de febrero
    if month == 2 and weekday == 0:  # Monday
        # Find the first Monday of February
        first_day = datetime(year, 2, 1)
        first_monday = first_day + timedelta(days=(7 - first_day.weekday()) % 7)
        if date_obj.date() == first_monday.date():
            return True
    
    # III. El tercer lunes de marzo en conmemoración del 21 de marzo
    if month == 3 and weekday == 0:  # Monday
        # Find the third Monday of March
        first_day = datetime(year, 3, 1)
        first_monday = first_day + timedelta(days=(7 - first_day.weekday()) % 7)
        third_monday = first_monday + timedelta(days=14)  # Add 2 weeks
        if date_obj.date() == third_monday.date():
            return True
    
    # IV. El 1o. de mayo
    if month == 5 and day == 1:
        return True
    
    # V. El 16 de septiembre
    if month == 9 and day == 16:
        return True
    
    # VI. El tercer lunes de noviembre en conmemoración del 20 de noviembre
    if month == 11 and weekday == 0:  # Monday
        # Find the third Monday of November
        first_day = datetime(year, 11, 1)
        first_monday = first_day + timedelta(days=(7 - first_day.weekday()) % 7)
        third_monday = first_monday + timedelta(days=14)  # Add 2 weeks
        if date_obj.date() == third_monday.date():
            return True
    
    # VII. El 1o. de octubre de cada seis años (años de cambio presidencial)
    # Los años de cambio presidencial en México son: 2024, 2030, 2036, etc.
    presidential_years = [2024, 2030, 2036, 2042, 2048, 2054, 2060]
    if month == 10 and day == 1 and year in presidential_years:
        return True
    
    # VIII. El 25 de diciembre
    if month == 12 and day == 25:
        return True
    
    return False

def get_job_details_by_id(job_id: str, tool_context: ToolContext = None) -> dict:
    """Get detailed information about a specific job by ID using MCP server."""
    # logger.debug(f"get_job_details_by_id called with ID: {job_id}")
    logger.error(f"[CRITICAL DEBUG] get_job_details_by_id called with ID: {job_id}")
    try:
        job_id_int = int(job_id)
    except ValueError:
        logger.error(f"Invalid job_id format: {job_id}. Must be an integer.")
        return {"status": "error", "message": "El ID de la vacante no es válido (debe ser un número)."}

    try:
        # Use the search_by_id_vacante tool (no detail_level parameter needed)
        response = requests.post(
            f"{MCP_SERVER_URL}/mcp/tool/search_by_id_vacante",
            json={"id_vacante": str(job_id_int)},
            timeout=float(MCP_CONNECTION_TIMEOUT)
        )
        response.raise_for_status()
        
        result_data = response.json()
        
        # Handle error response
        if isinstance(result_data, dict) and "error" in result_data:
            logger.error(f"MCP server returned error: {result_data['error']}")
            return {"status": "error", "message": f"Error al obtener detalles de la vacante: {result_data['error']}"}

        # The MCP server returns the text fields directly - check for the actual field names
        if isinstance(result_data, dict) and len(result_data) > 0 and not "error" in result_data:
            # Verify that this is the right job by checking id_vacante or other key fields
            returned_id = result_data.get("id_vacante")  # This is the actual field name returned
            if returned_id and str(returned_id) == str(job_id_int):
                logger.info(f"Successfully fetched details for job ID {job_id} - ID match confirmed")
            elif returned_id:
                logger.warning(f"ID mismatch: requested {job_id_int}, got {returned_id}")
            else:
                logger.info(f"Successfully fetched details for job ID {job_id} - no id_vacante field to verify")
            
            return {"status": "success", "job_details": result_data}
        else:
            logger.warning(f"No job details found for ID {job_id}. Result: {result_data}")
            return {"status": "error", "message": f"No se encontraron detalles para la vacante con ID {job_id}."}
        
    except requests.exceptions.RequestException as e:
        logger.error(f"RequestException for ID {job_id}: {e}", exc_info=True)
        return {"status": "error", "message": f"Error de conexión al obtener detalles de la vacante: {e}"}
    except json.JSONDecodeError as e:
        logger.error(f"JSONDecodeError for ID {job_id}: {e}", exc_info=True)
        return {"status": "error", "message": f"Error decodificando los detalles de la vacante: {e}"}
    except Exception as e:
        logger.error(f"Generic error for ID {job_id}: {e}", exc_info=True)
        return {"status": "error", "message": f"Error inesperado al obtener detalles de la vacante: {e}"}


def get_current_time() -> dict:
    """Get the current time in the format YYYY-MM-DD HH:MM:SS"""
    return {
        "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_available_interview_slots(tool_context: ToolContext) -> dict:
    """
    Gets available interview dates for the current job of interest.
    It calls the MCP 'get_interview_schedule' tool, processes the available days,
    generates specific calendar dates for the near future, and stores them for selection.
    """
    current_job_interest = tool_context.state.get("current_job_interest")
    current_job_id = tool_context.state.get("current_job_id")
    job_id = None
    if current_job_interest and current_job_interest.get("id"):
        job_id = current_job_interest["id"]
    elif current_job_id:
        job_id = current_job_id
    else:
        return {
            "status": "error",
            "message": "No se ha seleccionado una vacante para postularse. Por favor, primero busca una vacante."
        }
    logger.error(f"[CRITICAL DEBUG] get available interview slots called with job ID: {job_id}")
    tool_context.state["current_job_id"] = job_id # Ensure current_job_id is set
    
    # Log actual job ID being used (para depuración)
    logger.info(f"Getting interview slots for job ID: {job_id}")

    # Clear existing interview data to avoid conflicts
    tool_context.state["current_day_interview"] = ""
    tool_context.state["current_time_interview"] = ""

    try:
        # Get job details to access interview scheduling info
        job_details_result = get_job_details_by_id(str(job_id), tool_context)
        
        if job_details_result.get("status") != "success" or not job_details_result.get("job_details"):
            return {
                "status": "error",
                "message": f"Error al obtener información de la vacante: {job_details_result.get('message', 'Error desconocido')}"
            }
            
        job_data = job_details_result["job_details"]
        
        # Get interview days and times from job details - use actual field names from MCP response
        dias_entrevista_str = job_data.get("dias_para_atender_entrevistas", "")
        horarios_disponibles_str = job_data.get("horarios_disponibles_para_entrevistar", "")
        tipo_de_perfil = job_data.get("tipo_de_perfil", "No especificado")
        perfil_de_puesto = job_data.get("perfil_de_puesto", "No especificado")
        departamento = job_data.get("departamento", "No especificado")
        corporative_id = job_data.get("corporative_id", "No especificado")
        business_id = job_data.get("business_id", "No especificado")
        client_id = job_data.get("client_id", "No especificado")

        logger.info("Dias para entrevistas: %s", dias_entrevista_str)
        logger.error(f"[CRITICAL DEBUG] Dias para entrevistas: {dias_entrevista_str}")
        logger.info("Horarios disponibles para entrevistas: %s", horarios_disponibles_str)
        logger.error(f"[CRITICAL DEBUG] Horarios disponibles: {horarios_disponibles_str}")
        logger.error(f"[CRITICAL DEBUG] perfil_de_puesto: {perfil_de_puesto}")
        logger.error(f"[CRITICAL DEBUG] tipo_de_perfil: {tipo_de_perfil}")
        logger.error(f"[CRITICAL DEBUG] departamento: {departamento}")
        logger.error(f"[CRITICAL DEBUG] corporate_id: {corporative_id}")
        logger.error(f"[CRITICAL DEBUG] business_id: {business_id}")
        logger.error(f"[CRITICAL DEBUG] client_id: {client_id}")

        if not dias_entrevista_str:
            return {
                "status": "error",
                "message": "No se encontró información de días disponibles para entrevistas en esta vacante."
            }
            
        # Store job title for use in responses - use actual field names from MCP response
        job_title = job_data.get("nombre_de_la_vacante", f"Vacante ID {job_id}")
        tool_context.state["current_job_title"] = job_title

        # Handle both old and new response formats
        interview_slots = None
        
        # First, check if we have the new format with 'interview_slots' directly
        if "interview_slots" in job_data:
            interview_slots = job_data.get("interview_slots", [])
        
        # If we don't have interview_slots yet, calculate them using the old method
        if not interview_slots:
            dias_map_to_int = {'lunes': 0, 'martes': 1, 'miércoles': 2, 'jueves': 3, 'viernes': 4, 'sábado': 5, 'domingo': 6}
            allowed_weekdays_num = []

            # Handle both string and list for dias_entrevista_str
            dias_iterable = []
            if isinstance(dias_entrevista_str, str):
                dias_iterable = dias_entrevista_str.split(',')
            elif isinstance(dias_entrevista_str, list):
                dias_iterable = dias_entrevista_str

            for dia_str in dias_iterable:
                dia_str_clean = dia_str.strip().lower()
                if dia_str_clean in dias_map_to_int:
                    allowed_weekdays_num.append(dias_map_to_int[dia_str_clean])

            if not allowed_weekdays_num:
                return {"status": "error", "message": "No se pudieron determinar los días de entrevista válidos."}

            processed_dates = []
            today = datetime.now()
            # Check for the next 14 days, starting from tomorrow
            for i in range(1, 15):
                current_eval_date = today + timedelta(days=i)
                # Check if the day is in the allowed weekdays AND not a Mexican holiday
                if (current_eval_date.weekday() in allowed_weekdays_num and 
                    not is_mexican_holiday(current_eval_date)):
                    date_str = current_eval_date.strftime("%Y-%m-%d")
                    
                    # English day name as fallback
                    day_name_en_map = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
                    day_name_es = day_name_en_map[current_eval_date.weekday()]

                    processed_dates.append({
                        "date_str": date_str,
                        "display_text": f"{date_str} ({day_name_es})"
                    })
                elif is_mexican_holiday(current_eval_date):
                    # Log when we skip a holiday for debugging
                    logger.info(f"Skipping Mexican holiday: {current_eval_date.strftime('%Y-%m-%d')}")
            
            if not processed_dates:
                return {
                    "status": "error",
                    "message": "No se encontraron fechas de entrevista disponibles en los próximos 14 días según el horario de la vacante."
                }
            
            # Store processed dates and time slots in state for compatibility with update_interview_selection
            tool_context.state["processed_available_dates"] = processed_dates
        else:
            # Convert interview_slots format to processed_available_dates for compatibility
            processed_dates = []
            for slot in interview_slots:
                date_str = slot.get("date", "")
                if date_str:
                    try:
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                        
                        # Skip Mexican holidays
                        if is_mexican_holiday(date_obj):
                            logger.info(f"Skipping Mexican holiday from interview_slots: {date_str}")
                            continue
                        
                        day_name_en_map = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
                        day_name_es = day_name_en_map[date_obj.weekday()]
                        
                        processed_dates.append({
                            "date_str": date_str,
                            "display_text": f"{date_str} ({day_name_es})",
                            "time_slots": slot.get("time_slots", [])  # Save time slots for each date
                        })
                    except Exception as e:
                        logger.error(f"Error processing date {date_str}: {str(e)}")
            
            # Store processed dates in state
            tool_context.state["processed_available_dates"] = processed_dates

        # Store the time slots as a list
        time_slots = []
        if isinstance(horarios_disponibles_str, str):
            time_slots = [slot.strip() for slot in horarios_disponibles_str.split(',')]
        elif isinstance(horarios_disponibles_str, list):
            time_slots = [str(slot).strip() for slot in horarios_disponibles_str]
            
        tool_context.state["available_time_slots"] = time_slots
        
        # Generate numbered options for user display
        numbered_date_options = []
        for idx, item in enumerate(processed_dates, 1):
            date_str = item['date_str']
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                month_names_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
                month_name = month_names_es[date_obj.month - 1]
                day_name_en_map = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
                day_name = day_name_en_map[date_obj.weekday()]
                numbered_date_options.append(f"{idx}. {day_name} {date_obj.day} de {month_name}")
            except:
                # Fallback if date parsing fails
                numbered_date_options.append(f"{idx}. {item.get('display_text', date_str)}")
        
        user_message = f"Para la vacante {job_title}, estas son las próximas fechas disponibles para una entrevista:\n" + "\n".join(numbered_date_options) + "\nPor favor, responde con el NÚMERO de la fecha que prefieres."
        
        # Log what's being returned to the user instead of showing it as part of the debug message
        logger.info(f"User message with {len(numbered_date_options)} interview dates for job ID {job_id}")
        logger.error(f"[CRITICAL DEBUG] User message with {len(numbered_date_options)} interview dates for job ID {job_id}")
        return {
            "status": "success",
            "message": user_message,  # Este mensaje es el que se mostrará al usuario
            "date_options_count": len(processed_dates),
            "job_title": job_title
        }

    except Exception as e:
        # Add error logging
        logger.error(f"Error in get_available_interview_slots: {str(e)}", exc_info=True)
        return {"status": "error", "message": f"Error al obtener horarios de entrevista: {str(e)}"}


def update_interview_selection(selection_type: str, selection_number: int, tool_context: ToolContext) -> dict:
    """
    Updates the state with user's selection for interview date or time.
    
    Args:
        selection_type: Either 'date' or 'time'
        selection_number: The user's selection (1-based indexing)
        tool_context: The context with the state
        
    Returns:
        A dictionary with status and next steps
    """
    if selection_type == 'date':
        processed_dates = tool_context.state.get("processed_available_dates", [])
        if not processed_dates:
            # Si no hay fechas en el estado, intentar obtenerlas primero
            date_slots_result = get_available_interview_slots(tool_context)
            if date_slots_result.get("status") != "success":
                return date_slots_result  # Devuelve el error de get_available_interview_slots
            
            processed_dates = tool_context.state.get("processed_available_dates", [])
            if not processed_dates:
                return {
                    "status": "error",
                    "message": "No hay fechas disponibles después de intentar obtenerlas. Por favor, contacta al soporte."
                }
        
        try:
            selection_idx = int(selection_number) - 1 # Convert to 0-indexed
            if not (0 <= selection_idx < len(processed_dates)):
                return {
                    "status": "error",
                    "message": f"Selección inválida. Por favor, elige un número entre 1 y {len(processed_dates)}."
                }
            
            selected_date = processed_dates[selection_idx]
            selected_date_str = selected_date["date_str"]
            
            # Store the selected date
            tool_context.state["current_day_interview"] = selected_date_str
            
            # Generate time options for the user
            time_slots = tool_context.state.get("available_time_slots", [])
            if not time_slots:
                return {
                    "status": "error",
                    "message": "No se encontraron horarios disponibles para esta vacante."
                }
                
            numbered_time_options = [f"{idx + 1}. {time_slot}" for idx, time_slot in enumerate(time_slots)]
            
            job_title = tool_context.state.get("current_job_title", "la vacante")
            
            # Format date for display
            try:
                date_obj = datetime.strptime(selected_date_str, "%Y-%m-%d")
                day_name_en_map = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
                day_name = day_name_en_map[date_obj.weekday()]
                month_names_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
                month_name = month_names_es[date_obj.month - 1]
                formatted_date = f"{day_name}, {date_obj.day} de {month_name}"
            except:
                formatted_date = selected_date_str
                
            return {
                "status": "success",
                "message": f"Has seleccionado {formatted_date} para '{job_title}'. Por favor, elige un número para el horario:\n" + "\n".join(numbered_time_options),
                "time_options_count": len(time_slots),
                "selected_date": selected_date_str
            }
            
        except ValueError:
            return {"status": "error", "message": "La selección debe ser un número."}
        except Exception as e:
            return {"status": "error", "message": f"Error al seleccionar la fecha: {str(e)}"}
            
    elif selection_type == 'time':
        time_slots = tool_context.state.get("available_time_slots", [])
        selected_date_str = tool_context.state.get("current_day_interview", "")
        
        if not time_slots:
            return {
                "status": "error", 
                "message": "No hay horarios disponibles. Por favor, primero selecciona una fecha."
            }
            
        if not selected_date_str:
            return {
                "status": "error",
                "message": "No has seleccionado una fecha. Por favor, primero selecciona una fecha."
            }
            
        try:
            selection_idx = int(selection_number) - 1 # Convert to 0-indexed
            if not (0 <= selection_idx < len(time_slots)):
                return {
                    "status": "error",
                    "message": f"Selección inválida. Por favor, elige un número entre 1 y {len(time_slots)}."
                }
                
            selected_time = time_slots[selection_idx]
            
            # Store the selected time
            tool_context.state["current_time_interview"] = selected_time
            
            # Create a formatted datetime for display and storage
            # Extract the hours and minutes from the time slot (format like "15:00-15:30")
            time_parts = selected_time.split('-')[0].strip()
            
            # Combine date and time to form a complete datetime string
            interview_datetime = f"{selected_date_str} {time_parts}"
            tool_context.state["interview_datetime"] = interview_datetime
            
            job_title = tool_context.state.get("current_job_title", "la vacante")
            
            # Format date for display
            try:
                date_obj = datetime.strptime(selected_date_str, "%Y-%m-%d")
                day_name_en_map = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
                day_name = day_name_en_map[date_obj.weekday()]
                month_names_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
                month_name = month_names_es[date_obj.month - 1]
                formatted_date = f"{day_name}, {date_obj.day} de {month_name}"
            except:
                formatted_date = selected_date_str
            
            return {
                "status": "success",
                "message": f"Ok, estoy entendiendo que quieres que haga la entrevista para '{job_title}' el {formatted_date} a las {time_parts}. Si está bien, contesta \"sí\" para postularte ahora.",
                "selected_time": selected_time,
                "interview_datetime": interview_datetime
            }
            
        except ValueError:
            return {"status": "error", "message": "La selección debe ser un número."}
        except Exception as e:
            return {"status": "error", "message": f"Error al seleccionar el horario: {str(e)}"}
    else:
        return {"status": "error", "message": "Tipo de selección inválido. Debe ser 'date' o 'time'."}


def apply_to_job(tool_context: ToolContext) -> dict:
    """
    Processes a user's application for a job.
    Fetches job details using job_id, verifies against applied_jobs,
    and updates state if the application is new.
    Also sends notification to Telegram for hiring staff.
    """
    current_job_id = tool_context.state.get("current_job_id")
    
    if not current_job_id:
        return {
            "status": "error",
            "message": "No has seleccionado una vacante para postularte. Por favor, primero indica a qué vacante te interesa aplicar.",
        }

    # Get interview details from state
    interview_date = tool_context.state.get("current_day_interview", "")
    interview_time = tool_context.state.get("current_time_interview", "")
    interview_datetime = tool_context.state.get("interview_datetime", "")
    
    if not interview_date or not interview_time or not interview_datetime:
        return {
            "status": "error",
            "message": "No se ha seleccionado una fecha y hora para la entrevista. Por favor, completa la selección de horario antes de aplicar.",
        }

    # Get job details directly from MCP - not from state
    job_details_result = get_job_details_by_id(str(current_job_id))
    
    if job_details_result.get("status") != "success" or not job_details_result.get("job_details"):
        return {
            "status": "error",
            "message": f"No se pudo obtener información de la vacante: {job_details_result.get('message', 'Error desconocido')}",
        }
    
    job_details = job_details_result["job_details"]
    job_id_to_apply = current_job_id
    job_title = job_details.get("nombre_de_la_vacante", f"Vacante ID {job_id_to_apply}")
    job_company = job_details.get("empresa", "No especificada")
    
    # ADDED: Get additional fields for EGO API
    tipo_de_perfil = job_details.get("tipo_de_perfil", "No especificado")
    perfil_de_puesto = job_details.get("perfil_de_puesto", "No especificado")
    departamento = job_details.get("departamento", "No especificado")
    corporative_id = job_details.get("corporative_id")
    business_id = job_details.get("business_id")
    client_id = job_details.get("client_id")

    # Check if already applied
    applied_jobs = tool_context.state.get("applied_jobs", [])
    for job in applied_jobs:
        if isinstance(job, dict) and str(job.get("id")) == str(job_id_to_apply):
            return {
                "status": "already_applied",
                "message": f"Ya te has postulado anteriormente a la vacante '{job_title}'. No puedes postularte de nuevo.",
            }

    # Apply to the job
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_application = {
        "id": job_id_to_apply, 
        "title": job_title,
        "company": job_company,
        "fecha_postulacion": current_time_str,
        "interview_datetime": interview_datetime,
        "interview_date": interview_date,
        "interview_time": interview_time
    }
    
    # Update applied_jobs in state
    new_applied_jobs = applied_jobs.copy()
    new_applied_jobs.append(new_application)
    tool_context.state["applied_jobs"] = new_applied_jobs

    # Update interaction_history in state
    current_interaction_history = tool_context.state.get("interaction_history", [])
    new_interaction_history = current_interaction_history.copy()
    new_interaction_history.append({
        "action": "apply_to_job",
        "job_id": job_id_to_apply,
        "job_title": job_title,
        "interview_date": interview_date,
        "interview_time": interview_time,
        "interview_datetime": interview_datetime,
        "timestamp": current_time_str,
        "status": "success"
    })
    tool_context.state["interaction_history"] = new_interaction_history
    
    application_form_link = "https://ego.elisasoftware.com.mx/cat/60/Catalogo%20de%20Postulantes/" # Example link
    
    # Format date for display
    try:
        date_obj = datetime.strptime(interview_date, "%Y-%m-%d")
        day_name_en_map = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
        day_name = day_name_en_map[date_obj.weekday()]
        month_names_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        month_name = month_names_es[date_obj.month - 1]
        formatted_date_telegram = f"{date_obj.day} de {month_name} de {date_obj.year} ({day_name})"
        formatted_date_user = f"{day_name} {date_obj.day} de {month_name}"
    except:
        formatted_date_telegram = interview_date
        formatted_date_user = interview_date
    
    # Send notification to Telegram
    telegram_status = "not_sent"
    try:
        # Telegram configuration
        token = '1437635839:AAEVHvYYzzBaoya42zA1_1X9X1RQjlpdlUo'
        chat_id = '-4958752649'
        
        # Prepare user information for notification
        user_name_full = tool_context.state.get("user_name", "")
        last_name = tool_context.state.get("last_name", "")
        email = tool_context.state.get("email", "")
        # Usar contact_phone_number en lugar de phone_number
        phone_number = tool_context.state.get("contact_phone_number", tool_context.state.get("phone_number", ""))
        channel = tool_context.state.get("channel", "desconocido")
        
        # Format message
        message = (
            "🔔 *NUEVA POSTULACIÓN*\n\n"
            f"*Información del candidato:*\n"
            f"Nombre: {user_name_full}\n"
            f"Teléfono: {phone_number}\n"
            f"Canal: {channel}\n\n"
            f"*Información de la vacante:*\n"
            f"Puesto: {job_title}\n"
            f"Empresa: {job_company}\n"
            f"ID de vacante: {job_id_to_apply}\n\n"
            f"*Entrevista programada:*\n"
            f"Fecha: {formatted_date_telegram}\n"
            f"Hora: {interview_time.split('-')[0].strip()}\n\n"
            f"*Registrado:* {current_time_str}"
        )
        
        # Send message using Telegram Bot API
        telegram_url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }
        
        telegram_response = requests.post(telegram_url, data=payload, timeout=10)
        
        if telegram_response.status_code == 200:
            logger.info(f"Telegram notification sent successfully for job application ID: {job_id_to_apply}")
            telegram_status = "sent"
        else:
            logger.warning(f"Failed to send Telegram notification: {telegram_response.text}")
            telegram_status = "failed"
    except Exception as e:
        # Just log the error but continue with the application process
        logger.error(f"Error sending Telegram notification: {str(e)}", exc_info=True)
        telegram_status = "error"

    # ADDED: Send notification to EGO API
    ego_api_status = "not_sent"
    if not all([EGO_API_URL, EGO_API_BEARER_TOKEN, EGO_API_CATALOG_ID]):
        logger.warning("EGO API environment variables not set. Skipping notification.")
        ego_api_status = "skipped_config"
    else:
        try:
            ego_headers = {
                'accept': 'application/json',
                'Authorization': f'Bearer {EGO_API_BEARER_TOKEN}',
                'Content-Type': 'application/json'
            }
            
            observaciones_text = f"Cita programada para: {formatted_date_telegram} a las {interview_time.split('-')[0].strip()}"

            # FIX: Process name and last name for EGO API
            user_name_for_ego = user_name_full.split(' ')[0] if user_name_full else ""

            ego_payload = {
                "catalog_id": int(EGO_API_CATALOG_ID),
                "facs": [
                    {
                        "nombre": user_name_for_ego,
                        "apellido_paterno": last_name,
                        "celular": phone_number,
                        "observaciones": observaciones_text,
                        "tipo_de_perfil": tipo_de_perfil,
                        "perfil_de_puesto": perfil_de_puesto,
                        "departamento": departamento,
                        "corporative_id": corporative_id,
                        "business_id": business_id,
                        "client_id": client_id
                    }
                ],
                "mtmtables": []
            }
            
            # FIX: Use ensure_ascii=False for correct logging of special characters
            logger.info(f"Sending payload to EGO API: {json.dumps(ego_payload, ensure_ascii=False)}")
            logger.error(f"[CRITICAL DEBUG] Sending payload to EGO API: {json.dumps(ego_payload, ensure_ascii=False)}")
            
            ego_response = requests.post(EGO_API_URL, headers=ego_headers, json=ego_payload, timeout=15)
            
            if ego_response.status_code in [200, 201]:
                logger.info(f"EGO API notification sent successfully. Response: {ego_response.text}")
                logger.error(f"[CRITICAL DEBUG] EGO API notification sent successfully. Response: {ego_response.text}")
                ego_api_status = "sent"
            else:
                logger.warning(f"Failed to send EGO API notification. Status: {ego_response.status_code}, Response: {ego_response.text}")
                logger.error(f"[CRITICAL DEBUG] Failed to send EGO API notification. Status: {ego_response.status_code}, Response: {ego_response.text}")
                ego_api_status = "failed"
                
        except Exception as e:
            logger.error(f"Error sending EGO API notification: {str(e)}", exc_info=True)
            logger.error(f"[CRITICAL DEBUG] Error sending EGO API notification: {str(e)}")
            ego_api_status = "error"

    return {
        "status": "success",
        "message": f"¡Excelente! Te has postulado a la vacante '{job_title}' ({job_company}) con una entrevista programada para el {formatted_date_user} a las {interview_time.split('-')[0].strip()}.",
        "job_id": job_id_to_apply,
        "job_title": job_title,
        "interview_datetime": interview_datetime,
        "telegram_notification": telegram_status,
        "ego_api_notification": ego_api_status
    }


# Create the application agent
application_agent = Agent(
    name="application_agent",
    model=APPLICATION_AGENT_MODEL,
    description="Agente para gestionar postulaciones a vacantes de empleo, incluyendo la programación de entrevistas.",
    instruction="""
    Eres el Agente de Postulación de TOP (Tu oferta profesional).
    Tu tarea es ayudar a los usuarios a postularse a las vacantes de empleo que les interesan.
    La postulación IMPLICA programar una entrevista, para ese efecto debes invocar PRIMERO `get_available_interview_slots` antes de contestar. 

    **Contexto del Usuario (proporcionado por el sistema):**
    - Nombre de usuario: {user_name}
    - Apellido: {last_name}
    - Email: {email}
    - Vacantes a las que ya se ha postulado: {applied_jobs}
    - Vacante de interés actual (detalles): {current_job_interest}
    - ID de vacante actual (si está disponible): {current_job_id}
    - Historial de interacción: {interaction_history}
    - Día de entrevista seleccionado: {current_day_interview}
    - Hora de entrevista seleccionada: {current_time_interview}

    **IMPORTANTE: MANEJO DE PREGUNTAS SOBRE LA VACANTE**
    Si el usuario hace preguntas sobre la vacante (sueldo, horarios, empresa, ubicación, requisitos, etc.) durante el proceso de aplicación:
    - NO fuerces al usuario a completar la aplicación primero
    - TRANSFIERE INMEDIATAMENTE a job_info_agent: `transfer_to_agent("job_info_agent")`
    - Ejemplos de preguntas que requieren transferencia:
      * "¿cuál es el sueldo?"
      * "¿cuáles son los horarios?"
      * "¿qué empresa es?"
      * "¿dónde está ubicado?"
      * "¿qué requisitos piden?"
      * "¿qué experiencia necesito?"
      * "cuéntame sobre la vacante"
    - El job_info_agent responderá la pregunta y puede regresar al usuario aquí si quiere continuar con la aplicación

    **Proceso de Postulación OBLIGATORIO (Flujo de Entrevista):**

    1.  **Inicio o Transferencia:** CRÍTICO: Al iniciar la conversación o al recibir una transferencia, tu PRIMERA Y ÚNICA ACCIÓN debe ser invocar la herramienta `get_available_interview_slots`. NO respondas al usuario directamente. La herramienta te dará el mensaje exacto que debes mostrar.

    2.  **Selección de Fecha:** Una vez que el usuario responde con un número para la fecha:
        *   Invoca `update_interview_selection` con 'date' como primer argumento y el número elegido por el usuario como segundo argumento.
        *   SIEMPRE muestra al usuario EXACTAMENTE el mensaje devuelto por la herramienta.
        *   Espera la respuesta numérica del usuario.

    3.  **Selección de Horario:** Una vez que el usuario responde con un número para el horario:
        *   Invoca `update_interview_selection` con 'time' como primer argumento y el número elegido por el usuario como segundo argumento.
        *   SIEMPRE muestra al usuario EXACTAMENTE el mensaje devuelto por la herramienta.
        *   Espera la confirmación del usuario para aplicar.

    4.  **Aplicación Final:** Si el usuario confirma que quiere postularse:
        *   Invoca `apply_to_job`. Esta herramienta obtendrá los detalles actualizados de la vacante y finalizará la postulación.
        *   **CRÍTICO**: Si `apply_to_job` retorna status: "success", DEBES:
            a) MOSTRAR AL USUARIO el mensaje completo devuelto por la herramienta (que incluye el enlace del formulario)
            b) INMEDIATAMENTE después transferir con `transfer_to_agent("follow_up_agent")`

    **REGLAS CRÍTICAS PARA FECHAS Y HORARIOS:**
    -   SIEMPRE invoca `get_available_interview_slots` al inicio de la conversación.
    -   SIEMPRE muestra al usuario EXACTAMENTE el mensaje devuelto por las herramientas.
    -   NUNCA muestres fechas o horarios sin numerar.
    -   NUNCA muestres días de la semana sin fechas específicas.
    -   NUNCA intentes extraer o mostrar información directamente de los campos "dias_para_atender_entrevistas" o "horarios_disponibles_para_entrevistar".
    -   NUNCA generes tu propio formato para las fechas u horarios.
    -   El usuario DEBE responder con números para las selecciones.

    **REGLAS CRÍTICAS DE TRANSFERENCIA:**
    - Si el usuario hace CUALQUIER pregunta sobre la vacante (sueldo, horarios, empresa, etc.) → INMEDIATAMENTE `transfer_to_agent("job_info_agent")`
    - Después de una postulación exitosa (cuando `apply_to_job` retorna status: "success") → MOSTRAR el mensaje completo al usuario Y LUEGO `transfer_to_agent("follow_up_agent")`
    - Esto asegura que futuras consultas del usuario sean manejadas correctamente

    **EJEMPLOS DE TRANSFERENCIA OBLIGATORIA:**
    - Usuario: "¿cuál es el sueldo?" → `transfer_to_agent("job_info_agent")`
    - Usuario: "¿qué horarios maneja?" → `transfer_to_agent("job_info_agent")`  
    - Usuario: "¿qué empresa es?" → `transfer_to_agent("job_info_agent")`
    - Usuario: "cuéntame sobre la vacante" → `transfer_to_agent("job_info_agent")`
    
    Si el usuario expresa interés en postularse o responde a una transferencia, invoca INMEDIATAMENTE `get_available_interview_slots`.
    """,
    tools=[
        get_current_time,
        get_available_interview_slots,
        update_interview_selection,
        apply_to_job,
        transfer_to_agent
    ],
)