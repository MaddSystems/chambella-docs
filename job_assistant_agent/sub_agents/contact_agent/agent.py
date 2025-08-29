from google.adk.agents import Agent
from google.adk.tools import FunctionTool, ToolContext, transfer_to_agent
import logging
import os
from dotenv import load_dotenv

# Import centralized config  
from config import CONTACT_AGENT_MODEL

# Construct path to the parent directory's .env file
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path, override=True)

# Configure logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def check_current_state(tool_context: ToolContext) -> dict:
    """
    Checks the current state to see what contact information is missing.

    Args:
        tool_context (ToolContext): The context for accessing state.
    """
    logger.info("check_current_state called")
    
    user_name = tool_context.state.get('user_name', '').strip()
    last_name = tool_context.state.get('last_name', '').strip()
    # Priorizar contact_phone_number y caer en phone_number como respaldo (solo para WhatsApp)
    phone_number = tool_context.state.get('contact_phone_number', '').strip()
    if not phone_number and tool_context.state.get('channel') == 'whatsapp':
        phone_number = tool_context.state.get('phone_number', '').strip()
    
    # Split user_name to get first name if it contains both
    first_name = user_name.split()[0] if user_name else ''
    
    missing_fields = []
    if not first_name:
        missing_fields.append('nombre')
    if not last_name:
        missing_fields.append('apellido')
    if not phone_number:
        missing_fields.append('telefono')
    
    state_info = {
        "user_name": user_name,
        "first_name": first_name,
        "last_name": last_name,
        "phone_number": phone_number,
        "missing_fields": missing_fields,
        "is_complete": len(missing_fields) == 0
    }
    
    logger.info(f"Current state check: {state_info}")
    return state_info

def update_contact_info(nombre: str, apellido: str, telefono: str, tool_context: ToolContext) -> dict:
    """
    Updates the user's contact information in the state.

    Args:
        nombre (str): The first name of the user.
        apellido (str): The last name of the user.
        telefono (str): The phone number of the user.
        tool_context (ToolContext): The context for accessing state.
    """
    logger.info(f"update_contact_info called with nombre='{nombre}', apellido='{apellido}', telefono='{telefono}'")
    logger.info(f"State before update: user_name={tool_context.state.get('user_name', 'Not set')}, last_name={tool_context.state.get('last_name', 'Not set')}, phone_number={tool_context.state.get('phone_number', 'Not set')}")

    # Validar solo nombre, apellido y teléfono como obligatorios
    if not nombre or not apellido or not telefono:
        logger.warning(f"update_contact_info validation failed: Missing required fields: nombre='{nombre}', apellido='{apellido}', telefono='{telefono}'")
        return {"status": "error", "message": "El nombre, apellido y teléfono son obligatorios."}

    if not telefono.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "").isdigit():
        logger.warning(f"update_contact_info validation failed: Invalid phone format: '{telefono}'")
        return {"status": "error", "message": "El número de teléfono debe contener solo números, espacios, guiones, paréntesis o el símbolo +."}

    tool_context.state["user_name"] = f"{nombre} {apellido}"
    tool_context.state["last_name"] = apellido
    tool_context.state["contact_phone_number"] = telefono  # Guardar siempre en contact_phone_number
    
    # Si el canal es whatsapp, también actualizamos phone_number
    if tool_context.state.get("channel") == "whatsapp":
        tool_context.state["phone_number"] = telefono

    logger.info(f"State after update: user_name={tool_context.state.get('user_name')}, last_name={tool_context.state.get('last_name')}, phone_number={tool_context.state.get('phone_number')}")

    current_interaction_history = tool_context.state.get("interaction_history", [])
    new_interaction_history = current_interaction_history.copy()
    new_interaction_history.append({
        "action": "update_contact_info",
        "nombre": nombre,
        "apellido": apellido,
        "telefono": telefono
    })
    tool_context.state["interaction_history"] = new_interaction_history

    logger.info(f"Verifying top-level fields: user_name={tool_context.state.get('user_name')}, last_name={tool_context.state.get('last_name')}, phone_number={tool_context.state.get('phone_number')}")

    if (tool_context.state.get("user_name") != f"{nombre} {apellido}" or
        tool_context.state.get("last_name") != apellido or
        tool_context.state.get("phone_number") != telefono):
        logger.error("State persistence verification failed! State doesn't contain expected values after update.")
    else:
        logger.info("State persistence verification successful.")

    return {
        "status": "success",
        "message": f"¡Información de contacto actualizada correctamente!",
        "user_name": f"{nombre} {apellido}",
        "last_name": apellido,
        "phone_number": telefono,
        "should_transfer": True  # Indicador para transferir al application_agent
    }

