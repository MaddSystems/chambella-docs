# utils.py

from datetime import datetime
import asyncio
from google.genai import types
from google.genai.errors import ServerError
import logging
import argparse
import sys

# LOGGING CONFIGURATION - Now supports levels 0-3
VERBOSE_LEVEL = 0  # Default level, will be overridden by command line args

def parse_verbosity_args():
    """Parse command line arguments for verbosity level"""
    global VERBOSE_LEVEL
    
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--v', type=int, default=0, choices=[0, 1, 2, 3],
                       help='Verbosity level: 0=minimal, 1=basic, 2=detailed, 3=full debug')
    
    args, _ = parser.parse_known_args()
    VERBOSE_LEVEL = args.v
    
    print(f"🔧 Verbosity level set to: {VERBOSE_LEVEL}")
    return VERBOSE_LEVEL

def configure_llm_logging(verbose_level=None):
    if verbose_level is None:
        verbose_level = VERBOSE_LEVEL
    
    if verbose_level == 0:
        logging.getLogger('google.adk.models.google_llm').setLevel(logging.ERROR)
        logging.getLogger('google_genai.models').setLevel(logging.ERROR)
        logging.getLogger('httpcore').setLevel(logging.ERROR)
        logging.getLogger('httpx').setLevel(logging.ERROR)
        logging.getLogger('google.adk.sessions.database_session_service').setLevel(logging.WARNING)
    elif verbose_level == 1:
        logging.getLogger('google.adk.models.google_llm').setLevel(logging.WARNING)
        logging.getLogger('google_genai.models').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('google.adk.sessions.database_session_service').setLevel(logging.INFO)
    elif verbose_level == 2:
        logging.getLogger('google.adk.models.google_llm').setLevel(logging.INFO)
        logging.getLogger('google_genai.models').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)
        logging.getLogger('httpx').setLevel(logging.INFO)
        logging.getLogger('google.adk.sessions.database_session_service').setLevel(logging.INFO)
    else:  # verbose_level >= 3
        logging.getLogger('google.adk.models.google_llm').setLevel(logging.INFO)
        logging.getLogger('google_genai.models').setLevel(logging.INFO)
        logging.getLogger('httpcore').setLevel(logging.DEBUG)
        logging.getLogger('httpx').setLevel(logging.INFO)
        logging.getLogger('google.adk.sessions.database_session_service').setLevel(logging.DEBUG)

configure_llm_logging()

class Colors:
    RESET, BOLD, UNDERLINE = "\033[0m", "\033[1m", "\033[4m"
    BLACK, RED, GREEN, YELLOW = "\033[30m", "\033[31m", "\033[32m", "\033[33m"
    BLUE, MAGENTA, CYAN, WHITE = "\033[34m", "\033[35m", "\033[36m", "\033[37m"
    BG_BLACK, BG_RED, BG_GREEN, BG_YELLOW = "\033[40m", "\033[41m", "\033[42m", "\033[43m"
    BG_BLUE, BG_MAGENTA, BG_CYAN, BG_WHITE = "\033[44m", "\033[45m", "\033[46m", "\033[47m"

def update_interaction_history(session_service, app_name, user_id, session_id, entry):
    """Agregar una entrada al historial de interacciones en el estado.

    Args:
        session_service: La instancia del servicio de sesión
        app_name: El nombre de la aplicación
        user_id: El ID del usuario
        session_id: El ID de la sesión
        entry: Un diccionario que contiene los datos de la interacción
            - requiere la clave 'action' (por ejemplo, 'user_query', 'agent_response')
            - otras claves son flexibles dependiendo del tipo de acción
    """
    try:
        # Get current session
        session = session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )

        # Get current interaction history
        interaction_history = session.state.get("interaction_history", [])

        # Add timestamp if not already present
        if "timestamp" not in entry:
            entry["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Add the entry to interaction history
        interaction_history.append(entry)

        # Create updated state
        updated_state = session.state.copy()
        updated_state["interaction_history"] = interaction_history

        # Delete the old session
        session_service.delete_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id
        )

        # Create a new session with the updated state and the same ID
        session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,  # Use the same session_id
            state=updated_state,
        )
    except Exception as e:
        print(f"Error al actualizar el historial de interacciones: {e}")


def add_user_query_to_history(session_service, app_name, user_id, session_id, query):
    """Agregar una consulta del usuario al historial de interacciones."""
    try:
        update_interaction_history(
            session_service,
            app_name,
            user_id,
            session_id,
            {
                "action": "user_query",
                "query": query,
            },
        )
    except Exception as e:
        print(f"Error al actualizar el historial de interacciones: {e}")


def add_agent_response_to_history(session_service, app_name, user_id, session_id, agent_name, response):
    """Adds an agent's response to the interaction history."""
    update_interaction_history(
        session_service,
        app_name,
        user_id,
        session_id,
        {
            "action": "agent_response",
            "agent": agent_name,
            "response": response,
        },
    )


