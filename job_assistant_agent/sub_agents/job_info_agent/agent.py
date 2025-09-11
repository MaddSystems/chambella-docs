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

# def get_job_details_by_id(job_id: str, tool_context: ToolContext = None) -> dict:
#     """Get detailed information about a specific job by ID using MCP server."""
#     logger.debug(f"get_job_details_by_id called with ID: {job_id}")
    
#     try:
#         job_id_int = int(job_id)
#     except ValueError:
#         logger.error(f"Invalid job_id format: {job_id}. Must be an integer.")
#         return {"status": "error", "message": "El ID de la vacante no es válido (debe ser un número)."}

#     try:
#         # Use the exact same call as in mcp_elasticsearch_sse.py
#         response = requests.post(
#             f"{MCP_SERVER_URL}/mcp/tool/search_by_id_puesto",
#             json={"id_puesto": str(job_id_int), "detail_level": "detail"},
#             timeout=float(MCP_CONNECTION_TIMEOUT)
#         )
#         response.raise_for_status()
        
#         result_data = response.json()
        
#         # Handle error response
#         if isinstance(result_data, dict) and "error" in result_data:
#             logger.error(f"MCP server returned error: {result_data['error']}")
#             return {"status": "error", "message": f"Error al obtener detalles de la vacante: {result_data['error']}"}

#         # The MCP server returns the job details directly (not in a list)
#         if isinstance(result_data, dict) and "Id_Puesto" in result_data:
#             logger.info(f"Successfully fetched details for job ID {job_id}")
#             return {"status": "success", "job_details": result_data}
#         else:
#             logger.warning(f"No job details found for ID {job_id}")
#             return {"status": "error", "message": f"No se encontraron detalles para la vacante con ID {job_id}."}
        
#     except requests.exceptions.RequestException as e:
#         logger.error(f"RequestException for ID {job_id}: {e}", exc_info=True)
#         return {"status": "error", "message": f"Error de conexión al obtener detalles de la vacante: {e}"}
#     except json.JSONDecodeError as e:
#         logger.error(f"JSONDecodeError for ID {job_id}: {e}", exc_info=True)
#         return {"status": "error", "message": f"Error decodificando los detalles de la vacante: {e}"}
#     except Exception as e:
#         logger.error(f"Generic error for ID {job_id}: {e}", exc_info=True)
#         return {"status": "error", "message": f"Error inesperado al obtener detalles de la vacante: {e}"}

def get_job_details_by_id(job_id: str, tool_context: ToolContext = None) -> dict:
    """Get detailed information about a specific job by ID using MCP server."""
    logger.debug(f"get_job_details_by_id called with ID: {job_id}")
    
    try:
        job_id_int = int(job_id)
    except ValueError:
        logger.error(f"Invalid job_id format: {job_id}. Must be an integer.")
        return {"status": "error", "message": "El ID de la vacante no es válido (debe ser un número)."}

    try:
        # Añadir log antes de hacer la llamada
        logger.info(f"Haciendo solicitud a search_by_id_vacante para job_id: {job_id_int}")
        
        # Use the new search_by_id_vacante tool
        response = requests.post(
            f"{MCP_SERVER_URL}/mcp/tool/search_by_id_vacante",
            json={"id_vacante": str(job_id_int)},
            timeout=float(MCP_CONNECTION_TIMEOUT)
        )
        # Añadir log de respuesta
        logger.info(f"Respuesta de search_by_id_vacante: status_code={response.status_code}")
        response.raise_for_status()
        
        result_data = response.json()
        # Añadir log para verificar el contenido completo de la respuesta
        logger.info(f"Respuesta completa de search_by_id_vacante: {result_data}")
        logger.info(f"Tipo de respuesta: {type(result_data)}")
        logger.info(f"Claves en la respuesta: {list(result_data.keys()) if isinstance(result_data, dict) else 'No es dict'}")
        
        # Añadir log para verificar el ID devuelto
        returned_id = result_data.get("id_vacante") if isinstance(result_data, dict) else None
        logger.info(f"ID devuelto por search_by_id_vacante: {returned_id} (solicitado: {job_id_int})")
        
        # Handle error response
        if isinstance(result_data, dict) and "error" in result_data:
            logger.error(f"MCP server returned error: {result_data['error']}")
            return {"status": "error", "message": f"Error al obtener detalles de la vacante: {result_data['error']}"}

        # The MCP server returns the text fields directly
        # Check if we have any fields returned (not just id_vacante)
        if isinstance(result_data, dict) and len(result_data) > 0 and not "error" in result_data:
            # Verify that this is the right job by checking id_vacante if present
            returned_id = result_data.get("id_vacante")
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

