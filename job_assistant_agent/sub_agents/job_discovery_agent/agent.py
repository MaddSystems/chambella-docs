from google.adk.agents import Agent
from google.adk.tools import transfer_to_agent
from google.adk.tools.tool_context import ToolContext
import json
import logging
import os
import requests
from dotenv import load_dotenv

# Import centralized config
from config import INFO_AGENT_MODEL

# Construct path to the parent directory's .env file
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path, override=True)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Load environment variables
MCP_PORT = os.getenv("MCP_PORT")
if not MCP_PORT:
    raise RuntimeError("MCP_PORT environment variable is required for MCP_SERVER_URL")
try:
    MCP_PORT_INT = int(MCP_PORT)
except ValueError:
    raise RuntimeError(f"Invalid MCP_PORT value: {MCP_PORT}")
MCP_SERVER_URL = f"http://localhost:{MCP_PORT_INT}"
MCP_CONNECTION_TIMEOUT = int(os.getenv("MCP_CONNECTION_TIMEOUT", "5"))


def get_available_vacantes(offset: int = 0, tool_context: ToolContext = None) -> dict:
    """
    Get a paginated list of available job vacancies from the MCP server.
    
    :param offset: The starting index for fetching vacancies.
    :param tool_context: The context of the tool.
    """
    logger.info(f"🔧🔧🔧 TOOL EXECUTION: get_available_vacantes called with offset: {offset}")
    print(f"🔧🔧🔧 MCP TOOL CALLED: get_available_vacantes starting execution")
    
    try:
        mcp_url = f"{MCP_SERVER_URL}/mcp/tool/search_available_vacancies"
        logger.info(f"📡📡📡 Making HTTP request to MCP server: {mcp_url}")
        print(f"📡📡📡 HTTP REQUEST to MCP: {mcp_url}")
        
        response = requests.post(
            mcp_url,
            json={"detail_level": "summary", "offset": offset, "limit": 10},
            timeout=float(MCP_CONNECTION_TIMEOUT)
        )
        
        logger.info(f"📡📡📡 MCP Response status: {response.status_code}")
        print(f"📡📡📡 MCP RESPONSE STATUS: {response.status_code}")
        
        response.raise_for_status()
        
        data = response.json()
        vacantes = data.get("results", [])
        pagination_info = data.get("pagination", {})

        logger.info(f"✅✅✅ Successfully retrieved {len(vacantes)} vacantes from MCP server")
        print(f"✅✅✅ MCP SUCCESS: Retrieved {len(vacantes)} fresh vacantes")

        if not vacantes:
            logger.warning("❌❌❌ No vacantes found from MCP server")
            print("❌❌❌ MCP WARNING: No vacantes available")
            return {"status": "error", "message": "No se encontraron más vacantes disponibles."}

        # Format for display
        formatted_vacantes = [
            {"job_id": vacante.get("Id_Vacante"), "title": vacante.get("Nombre_de_la_vacante", "Sin título")}
            for vacante in vacantes
        ]
        
        logger.info(f"🎯🎯🎯 Returning {len(formatted_vacantes)} formatted vacantes to agent")
        print(f"🎯🎯🎯 TOOL RETURNING: {len(formatted_vacantes)} vacantes to job_discovery_agent")
        
        return {
            "status": "success", 
            "vacantes": formatted_vacantes,
            "pagination": pagination_info
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"❌❌❌ RequestException in get_available_vacantes: {e}", exc_info=True)
        print(f"❌❌❌ MCP ERROR: RequestException - {e}")
        return {"status": "error", "message": f"Error de conexión al obtener las vacantes: {e}"}
    except json.JSONDecodeError as e:
        logger.error(f"❌❌❌ JSONDecodeError in get_available_vacantes: {e}", exc_info=True)
        print(f"❌❌❌ MCP ERROR: JSONDecodeError - {e}")
        return {"status": "error", "message": f"Error decodificando la respuesta de las vacantes: {e}"}
    except Exception as e:
        logger.error(f"❌❌❌ Generic error in get_available_vacantes: {e}", exc_info=True)
        print(f"❌❌❌ MCP ERROR: Generic exception - {e}")
        return {"status": "error", "message": f"Error inesperado al obtener las vacantes: {e}"}