def prepare_whatsapp_response(text):
    if not text:
        return "Lo siento, no pude procesar su consulta. Por favor intente nuevamente."
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


def display_state(session_service, app_name, user_id, session_id, label="Estado Actual"):
    """Displays the current session state in a formatted way."""
    try:
        session = session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
        print(f"\n{'-' * 10} {label} {'-' * 10}")
        user_name = session.state.get("user_name", "No registrado") or "No registrado"
        print(f"👤 Usuario: {user_name}")
        
        applied_jobs_list = session.state.get("applied_jobs", [])
        if applied_jobs_list:
            print("💼 Postulaciones Realizadas:")
            for job_app in applied_jobs_list:
                if isinstance(job_app, dict):
                    print(f"  - ID: {job_app.get('id', 'N/A')}, Postulación: {job_app.get('fecha_postulacion', 'N/A')}")
                else:
                    print(f"  - {job_app}")
        else:
            print("💼 Postulaciones Realizadas: Ninguna")

        interaction_history = session.state.get("interaction_history", [])
        if interaction_history:
            print("📝 Historial de Interacciones:")
            for idx, interaction in enumerate(interaction_history, 1):
                if isinstance(interaction, dict):
                    action = interaction.get("action", "interacción")
                    timestamp = interaction.get("timestamp", "")
                    content = ""
                    if action == "user_query":
                        content = f"\"{interaction.get('query', '')}\""
                    elif action == "agent_response":
                        content = f"de {interaction.get('agent', '?')}: \"{interaction.get('response', '')[:80]}...\""
                    print(f'  {idx}. [{timestamp}] {action.title()} {content}')
                else:
                    print(f"  {idx}. {interaction}")
        else:
            print("📝 Historial de Interacciones: Ninguno")

        print("🔑 Estado Actual:")
        other_keys = {k: v for k, v in session.state.items() if k not in ["user_name", "applied_jobs", "interaction_history"]}
        for key, value in other_keys.items():
            print(f"  {key}: {value}")
        print("-" * (22 + len(label)))
    except Exception as e:
        logging.error(f"Error displaying state: {e}")


async def process_agent_response(event, for_whatsapp=False, verbose_level=None):
    if verbose_level is None: verbose_level = VERBOSE_LEVEL
    final_response = None
    if event.is_final_response() and event.content and event.content.parts and hasattr(event.content.parts[0], "text"):
        final_response = event.content.parts[0].text.strip()
        if verbose_level >= 1:
            if not for_whatsapp:
                print(f"\n{Colors.BG_BLUE}{Colors.WHITE}{Colors.BOLD} RESPUESTA DEL AGENTE {Colors.RESET}\n{Colors.CYAN}{final_response}{Colors.RESET}\n")
            else:
                print(f"\n== RESPUESTA DEL AGENTE (WhatsApp) ==\n{final_response}\n====================================\n")
    return final_response


async def call_agent_async(runner, user_id, session_id, query, for_whatsapp=False, max_retries=3, verbose_level=None):
    if verbose_level is None: verbose_level = VERBOSE_LEVEL
        
    content = types.Content(role="user", parts=[types.Part(text=query)])
    
    import os
    os.environ["LITELLM_SESSION_ID"] = session_id
    os.environ["LITELLM_USER_ID"] = user_id
    
    if verbose_level >= 1:
        display_state(runner.session_service, runner.app_name, user_id, session_id, "Estado ANTES de procesar")
        print(f"\n{Colors.BG_GREEN}{Colors.BLACK}--- Ejecutando Consulta: {query} ---{Colors.RESET}")
        
    final_response_text = None
    agent_name = None

    for attempt in range(max_retries):
        try:
            async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
                if event.author: agent_name = event.author
                response = await process_agent_response(event, for_whatsapp=for_whatsapp, verbose_level=verbose_level)
                if response: final_response_text = response
            break 
        except ServerError as e:
            if "503" in str(e) and "overloaded" in str(e).lower() and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"{Colors.BG_YELLOW}{Colors.BLACK}Modelo sobrecargado, reintentando en {wait_time}s...{Colors.RESET}")
                await asyncio.sleep(wait_time)
            else:
                logging.error(f"ServerError on final attempt: {e}")
                final_response_text = "Lo siento, el servicio está temporalmente saturado. Por favor intenta nuevamente en unos momentos."
                break
        except Exception as e:
            logging.error(f"ERROR durante la ejecución del agente: {e}", exc_info=True)
            final_response_text = "Lo siento, ocurrió un error al procesar tu solicitud. Por favor intenta nuevamente."
            break

    if final_response_text and agent_name:
        add_agent_response_to_history(
            runner.session_service, runner.app_name, user_id, session_id, agent_name, final_response_text
        )

    if verbose_level >= 1:
        display_state(runner.session_service, runner.app_name, user_id, session_id, "Estado DESPUÉS de procesar")
        
    return final_response_text