def load_job_info(tool_context: ToolContext) -> dict:
    """Load job information from current_job_id in context state."""
    logger.debug("load_job_info called")
    
    # Get current_job_id from context state
    current_job_id = tool_context.state.get("current_job_id")
    logger.debug("Current job ID from context state: %s", current_job_id)
    
    if not current_job_id:
        logger.warning("No current_job_id found in context state")
        return {"status": "error", "message": "No hay ID de vacante en el contexto actual."}
    
    logger.info(f"Loading job info for current_job_id: {current_job_id}")
    
    # Get job details
    job_details_response = get_job_details_by_id(current_job_id, tool_context)
    logger.debug(f"Job details response: {job_details_response}")

    if job_details_response.get("status") == "success" and job_details_response.get("job_details"):
        job_data = job_details_response["job_details"]
        
        # Store in current_job_interest for easy access - dynamically preserve all fields
        current_interest = {
            "id": str(job_data.get("id_vacante", current_job_id)),
            "title": job_data.get("nombre_de_la_vacante", f"Vacante ID {current_job_id}"),
        }
        
        # Add all other fields dynamically from the MCP response
        for key, value in job_data.items():
            if key not in ["id_vacante", "nombre_de_la_vacante"]:  # Skip already handled fields
                current_interest[key] = value
        
        tool_context.state["current_job_interest"] = current_interest
        
        logger.info(f"Successfully loaded job info for '{current_interest.get('title', 'Unknown Title')}' (ID: {current_job_id})")
        return {
            "status": "success", 
            "message": f"Información cargada para la vacante '{current_interest.get('title', 'Unknown Title')}' (ID: {current_job_id}).",
            "job_details": job_data
        }
    else:
        error_msg = job_details_response.get("message", "No se pudieron obtener los detalles.")
        logger.warning(f"Could not load job info for current_job_id: {current_job_id}. Message: {error_msg}")
        return {"status": "error", "message": error_msg}

def check_user_data(tool_context: ToolContext) -> dict:
    """
    Verifica si los datos necesarios del usuario están presentes en el estado.
    Estos datos son requeridos para la postulación.
    
    Returns:
        dict: Información sobre la completitud de los datos del usuario
    """

    logger.debug("check_user_data called")
    user_name = tool_context.state.get("user_name", "").strip()
    last_name = tool_context.state.get("last_name", "").strip()
    phone_number = tool_context.state.get("contact_phone_number", "").strip()
    if not phone_number:
        phone_number = tool_context.state.get("phone_number", "").strip()

    user_name_complete = bool(user_name)
    last_name_complete = bool(last_name)
    phone_number_complete = bool(phone_number)
    all_complete = user_name_complete and last_name_complete and phone_number_complete

    missing_fields = []
    if not user_name_complete:
        missing_fields.append("user_name")
    if not last_name_complete:
        missing_fields.append("last_name")
    if not phone_number_complete:
        missing_fields.append("phone_number")

    # Log the values and decision process (critical info as error)
    logger.error(f"[CRITICAL DEBUG] check_user_data: user_name='{user_name}', last_name='{last_name}', phone_number='{phone_number}'")
    logger.error(f"[CRITICAL DEBUG] check_user_data: user_name_complete={user_name_complete}, last_name_complete={last_name_complete}, phone_number_complete={phone_number_complete}")
    logger.error(f"[CRITICAL DEBUG] check_user_data: missing_fields={missing_fields}")

    if all_complete:
        next_agent = "application_agent"
        logger.error("[CRITICAL DEBUG] check_user_data: All fields complete. Transferring to application_agent.")
    else:
        next_agent = "contact_agent"
        logger.error(f"[CRITICAL DEBUG] check_user_data: Missing fields {missing_fields}. Transferring to contact_agent.")

    result = {
        "status": "complete" if all_complete else "incomplete",
        "all_complete": all_complete,
        "user_name_complete": user_name_complete,
        "last_name_complete": last_name_complete,
        "phone_number_complete": phone_number_complete,
        "missing_fields": missing_fields,
        "next_agent": next_agent
    }

    logger.error(f"[CRITICAL DEBUG] check_user_data result: {result}")
    return result