def select_job(job_id: str, job_title: str, tool_context: ToolContext) -> dict:
    """Selects a job, updates the session state, and transfers to the job_info_agent."""
    logger.debug(f"select_job called with ID: {job_id} and Title: {job_title}")

    if not job_id or not job_title:
        return {"status": "error", "message": "No se proporcionó un ID o título de vacante."}

    # Update the state with the selected job information
    tool_context.state["current_job_id"] = job_id
    tool_context.state["current_job_title"] = job_title
    
    # Clear part of the history so the next agent is not confused
    tool_context.state["interaction_history"] = []

    logger.info(f"Session state updated with new job: ID {job_id}, Title '{job_title}'")

    # Transfer to the job_info_agent to provide details about the selected job
    transfer_to_agent(agent_name="job_info_agent", tool_context=tool_context)

    return {"status": "success", "message": f"Vacante '{job_title}' seleccionada. Transfiriendo a agente de información."}


# Job Discovery Agent
job_discovery_agent = Agent(
    name="job_discovery_agent",
    model=INFO_AGENT_MODEL,
    description="Agente para descubrir y seleccionar vacantes.",
    instruction='''
    Eres "Chambella", un asistente virtual amigable y profesional para ayudar al usuario a seleccionar una vacante de su interés.

    **REGLA CRÍTICA FUNDAMENTAL:**
    SIEMPRE, SIN EXCEPCIÓN, debes llamar a la herramienta `get_available_vacantes()` para obtener vacantes frescas del servidor MCP.
    NUNCA uses información previa o del historial. SIEMPRE consulta el servidor.

    **FLUJO OBLIGATORIO (NO OPCIONAL):**
    1. **PRIMERA ACCIÓN MANDATORIA:** Llama INMEDIATAMENTE a `get_available_vacantes()` - NO hagas nada más hasta ejecutar esta herramienta
    2. **ESPERA los resultados** de la herramienta MCP
    3. **SOLO ENTONCES** presenta las vacantes al usuario

    **INSTRUCCIONES ESPECÍFICAS:**

    **INICIO DE CONVERSACIÓN:**
    - Tu PRIMERA y ÚNICA acción es: `get_available_vacantes()`
    - NO respondas con texto hasta que hayas ejecutado la herramienta
    - NO uses listas hardcodeadas o del historial
    - SIEMPRE consulta el servidor MCP en tiempo real

    **PRESENTACIÓN DE VACANTES:**
    - SOLO después de recibir resultados del MCP, presenta:
      "¡Hola! Te ayudaré a encontrar una vacante. Aquí tienes las vacantes disponibles:
      1. [Título real del MCP]
      2. [Título real del MCP]
      Por favor, dime el número de la vacante que te interesa. (selecciona solo una)"

    **SELECCIÓN DE USUARIO:**
    - Cuando el usuario elija una vacante con un solo número, llama a `select_job()` con los datos REALES del MCP.
    - Si el usuario da una respuesta múltiple o confusa (ej: "la 1 y la 2", "dime de todas"), DEBES responder: "Por favor, selecciona un número correspondiente al menu de vacantes. Si quieres ver el menu principal teclea vacantes" y esperar a que elija una sola opción. NO llames a ninguna herramienta hasta que elija un solo número.

    **TRANSFERENCIA DE AGENTE:**
    - La transferencia al siguiente agente (`job_info_agent`) se realiza AUTOMÁTICAMENTE dentro de la herramienta `select_job`.
    - Por lo tanto, NO puedes transferir al agente de información hasta que el usuario haya hecho una selección de vacante ÚNICA y VÁLIDA.
    - Si el usuario no selecciona una opción del menú, DEBES insistir y volver a presentar el menú. NO llames a `select_job` ni intentes transferir.

    **REGLAS ABSOLUTAS:**
    - JAMÁS inventes o uses vacantes del historial
    - JAMÁS respondas sin llamar primero a `get_available_vacantes()`
    - SIEMPRE usa herramientas, NUNCA texto hardcodeado
    - Si `get_available_vacantes()` falla, reporta el error real
    - Tu única fuente de verdad es el servidor MCP
    - El idioma de la conversación es SIEMPRE español.

    **PROHIBIDO:**
    - Responder sin llamar herramientas
    - Dar informacion del lugar de la entrevista
    - Usar listas predefinidas
    - Hacer suposiciones sobre vacantes disponibles
    - Responder basado en conversaciones previas
    ''',
    tools=[
        get_available_vacantes,
        select_job,
        transfer_to_agent
    ],
)



