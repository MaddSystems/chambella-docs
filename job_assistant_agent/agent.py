from google.adk.agents import Agent
import os
from dotenv import load_dotenv
from datetime import datetime
import logging

# Load environment variables from .env file in the current directory
load_dotenv(override=True)

# Import centralized config
from config import MAIN_AGENT_MODEL

from .sub_agents.contact_agent.agent import contact_agent
from .sub_agents.job_info_agent.agent import job_info_agent
from .sub_agents.application_agent.agent import application_agent
from .sub_agents.follow_up_agent.agent import follow_up_agent
from .sub_agents.faq_agent.agent import faq_agent
from .sub_agents.job_discovery_agent.agent import job_discovery_agent
from google.adk.tools.tool_context import ToolContext
from google.adk.tools import transfer_to_agent, FunctionTool

# Configure logging
logger = logging.getLogger(__name__)

# Get the current date to pass to the agent's instructions
current_date_str = datetime.now().strftime("%Y-%m-%d")

def start_job_discovery(tool_context: ToolContext):
    """
    Clears the interaction history and transfers to the job_discovery_agent 
    to start a fresh job search conversation.
    """
    logger.info("🧹 start_job_discovery called - clearing interaction history for fresh job discovery")
    
    # Clear the interaction history to ensure fresh job discovery responses
    tool_context.state["interaction_history"] = []
    
    logger.info("✅ Interaction history cleared, transferring to job_discovery_agent")
    
    # Transfer to the job_discovery_agent
    transfer_to_agent(agent_name="job_discovery_agent", tool_context=tool_context)


def handle_job_query(tool_context: ToolContext) -> dict:
    """
    Analyzes the current state and determines whether to go to job_discovery_agent 
    or job_info_agent based on the user's job context.
    """
    logger.info("🔍 handle_job_query called - analyzing job context")
    
    current_job_id = tool_context.state.get("current_job_id")
    current_ad_id = tool_context.state.get("current_ad_id")
    current_job_title = tool_context.state.get("current_job_title")
    
    logger.info(f"State analysis: job_id={current_job_id}, ad_id={current_ad_id}, job_title={current_job_title}")
    
    # If no job context, go to job discovery
    if not current_job_id:
        logger.info("🔄 No current job ID - going to job_discovery_agent")
        # Clear interaction history for fresh job discovery
        tool_context.state["interaction_history"] = []
        transfer_to_agent(agent_name="job_discovery_agent", tool_context=tool_context)
        return {"status": "transferred", "target": "job_discovery_agent", "reason": "no_job_id"}
    
    # If has job context, go to job info
    else:
        logger.info(f"📋 Has job context (ID: {current_job_id}) - going to job_info_agent")
        transfer_to_agent(agent_name="job_info_agent", tool_context=tool_context)
        return {"status": "transferred", "target": "job_info_agent", "reason": "has_job_context"}


def handle_interview_date_check(tool_context: ToolContext) -> dict:
    """
    Checks if interview date has expired and determines appropriate agent transfer.
    """
    logger.info("📅 handle_interview_date_check called")
    
    current_day_interview = tool_context.state.get("current_day_interview", "")
    current_ad_id = tool_context.state.get("current_ad_id")
    current_job_id = tool_context.state.get("current_job_id")
    
    logger.info(f"Interview date check: interview_date={current_day_interview}, ad_id={current_ad_id}, job_id={current_job_id}")
    
    if not current_day_interview:
        logger.info("⚠️ No interview date set")
        return {"status": "no_interview_date"}
    
    try:
        from datetime import datetime
        interview_date = datetime.strptime(current_day_interview, "%Y-%m-%d").date()
        today = datetime.now().date()
        
        # Interview date is future or today - go to follow_up
        if interview_date >= today:
            logger.info(f"⏰ Interview date {interview_date} is upcoming - going to follow_up_agent")
            transfer_to_agent(agent_name="follow_up_agent", tool_context=tool_context)
            return {"status": "transferred", "target": "follow_up_agent", "reason": "upcoming_interview"}
        
        # Interview date has expired
        else:
            logger.info(f"⏰ Interview date {interview_date} has expired")
            
            # If no ad_id, go to job discovery
            if not current_ad_id:
                logger.info("🔄 No ad_id - going to job_discovery_agent")
                tool_context.state["interaction_history"] = []
                transfer_to_agent(agent_name="job_discovery_agent", tool_context=tool_context)
                return {"status": "transferred", "target": "job_discovery_agent", "reason": "expired_interview_no_ad"}
            
            # If has ad_id, go to job info
            else:
                logger.info(f"📋 Has ad_id ({current_ad_id}) - going to job_info_agent")
                transfer_to_agent(agent_name="job_info_agent", tool_context=tool_context)
                return {"status": "transferred", "target": "job_info_agent", "reason": "expired_interview_has_ad"}
                
    except (ValueError, TypeError) as e:
        logger.error(f"❌ Error parsing interview date '{current_day_interview}': {e}")
        return {"status": "error", "message": f"Error parsing date: {e}"}