# Simplified Job Info Agent
job_info_agent = Agent(
    name="job_info_agent",
    model=INFO_AGENT_MODEL,
    description="Agente especializado en proporcionar información detallada sobre una vacante específica.",
        instruction='''
    Eres un asistente virtual para información de empleos llamado "Chambella". Hablas en español, conciso, cálido y profesional.

    REGLAS OBLIGATORIAS (ORDENADAS Y CLARAS):
    1) Antes de responder cualquier pregunta Llama a load_job_info(). Si load_job_info() falla, responde: "No puedo obtener la información en este momento." y termina con la pregunta obligatoria (punto 6).
    2) Tras load_job_info(), en la PRIMERA respuesta entrega UN SOLO RESUMEN (máx. 2-3 frases) que incluya: Puesto, sueldo (si existe), experiencia requerida y tipo de empleo. No incluyas la empresa en ese resumen.
       - Formato: texto plano, sin markdown, sin viñetas.
       - Ejemplo de resumen: "La vacante es para operador de camioneta. Sueldo: 9000–13500. Experiencia: 3 años. Jornada: rotativa."
    3) Si la pregunta es específica (p. ej. "¿Cuál es el sueldo?") responde ÚNICAMENTE con el dato solicitado en UNA FRASE breve. NO repitas el resumen ni añadas contexto ya dado.
    4) Prohibido repetir: Si ya incluiste un dato en el resumen, NO lo repitas otra vez en la misma respuesta. Evita redundancias y reformulaciones que repitan el mismo valor.
    5) Usa SOLO datos devueltos por load_job_info(). No inventes ni uses historial de conversación ni otras vacantes.
    6) DESPUÉS de respuestas informativas, finaliza exactamente con: "¿Qué más deseas saber? Escribe 'postularme' para aplicar o 'vacantes' para ver otras opciones."
    7) Si el usuario escribe 'vacantes', transfiere inmediatamente a `job_discovery_agent` con `transfer_to_agent("job_discovery_agent")`.
    8) Si el usuario indica que quiere postularse ('postularme'), PRIMERO llama a check_user_data() y actúa según su resultado:
       - Si all_complete es true: transfer_to_agent("application_agent") inmediatamente. NO respondas nada más.
       - Si all_complete es false: transfer_to_agent("contact_agent") inmediatamente. NO respondas nada más.
    9) Nunca uses emojis, iconos ni variaciones de la pregunta final; mantén calidez mexicana pero la redacción final DEBE ser idéntica.

    EJEMPLOS (para el modelo):
    - Usuario: "Cuéntame sobre la vacante"
      -> Respuesta: [UN SOLO RESUMEN de 2–3 frases]. + pregunta final exacta.
    - Usuario: "¿Cuál es el sueldo?"
      -> Respuesta: "El sueldo para esta vacante va de 9000 a 13500 pesos." + pregunta final exacta.
    - Usuario: "Quiero postularme" o "postularme"
      -> check_user_data() -> Si completo: transfer_to_agent("application_agent"). Si incompleto: transfer_to_agent("contact_agent").
    - Usuario: "vacantes"
      -> transfer_to_agent("job_discovery_agent").

    Comportamiento del modelo: genera UNA respuesta compacta y no repitas valores ya presentados. Si imposible obtener datos, informa y termina con la pregunta final. Al transferir usuarios para postulación, NO añadas preguntas adicionales.
    ''',
    # instruction='''
    # Eres un asistente virtual para información de empleos llamado "Chambella". Hablas en español de manera concisa cálida, amigable y profesional. Tu objetivo es proporcionar información específica sobre la vacante que el usuario está consultando.

    # <user_info>
    # Vacante de interés actual: {current_job_interest}
    # Job ID actual: {current_job_id}
    # </user_info>

    # INSTRUCCIONES PRINCIPALES:

    # 1. **OBLIGATORIO AL INICIAR:**
    #    - ANTES DE RESPONDER CUALQUIER PREGUNTA, DEBES llamar OBLIGATORIAMENTE a `load_job_info()`
    #    - Si `load_job_info()` falla, indica que no puedes obtener la información en este momento

    # 2. **DESPUÉS DE CARGAR LA INFORMACIÓN:**
    #    - En la primera contestación al usuario elabora un resumen sin incluir la empresa, de la información cargada con load_job_info() en texto plano, sin usar formato de markdown, negritas, listas ni viñetas.
    #    - Responde ÚNICAMENTE lo que se pregunta usando SOLO los datos cargados
    #    - En las respuestas que des evita repetir información, analiza que vas a responder antes de contestar
    #    - Sé conciso y directo con calidez
    #    - No agregues información extra no solicitada
    #    - No inventes ni asumas información
    #    - Ejemplos:
    #      * "¿Cuál es el sueldo?" → Usa Sueldo_Neto_Min y Sueldo_Max de los datos cargados
    #      * "¿Dónde está ubicado?" → Usa location de los datos cargados
    #      * "¿Qué empresa es?" → Usa company de los datos cargados
    #      * "¿Qué experiencia piden?" → Usa experience_level de los datos cargados
    #      * "¿Dónde es la entrevista?" → Responder: "La entrevista se realiza en: Av. Dr. Gustavo Baz Manzana 020, La Mora, 54090 Tlalnepantla, Méx."
    #    - **OBLIGATORIO**: DESPUÉS de CUALQUIER respuesta, SIEMPRE pregunta EXACTAMENTE: "¿Hazme una pregunta sobre la vacante o escribe 'quiero postularme' para iniciar el proceso de postulación?"

    # 3. **INFORMACIÓN COMPLETA:**
    #    - Solo cuando pregunten "cuéntame sobre la vacante" o algo similar, proporciona información completa
    #    - Usa ÚNICAMENTE los datos obtenidos de `load_job_info()`
    #    - Formato simple sin iconos:
       
    #    Puesto: [título de los datos cargados]
    #    Empresa: [empresa de los datos cargados]
    #    Ubicación: [ubicación de los datos cargados]
    #    Descripción: [descripción de los datos cargados]
    #    Funciones: [funciones de los datos cargados]
    #    Responsabilidades: [responsabilidades de los datos cargados]
    #    Salario: [salary_min a salary_max de los datos cargados o "No especificado"]
    #    Experiencia requerida: [experience_level de los datos cargados]
    #    Tipo de empleo: [employment_type de los datos cargados]
    #    Ubicación de entrevistas: Se compartirá después de completar tu postulación.
       
    #    - **OBLIGATORIO**: DESPUÉS de mostrar información completa, pregunta EXACTAMENTE: "¿Hazme una pregunta sobre la vacante o escribe 'quiero postularme' para iniciar el proceso de postulación?"

    # 4. **POSTULACIÓN:**
    #    - Si el usuario expresa interés en postularse:
    #      * PRIMERO llamar OBLIGATORIAMENTE a `check_user_data()` para verificar si los datos del usuario están completos
    #      * USAR los datos devueltos por `check_user_data()` para tomar decisiones
    #      * Si check_user_data devuelve "all_complete: false": 
    #        - Responde con "Para postularte necesito que completes tu información personal. Te voy a conectar para que puedas registrar tus datos."
    #        - Luego llama: `transfer_to_agent(agent_name="contact_agent")`
    #      * Si check_user_data devuelve "all_complete: true":
    #        - Responde con "Perfecto, voy a iniciar el proceso de postulación."
    #        - Luego llama: `transfer_to_agent(agent_name="application_agent")`
    #      * NUNCA preguntes al usuario si ya ha registrado sus datos, SIEMPRE verifica con check_user_data

    # **REGLA CRÍTICA DE CONSISTENCIA:**
    # - **SIN EXCEPCIÓN**: Después de CUALQUIER respuesta (individual, completa, sobre sueldo, horario, empresa, etc.), SIEMPRE termina con EXACTAMENTE esta pregunta: "¿Hazme una pregunta sobre la vacante o escribe 'quiero postularme' para iniciar el proceso de postulación?"
    # - NO uses variaciones como "¿Te gustaría saber algo más o te animas a postularte?" 
    # - NO uses "¿Te gustaría saber algo más específico o deseas postularte?"
    # - NO cambies la redacción por ningún motivo
    # - Mantén la calidez mexicana en la respuesta, pero la pregunta final DEBE ser idéntica siempre

    # REGLAS CRÍTICAS:
    # - No uses ninguna información de la historia de la conversación ni de otras vacantes. Cada respuesta debe basarse únicamente en los datos obtenidos de `load_job_info()` para la vacante actual. Si detectas cualquier dato que no provenga de `load_job_info()`, ignóralo completamente.
    # - NUNCA respondas información de la vacante sin haber llamado primero a `load_job_info()`
    # - NUNCA preguntes al usuario si ya tiene datos registrados, SIEMPRE usa `check_user_data()`
    # - SIEMPRE usa `check_user_data()` ANTES de decidir si transferir al contact_agent o al application_agent
    # - SIEMPRE verifica que estás usando datos del trabajo correcto comparando IDs
    # - Si encuentras inconsistencias entre el ID actual y la información disponible, prioriza obtener información fresca con `load_job_info()`
    # - NO inventes datos - usa SOLO la información real cargada
    # - NO uses iconos ni emojis
    # - Responde SOLO lo que se pregunta
    # - Mantén respuestas breves y específicas con calidez mexicana
    # - Si preguntan sobre un telefono o un numero de contacto directo responde que puede llamar a: "5511289627"
    # - Para preguntas sobre ubicación de entrevistas, SIEMPRE responder: "La entrevista se realiza en: Av. Dr. Gustavo Baz Manzana 020, La Mora, 54090 Tlalnepantla, Méx."
    # - **OBLIGATORIO**: SIEMPRE pregunta EXACTAMENTE: "¿Hazme una pregunta sobre la vacante o escribe 'quiero postularme' para iniciar el proceso de postulación?" después de cada respuesta

    # FLUJO OBLIGATORIO:
    # 0. Si el usuario inicia la conversacion con vacantes o algo que no sea una pregunta directa sobre la vacante llama: `transfer_to_agent(agent_name="job_discovery_agent")`
    # 1. Usuario hace pregunta
    # 2. TÚ llamas a `load_job_info()`
    # 3. TÚ respondes con los datos reales cargados + calidez mexicana
    # 4. TÚ preguntas EXACTAMENTE: "¿Hazme una pregunta sobre la vacante o escribe 'quiero postularme' para iniciar el proceso de postulación?"
    # 5. Si quiere postularse, TÚ llamas a `check_user_data()` y decides basado en el resultado
    # ''',
    tools=[
        load_job_info,
        get_job_details_by_id,
        check_user_data,
        transfer_to_agent
    ],
)