# Welcome Agent
contact_agent = Agent(
    name="contact_agent",
    model=CONTACT_AGENT_MODEL,
    description="gente especializado en recopilar información de contacto del usuario antes de postularse a vacantes.",
    instruction='''
    Eres un agente especializado ÚNICAMENTE en recopilar información de contacto del usuario. Tu única misión es completar estos 3 campos en el estado:
    - user_name (nombre completo)
    - last_name (apellido)  
    - phone_number (número de teléfono)

    **REGLA FUNDAMENTAL:** 
    - PRIMERO: Usa `check_current_state()` para verificar qué información ya tienes y qué te falta.
    - Si tienes toda la información completa, TRANSFIERE INMEDIATAMENTE al usuario al application_agent.
    - Si el usuario pregunta CUALQUIER COSA que no sea proporcionar datos de contacto, pasa a responder sus inquietudes sin mencionar cambios de agente.

    <user_info>
    Nombre completo: {user_name}
    Información de contacto:
      Apellido: {last_name}
      Teléfono: {phone_number}
    </user_info>

    <interaction_history>
    {interaction_history}
    </interaction_history>

    **PROCESO INTELIGENTE DE RECOLECCIÓN:**

    1. **Al iniciar cualquier interacción**:
       - Llama `check_current_state()` para ver qué información ya tienes
       - Si `is_complete` es true → TRANSFIERE INMEDIATAMENTE al usuario usando `transfer_to_agent(agent_name="application_agent")`
       - Si hay `missing_fields` → solicita solo los datos faltantes

    2. **Solicitud inteligente basada en campos faltantes**:
       - Si falta "nombre" → "Para poder postularte necesito tu nombre (sin apellido)."
       - Si falta "apellido" → "¿Cuál es tu apellido?"
       - Si falta "telefono" → "¿Cuál es tu número de teléfono?"
       - Si faltan múltiples → pide uno por uno en orden: nombre → apellido → teléfono

    3. **Uso de herramientas**:
       - `check_current_state()` → SIEMPRE al inicio para evaluar el estado actual
       - `update_contact_info(nombre, apellido, telefono)` → SOLO cuando tengas TODOS los 3 datos completos

    4. **Flujo optimizado**:
       - Verifica estado actual con `check_current_state()`
       - Recolecta solo los datos faltantes uno por uno
       - Solo cuando tengas los 3 datos → llama `update_contact_info` con todos los parámetros
       - Después de actualizar → llama INMEDIATAMENTE `transfer_to_agent(agent_name="application_agent")`

    **POSTERIOR A LA ACTUALIZACIÓN DE DATOS:**
    - Una vez que `update_contact_info` retorne éxito, NO hagas ninguna pregunta adicional
    - NO solicites fechas u horas para entrevistas
    - NO preguntes sobre preferencias de horarios
    - Responde con "¡Gracias por proporcionar tu información! Te transferiré para continuar con el proceso de postulación."
    - DESPUÉS usa `transfer_to_agent(agent_name="application_agent")` INMEDIATAMENTE

    **REGLAS CRÍTICAS:**
    - NUNCA preguntes sobre fechas u horarios para entrevistas
    - NUNCA preguntes "¿Cuándo estarías disponible?"
    - NUNCA preguntes "¿Qué día te gustaría programar tu entrevista?"
    - TRANSFIERE al usuario tan pronto como tengas los 3 datos (nombre, apellido y teléfono)
    - La programación de entrevistas es responsabilidad EXCLUSIVA del application_agent
    ''',
    tools=[
        FunctionTool(check_current_state),
        FunctionTool(update_contact_info),
        transfer_to_agent
    ]
)