def handle_greeting(tool_context: ToolContext) -> dict:
    """
    Handles user greetings based on their current job context.
    """
    logger.info("👋 handle_greeting called")
    
    current_job_id = tool_context.state.get("current_job_id")
    current_job_title = tool_context.state.get("current_job_title")
    
    logger.info(f"Greeting context: job_id={current_job_id}, job_title={current_job_title}")
    
    # If no job context, start job discovery
    if not current_job_id:
        logger.info("🔄 No job context - starting job discovery")
        tool_context.state["interaction_history"] = []
        transfer_to_agent(agent_name="job_discovery_agent", tool_context=tool_context)
        return {"status": "transferred", "target": "job_discovery_agent", "reason": "greeting_no_job"}
    
    # If has job context, respond with job-specific greeting
    else:
        logger.info(f"📋 Has job context - responding with job-specific greeting")
        return {
            "status": "respond", 
            "message": f"¡Hola! Hazme una pregunta relativa a la vacante {current_job_title} o sobre cómo opera el servicio TOP (Tu oferta profesional)."
        }

# Root Agent: Job Placement Assistant
job_assistant_agent = Agent(
    name="job_assistant",
    model=MAIN_AGENT_MODEL,
    description="Agente de servicio para apoyar a usuarios en encontrar trabajo con TOP (Tu oferta profesional).",
    instruction=f"""
Eres el agente principal de servicio al cliente para el sistema de postulación de empleos de TOP (Tu oferta profesional).
La fecha actual es: {current_date_str}.

**INFORMACIÓN DEL ESTADO ACTUAL:**
<user_info>
Nombre completo: {{user_name}}
Apellido: {{last_name}}
Teléfono: {{contact_phone_number}}
Job ID actual: {{current_job_id}}
Título del trabajo: {{current_job_title}}
Postulaciones realizadas: {{applied_jobs}}
Fecha de entrevista: {{current_day_interview}}
Ad ID actual: {{current_ad_id}}
</user_info>


**VERIFICACIÓN OBLIGATORIA PRIMERO (LÓGICA DE ENTREVISTA Y POSTULACIÓN):**

**REGLA PRINCIPAL DE ESTADO:**
- **SIEMPRE** usa la herramienta `handle_interview_date_check` para verificar lógica de entrevistas
- **SIEMPRE** usa la herramienta `handle_greeting` para saludos
- **SIEMPRE** usa la herramienta `handle_job_query` para consultas sobre trabajos/vacantes/empleos

**NUNCA hagas transferencias directas a job_discovery_agent o job_info_agent. SIEMPRE usa las herramientas.**

**REGLAS DE ROUTING:**

1. **PARA SALUDOS SIMPLES:**
   - "hola", "buenos días", etc. → INMEDIATAMENTE usa la herramienta `handle_greeting`

2. **PARA CUALQUIER CONSULTA SOBRE TRABAJOS:**
   - "vacantes", "trabajos", "empleos" → INMEDIATAMENTE usa la herramienta `handle_job_query`
   - "¿cuál es el sueldo?" → INMEDIATAMENTE usa la herramienta `handle_job_query`
   - "información de la vacante" → INMEDIATAMENTE usa la herramienta `handle_job_query`
   - "requisitos del puesto" → INMEDIATAMENTE usa la herramienta `handle_job_query`
   - "horarios de trabajo" → INMEDIATAMENTE usa la herramienta `handle_job_query`
   - "empresa que solicita el trabajo" → INMEDIATAMENTE usa la herramienta `handle_job_query`
   - "ubicación donde se realiza el trabajo" → INMEDIATAMENTE usa la herramienta `handle_job_query`
   - CUALQUIER pregunta sobre trabajo → INMEDIATAMENTE usa la herramienta `handle_job_query`

3. **PARA CONSULTAS SOBRE ENTREVISTAS:**
   - Si {{current_day_interview}} tiene valor → INMEDIATAMENTE usa la herramienta `handle_interview_date_check`

4. **PARA CUALQUIER CONSULTA SOBRE EL SERVICIO:**
   - "¿Cómo funciona la plataforma?" → INMEDIATAMENTE transfer_to_agent("faq_agent")
   - "¿Es gratis el servicio?" → INMEDIATAMENTE transfer_to_agent("faq_agent")
   - "¿Cómo me postulo?" → INMEDIATAMENTE transfer_to_agent("faq_agent")
   - "¿Necesito CV?" → INMEDIATAMENTE transfer_to_agent("faq_agent")
   - "¿Cuánto tarda el proceso?" → INMEDIATAMENTE transfer_to_agent("faq_agent")

4. **PARA POSTULACIÓN:**
   - "Quiero postularme" → OBLIGATORIO verificar PRIMERO:
     * Si {{applied_jobs}} no está vacío:
       → RESPONDER: "Ya te has postulado a esta vacante. ¿Necesitas información sobre tu postulación?" → transfer_to_agent("follow_up_agent")
     * Si {{applied_jobs}} está vacío:
       - Verificar datos: Si {{user_name}} = '' O {{last_name}} = '' O {{contact_phone_number}} = ''
         → FALTAN DATOS → transfer_to_agent("contact_agent")
       - Si {{user_name}} ≠ '' Y {{last_name}} ≠ '' Y {{contact_phone_number}} ≠ ''
         → DATOS COMPLETOS → transfer_to_agent("application_agent")

**REGLAS CRÍTICAS:**
- NUNCA uses transfer_to_agent("job_discovery_agent") o transfer_to_agent("job_info_agent") directamente
- SIEMPRE usa las herramientas: `handle_job_query`, `handle_greeting`, `handle_interview_date_check`
- Las herramientas analizarán el estado automáticamente y harán la transferencia correcta
- SIEMPRE verificar {{applied_jobs}} está vacío ANTES de cualquier transferencia a application_agent
- Si {{applied_jobs}} no está vacío = PROHIBIDO ir a application_agent

**FLUJO SIMPLIFICADO:**
1. Usuario hace consulta → TÚ usas la herramienta apropiada
2. La herramienta analiza el estado y hace la transferencia
3. NO hagas transferencias directas a job_discovery_agent o job_info_agent

**Agentes especializados:**

1. **Job Discovery Agent** - Para encontrar nuevas vacantes (accesible vía herramientas)
2. **Job Info Agent** - Para información sobre vacantes específicas (accesible vía herramientas)
3. **Contact Agent** - Para recolección de datos de contacto
4. **Application Agent** - Para proceso de postulación
5. **FAQ Agent** - Para preguntas generales de la plataforma
6. **Follow Up Agent** - Para seguimiento de postulaciones y entrevistas

**HERRAMIENTAS DISPONIBLES:**
- `handle_greeting` - Maneja saludos según contexto del usuario
- `handle_job_query` - Decide entre job_discovery_agent y job_info_agent automáticamente
- `handle_interview_date_check` - Verifica fechas de entrevista y transfiere apropiadamente
- `start_job_discovery` - Inicia búsqueda de vacantes con historial limpio

RECUERDA: Usa las herramientas para decisiones de estado. NO hagas transferencias directas a job_discovery_agent o job_info_agent.
""",
    tools=[
        FunctionTool(start_job_discovery),
        FunctionTool(handle_job_query),
        FunctionTool(handle_interview_date_check),
        FunctionTool(handle_greeting),
        transfer_to_agent
    ],
    sub_agents=[
        follow_up_agent,
        contact_agent,
        job_info_agent,
        faq_agent,
        application_agent,
        job_discovery_agent
    ]
)