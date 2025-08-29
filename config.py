import os
from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm
import litellm

# Load environment variables
load_dotenv(override=True)

# LiteLLM Configuration
LITELLM_PROXY_API_KEY = os.getenv("LITELLM_PROXY_API_KEY", "sk-122103")
LITELLM_PROXY_API_BASE = os.getenv("LITELLM_PROXY_API_BASE", "https://litellm.armaddia.lat")
LITELLM_MODEL = os.getenv("LITELLM_MODEL", "gemini/gemini-2.0-flash")

# Set up environment for LiteLLM proxy
os.environ["LITELLM_PROXY_API_KEY"] = LITELLM_PROXY_API_KEY
os.environ["LITELLM_PROXY_API_BASE"] = LITELLM_PROXY_API_BASE

# Configure LiteLLM to use proxy
litellm.use_litellm_proxy = True

# Model configuration - all agents will use LiteLLM for cost tracking
DEFAULT_MODEL = os.getenv("AGENT_MODEL")

# LiteLLM model instances for cost tracking
MAIN_AGENT_MODEL = LiteLlm(model=LITELLM_MODEL)
SUB_AGENT_MODEL = LiteLlm(model=LITELLM_MODEL)
INFO_AGENT_MODEL = LiteLlm(model=LITELLM_MODEL)
APPLICATION_AGENT_MODEL = LiteLlm(model=LITELLM_MODEL)
FAQ_AGENT_MODEL = LiteLlm(model=LITELLM_MODEL)
FOLLOW_UP_AGENT_MODEL = LiteLlm(model=LITELLM_MODEL)
CONTACT_AGENT_MODEL = LiteLlm(model=LITELLM_MODEL)

# Logging
import logging
logger = logging.getLogger(__name__)
logger.info(f"LiteLLM configuration loaded: {LITELLM_MODEL} via {LITELLM_PROXY_API_BASE}")
logger.info(f"All agents will use LiteLLM for cost tracking")
