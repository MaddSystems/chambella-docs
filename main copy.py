# Import necessary libraries from all original files
import asyncio
import os
import json
from flask import Flask, request, jsonify, render_template, send_from_directory
import logging
from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from job_assistant_agent.agent import job_assistant_agent
from utils import add_user_query_to_history, call_agent_async, configure_llm_logging, parse_verbosity_args
from asgiref.wsgi import WsgiToAsgi
import uvicorn
import signal
import sys
import aiohttp  # Use aiohttp for async requests
import time
import sqlite3
import json
import random
from datetime import datetime
import pytz
import urllib.parse # ADDED: For parsing referral links

# Parse verbosity level from command line FIRST
VERBOSE_LEVEL = parse_verbosity_args()

# Load environment variables from .env and strip spaces if present
load_dotenv(override=True)
def get_env_var(key, default=None):
    value = os.getenv(key, default)
    if value is not None:
        value = value.strip()
    return value

# Set up logging configuration with parsed verbosity level
configure_llm_logging(VERBOSE_LEVEL)

# Configure logging
logging.basicConfig(
    #level=logging.INFO,
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ===== PART 1: Initialize Persistent Session Service =====
db_url = "sqlite:///./chambella_agent_data.db"
session_service = DatabaseSessionService(
    db_url=db_url,
)

# ===== PART 2: Initialize Runner & Agents =====
runner = Runner(
    agent=job_assistant_agent,
    app_name="Jobs Support",
    session_service=session_service,
)

# ===== PART 3: Define Initial State (Copied from main-messenger.py) =====
initial_state = {
    "user_name": "",
    "last_name": "",
    "email": "",
    "phone_number": "",  # Stores phone number for WhatsApp, sender.id for Messenger
    "contact_phone_number": "",  # Stores actual phone number for notifications regardless of channel
    "applied_jobs": [],
    "interaction_history": [],
    "current_job_interest": None,  # Stores referral.ref for Messenger
    "current_job_id": None,
    "current_ad_id":  None,
    "current_job_title": None,
    "current_search_step": None,
    "current_day_interview": "",
    "current_time_interview": "",
    "collected_criteria": {},
    "available_filter_options": None,
    "channel": None  # Tracks whether the message is from whatsapp or messenger
}


# ===== PART 4: Async Server Functions =====
app = Flask(__name__)

# Add this route to serve static files (like logos)
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

asgi_app = WsgiToAsgi(app)

# Environment variables for Meta APIs
VERIFY_TOKEN = get_env_var("VERIFY_TOKEN", "GPSc0ntr0l1")
MESSENGER_PAGE_ACCESS_TOKEN = get_env_var("MESSENGER_PAGE_ACCESS_TOKEN")
WHATSAPP_ACCESS_TOKEN = get_env_var("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = get_env_var("WHATSAPP_PHONE_NUMBER_ID")

# Telegram configuration for error alerts
TELEGRAM_BOT_TOKEN = get_env_var("TELEGRAM_BOT_TOKEN")
TELEGRAM_ERROR_CHAT_ID = get_env_var("TELEGRAM_ERROR_CHAT_ID")

# Delete session password
DELETE_PASSWORD = get_env_var("DELETE_PASSWORD", "GPSc0ntr0l1")

# Log environment variables on startup
# WARNING: Logging raw tokens can expose secrets in logs. Remove or mask in production.
logger.info(
    "Loaded environment variables:\n"
    f"VERIFY_TOKEN={VERIFY_TOKEN}\n"
    f"MESSENGER_PAGE_ACCESS_TOKEN={MESSENGER_PAGE_ACCESS_TOKEN}\n"
    f"\n"
    f"WHATSAPP_ACCESS_TOKEN={WHATSAPP_ACCESS_TOKEN}\n"
    f"WHATSAPP_PHONE_NUMBER_ID={WHATSAPP_PHONE_NUMBER_ID}\n"
    f"TELEGRAM_BOT_TOKEN={'***' if TELEGRAM_BOT_TOKEN else 'None'}\n"
    f"TELEGRAM_ERROR_CHAT_ID={TELEGRAM_ERROR_CHAT_ID}"
)


# Telegram error notification function
async def send_telegram_error_alert(phone_number: str, error_message: str, channel: str = "whatsapp") -> bool:
    """Send error alert to Telegram when WhatsApp/Messenger message fails."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ERROR_CHAT_ID:
        logger.warning("Telegram configuration not set. Cannot send error alert.")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        
        # Format the error message
        alert_message = (
            f"🚨 *ERROR EN CHAMBELLA*\n\n"
            f"*Canal:* {channel.upper()}\n"
            f"*Teléfono:* {phone_number}\n"
            f"*Error:* {error_message}\n"
            f"*Timestamp:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Por favor revisar la configuración del servidor."
        )
        
        payload = {
            'chat_id': TELEGRAM_ERROR_CHAT_ID,
            'text': alert_message,
            'parse_mode': 'Markdown'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=10) as response:
                response.raise_for_status()
                response_json = await response.json()
                logger.info(f"Telegram error alert sent successfully: {response_json}")
                return True
                
    except Exception as e:
        logger.error(f"Failed to send Telegram error alert: {e}")
        return False


# Unified message sending function
async def send_message_async(channel: str, recipient_id: str, message: str) -> bool:
    """Dispatches the message to the correct platform based on the channel."""
    if channel == 'whatsapp':
        return await send_whatsapp_message(recipient_id, message)
    elif channel == 'messenger':
        return await send_facebook_message(recipient_id, message)
    else:
        logger.error(f"Unsupported channel: {channel}")
        return False

# WhatsApp-specific message sending (Corrected with aiohttp)
async def send_whatsapp_message(recipient_id: str, message: str) -> bool:
    """Send a WhatsApp message using the WhatsApp Cloud API."""
    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        error_msg = "WhatsApp environment variables are not set."
        logger.error(error_msg)
        await send_telegram_error_alert(recipient_id, error_msg, "whatsapp")
        return False
    
    url = f"https://graph.facebook.com/v22.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "text",
        "text": {"body": message},
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=15) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    response_json = await response.json() if response_text else {}
                    logger.info(f"WhatsApp message sent to {recipient_id}: {response_json}")
                    return True
                else:
                    error_msg = f"WhatsApp API error {response.status}: {response_text}"
                    logger.error(error_msg)
                    await send_telegram_error_alert(recipient_id, error_msg, "whatsapp")
                    return False
                    
    except aiohttp.ClientError as e:
        error_msg = f"WhatsApp network error: {str(e)}"
        logger.error(error_msg)
        await send_telegram_error_alert(recipient_id, error_msg, "whatsapp")
        return False
    except Exception as e:
        error_msg = f"WhatsApp unexpected error: {str(e)}"
        logger.error(error_msg)
        await send_telegram_error_alert(recipient_id, error_msg, "whatsapp")
        return False

# Facebook Messenger-specific message sending (Corrected with aiohttp)
async def send_facebook_message(recipient_id: str, message: str) -> bool:
    """Send a Facebook Messenger message using the Messenger Platform API."""
    if not MESSENGER_PAGE_ACCESS_TOKEN:
        error_msg = "Messenger page access token is not set."
        logger.error(error_msg)
        await send_telegram_error_alert(recipient_id, error_msg, "messenger")
        return False
    
    params = {"access_token": MESSENGER_PAGE_ACCESS_TOKEN}
    payload = {"recipient": {"id": recipient_id}, "message": {"text": message}}
    url = "https://graph.facebook.com/v22.0/me/messages"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, params=params, json=payload, timeout=15) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    response_json = await response.json() if response_text else {}
                    logger.info(f"Messenger message sent to {recipient_id}: {response_json}")
                    return True
                else:
                    error_msg = f"Messenger API error {response.status}: {response_text}"
                    logger.error(error_msg)
                    await send_telegram_error_alert(recipient_id, error_msg, "messenger")
                    return False
                    
    except aiohttp.ClientError as e:
        error_msg = f"Messenger network error: {str(e)}"
        logger.error(error_msg)
        await send_telegram_error_alert(recipient_id, error_msg, "messenger")
        return False
    except Exception as e:
        error_msg = f"Messenger unexpected error: {str(e)}"
        logger.error(error_msg)
        await send_telegram_error_alert(recipient_id, error_msg, "messenger")
        return False

# ===== START: ADDED AD_ID AND REFERRAL HANDLING LOGIC =====

async def search_by_ad_id(ad_id: str) -> dict:
    """Calls an external tool to find job info by ad_id using aiohttp."""
    # This function assumes a local tool is running, as in the old file. 
    mcp_port = get_env_var("MCP_PORT", "8000")
    url = f"http://localhost:{mcp_port}/mcp/tool/search_by_ad_id"
    payload = {"ad_id": ad_id, "detail_level": "summary"}
    logger.info(f"Calling external tool to search for ad_id: {ad_id}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=10) as response:
                response.raise_for_status()
                result = await response.json()
                logger.info(f"Tool search_by_ad_id returned: {json.dumps(result)}")
                return result
    except aiohttp.ClientError as e:
        logger.error(f"Error calling search_by_ad_id tool: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error in search_by_ad_id: {e}", exc_info=True)
        return {}


async def update_session_with_job_info(user_id: str, channel: str, job_id, job_title: str, ad_id_or_ref: str = None):
    """
    Updates session state with job info. If the job has changed, it
    deletes the old session and starts a fresh one to avoid context mix-ups.
    """
    APP_NAME = "Jobs Support"
    should_reset_session = False
    
    # Correct WhatsApp number format before checking session
    if channel == 'whatsapp' and user_id.startswith('521'):
        user_id = user_id.replace('521', '52', 1)

    existing_sessions = session_service.list_sessions(app_name=APP_NAME, user_id=user_id)
    
    if existing_sessions and len(existing_sessions.sessions) > 0:
        session_id = existing_sessions.sessions[0].id
        session = session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
        current_job_id = session.state.get("current_job_id")
        
        # If the new job_id is different from the one in the session, flag for reset
        if job_id and current_job_id and str(job_id) != str(current_job_id):
            logger.info(f"Job ID changed from {current_job_id} to {job_id}. Resetting session for user {user_id}.")
            session_service.delete_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
            should_reset_session = True
        else:
            logger.info(f"Job ID ({job_id}) has not changed. Continuing existing session {session_id}.")
    else:
        # No existing session, so we need to create one.
        should_reset_session = True

    if should_reset_session:
        new_state = initial_state.copy()
        new_state.update({
            "channel": channel,
            "phone_number": user_id,
            "current_job_id": job_id,
            "current_job_title": job_title,
            "current_ad_id": ad_id_or_ref,
            "interaction_history": []
        })
        # If it's a new session from WhatsApp, also set the contact phone number
        if channel == 'whatsapp':
            new_state["contact_phone_number"] = user_id
            
        new_session = session_service.create_session(app_name=APP_NAME, user_id=user_id, state=new_state)
        logger.info(f"Created new fresh session {new_session.id} for user {user_id} with job {job_id}.")

# ===== END: ADDED AD_ID AND REFERRAL HANDLING LOGIC =====
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

# Unified webhook handlers for both platforms
@app.route("/webhook-messenger", methods=["GET", "POST"])
async def webhook_messenger():
    """Handles webhook requests from Facebook Messenger."""
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode and token and mode == "subscribe" and token == VERIFY_TOKEN:
            logger.info("Messenger webhook verified.")
            return challenge, 200
        else:
            logger.warning("Messenger verification failed.")
            return "Messenger verification failed.", 403

    elif request.method == "POST":
        data = request.json
        logger.info(f"Received Messenger POST request: {json.dumps(data, indent=2)}")
        try:
            for entry in data.get("entry", []):
                for messaging_event in entry.get("messaging", []):
                    sender_id = messaging_event.get("sender", {}).get("id")
                    if not sender_id:
                        continue

                    message_text = messaging_event.get("message", {}).get("text", "")
                    referral_data = messaging_event.get("referral")
                    
                    job_info_from_referral = None
                    search_value = None

                    if referral_data:
                        logger.info(f"Referral data found for {sender_id}: {referral_data}")
                        if referral_data.get('source') == 'ADS' and 'ad_id' in referral_data:
                            search_value = referral_data['ad_id']
                        elif 'ref' in referral_data:
                            search_value = referral_data['ref']
                        
                        if search_value:
                            job_info_from_referral = await search_by_ad_id(search_value)

                    if job_info_from_referral and job_info_from_referral.get('Id_Puesto'):
                        job_id = job_info_from_referral.get('Id_Puesto')
                        job_title = job_info_from_referral.get('Nombre_de_vacante') or job_info_from_referral.get('Puesto')
                        
                        await update_session_with_job_info(
                            user_id=sender_id,
                            channel="messenger",
                            job_id=job_id,
                            job_title=job_title,
                            ad_id_or_ref=search_value
                        )

                    if message_text:
                        await process_message(
                            sender_id=sender_id,
                            user_query=message_text,
                            channel="messenger",
                        )
                    else:
                        logger.info(f"Received event without text for {sender_id} (e.g., referral). No message processed.")

            return "EVENT_RECEIVED", 200
        except Exception as e:
            logger.error(f"Error processing Messenger request: {e}", exc_info=True)
            return jsonify({"status": "error", "message": "Internal Server Error"}), 500

@app.route("/webhook-whatsapp", methods=["GET", "POST"])
async def webhook_whatsapp():
    """Handles webhook requests from WhatsApp Cloud API."""
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode and token and mode == "subscribe" and token == VERIFY_TOKEN:
            logger.info("WhatsApp webhook verified.")
            return challenge, 200
        else:
            logger.warning("WhatsApp verification failed.")
            return "WhatsApp verification failed.", 403

    elif request.method == "POST":
        data = request.json
        logger.info(f"Received WhatsApp POST request: {json.dumps(data, indent=2)}")
        try:
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if "messages" in value:
                        for message_event in value["messages"]:
                            sender_id = message_event["from"]
                            message_text = message_event.get("text", {}).get("body", "")
                            
                            # MODIFIED: Check for WhatsApp referral data
                            referral_data = message_event.get("referral")
                            if referral_data and "whatsapp" in referral_data:
                                whatsapp_ref = referral_data["whatsapp"]
                                logger.info(f"WhatsApp referral data found for {sender_id}: {whatsapp_ref}")
                                
                                source = whatsapp_ref.get("source", {})
                                referral_id = source.get("id")
                                
                                if referral_id:
                                    # Use headline or body as job title
                                    job_title = whatsapp_ref.get("headline") or whatsapp_ref.get("body") or "Puesto de Anuncio de WhatsApp"
                                    
                                    await update_session_with_job_info(
                                        user_id=sender_id,
                                        channel="whatsapp",
                                        job_id=referral_id, # Use the referral ID as the job ID
                                        job_title=job_title,
                                        ad_id_or_ref=referral_id
                                    )

                            if message_text:
                                await process_message(
                                    sender_id=sender_id,
                                    user_query=message_text,
                                    channel="whatsapp",
                                )
                            else:
                                logger.info(f"Received WhatsApp event without text for {sender_id}. No message processed.")

            return "EVENT_RECEIVED", 200
        except Exception as e:
            logger.error(f"Error processing WhatsApp request: {e}", exc_info=True)
            return jsonify({"status": "error", "message": "Internal Server Error"}), 500


# CORRECTED unified message processing logic
async def process_message(sender_id: str, user_query: str, channel: str):
    """
    Unified function to process incoming messages, using correct session management.
    """
    logger.info(f"Processing message for {channel} from {sender_id}: '{user_query}'")
    APP_NAME = "Jobs Support"
    
    if channel == 'whatsapp':
        if sender_id.startswith('521'):
            original_id = sender_id
            sender_id = sender_id.replace('521', '52', 1)
            logger.info(f"Correcting WhatsApp number format from {original_id} to {sender_id}")
    
    USER_ID = sender_id

    try:
        existing_sessions = session_service.list_sessions(
            app_name=APP_NAME,
            user_id=USER_ID,
        )

        if existing_sessions and len(existing_sessions.sessions) > 0:
            SESSION_ID = existing_sessions.sessions[0].id
            logger.info(f"Continuing existing session: {SESSION_ID} for user {USER_ID}")
        else:
            new_session_state = initial_state.copy()
            new_session_state['channel'] = channel
            new_session_state['phone_number'] = USER_ID
            if channel == 'whatsapp':
                new_session_state['contact_phone_number'] = USER_ID

            new_session = session_service.create_session(
                app_name=APP_NAME,
                user_id=USER_ID,
                state=new_session_state,
            )
            SESSION_ID = new_session.id
            logger.info(f"Created new session: {SESSION_ID} for user {USER_ID}")

        add_user_query_to_history(
            session_service, APP_NAME, USER_ID, SESSION_ID, user_query
        )

        agent_response = await call_agent_async(
            runner, USER_ID, SESSION_ID, user_query, for_whatsapp=(channel == "whatsapp")
        )

        if agent_response:
            logger.info(f"Sending response to {channel} {sender_id}: '{agent_response}'")
            await send_message_async(channel, sender_id, agent_response)
        else:
            logger.warning(f"Agent returned no response for user {sender_id}")

    except Exception as e:
        logger.error(f"Error in process_message for user {sender_id}: {e}", exc_info=True)
        error_message = "Lo siento, ocurrió un error al procesar tu mensaje. Por favor, intenta de nuevo más tarde."
        await send_message_async(channel, sender_id, error_message)

def get_sessions_from_db():
    """Connects to the database and returns a list of users with their sessions."""
    try:
        conn = sqlite3.connect('./chambella_agent_data.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        mexico_tz = pytz.timezone('America/Mexico_City')
        
        def convert_to_mexico_time(timestamp_str):
            if not timestamp_str: return "Never"
            try:
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                return dt.astimezone(mexico_tz).strftime('%Y-%m-%d %H:%M:%S CST')
            except (ValueError, TypeError):
                return timestamp_str

        cursor.execute("""
            SELECT s.user_id, s.state, s.id as session_id, s.create_time, s.update_time
            FROM sessions s WHERE s.app_name = 'Jobs Support' ORDER BY s.user_id, s.update_time DESC
        """)
        
        users_map = {}
        for row in cursor.fetchall():
            user_id = row['user_id']
            state = json.loads(row['state'])

            if user_id not in users_map:
                users_map[user_id] = {
                    'user_id': user_id,
                    'user_name': state.get('user_name', ''),
                    'contact_phone_number': state.get('contact_phone_number', ''),
                    'last_access': convert_to_mexico_time(row['update_time']),
                    'sessions': []
                }
            session_data = {
                'session_id': row['session_id'],
                'current_ad_id': state.get('current_ad_id'),
                'current_job_id': state.get('current_job_id'),
                'current_job_title': state.get('current_job_title'),
                'create_time': convert_to_mexico_time(row['create_time']),
                'update_time': convert_to_mexico_time(row['update_time']),
                'interaction_history': state.get('interaction_history', []),
                'applied_jobs': state.get('applied_jobs', []),
                'events': []
            }
            users_map[user_id]['sessions'].append(session_data)

        session_id_map = {}
        for user in users_map.values():
            for session in user['sessions']:
                session_id_map[session['session_id']] = session

        cursor.execute("""
            SELECT session_id, author, timestamp, content
            FROM events
            WHERE app_name = 'Jobs Support'
            ORDER BY timestamp ASC
        """)
        for row in cursor.fetchall():
            session_id, author, timestamp, content_json = row
            content = json.loads(content_json) if content_json else {}
            event = {
                'author': author,
                'timestamp': convert_to_mexico_time(timestamp),
                'content': content
            }
            if session_id in session_id_map:
                session_id_map[session_id]['events'].append(event)

        users = list(users_map.values())
        conn.close()
        return users
    except Exception as e:
        logger.error(f"Error in get_sessions_from_db: {e}")
        return []
        
# ===== Database Query Interface =====
@app.route('/', methods=['GET'])
def db_interface():
    """Serve the database query interface."""
    try:
        users = get_sessions_from_db()
        return render_template('index.html', users=users, delete_password=DELETE_PASSWORD)
    except Exception as e:
        logger.error(f"Error serving database interface: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ===== FIX: Added Delete Session API Endpoint =====
@app.route('/api/delete-session', methods=['POST'])
def delete_session():
    """API endpoint to delete a session and create a new empty one"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        session_id = data.get('session_id')
        password = data.get('password')
        
        logger.info(f"DELETE SESSION REQUEST: user_id={user_id}, session_id={session_id}, password={'*' * len(password) if password else 'None'}")
        
        if password != DELETE_PASSWORD:
            logger.warning(f"Invalid password attempt for user {user_id}")
            return jsonify({'success': False, 'error': 'Incorrect password'}), 403
        
        if not user_id or not session_id:
            logger.error(f"Missing required fields: user_id={user_id}, session_id={session_id}")
            return jsonify({'success': False, 'error': 'Missing user_id or session_id'}), 400
        
        APP_NAME = "Jobs Support"
        
        try:
            current_session = session_service.get_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id
            )
            
            preserved_data = {
                "user_name": current_session.state.get("user_name", ""),
                "last_name": current_session.state.get("last_name", ""),
                "email": current_session.state.get("email", ""),
                "contact_phone_number": current_session.state.get("contact_phone_number", ""),
                "channel": current_session.state.get("channel", ""),
                "phone_number": current_session.state.get("phone_number", ""),
            }
            
            logger.info(f"Preserved user data: {preserved_data}")
            
        except Exception as e:
            logger.warning(f"Could not get current session data: {e}")
            preserved_data = {}
        
        try:
            session_service.delete_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id
            )
            logger.info(f"Successfully deleted session {session_id} for user {user_id}")
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}")
            return jsonify({'success': False, 'error': f'Failed to delete session: {str(e)}'}), 500
        
        try:
            new_clean_state = initial_state.copy()
            new_clean_state.update(preserved_data)
            
            new_session = session_service.create_session(
                app_name=APP_NAME,
                user_id=user_id,
                state=new_clean_state
            )
            
            logger.info(f"Successfully created new empty session {new_session.id} for user {user_id}")
            
            return jsonify({
                'success': True, 
                'message': 'Session deleted and new empty session created successfully',
                'new_session_id': new_session.id
            }), 200
            
        except Exception as e:
            logger.error(f"Error creating new session for user {user_id}: {e}")
            return jsonify({'success': False, 'error': f'Failed to create new session: {str(e)}'}), 500
            
    except Exception as e:
        logger.error(f"Error in delete_session API: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

# ===== Server Startup and Shutdown =====
PORT = int(os.environ.get("PORT", 7010))
HOST = os.environ.get("HOST", "0.0.0.0")

async def startup_handler():
    logger.info("Starting up runner and session service...")

async def shutdown_handler():
    logger.info("Shutting down...")
    logger.info("Shutdown complete.")

def signal_handler(sig, frame):
    logger.info(f"Received signal {sig}, initiating shutdown...")
    asyncio.create_task(shutdown_handler())

def start_server():
    """Start the async Flask server with uvicorn"""
    print(f"🚀 Starting Chambella unified server with verbosity level {VERBOSE_LEVEL}")
    print("   Level 0: Minimal output")
    print("   Level 1: Basic agent flow")
    print("   Level 2: Detailed with session state")
    print("   Level 3: Full debug with HTTP details")

    uvicorn.run(
        asgi_app,
        host=HOST,
        port=PORT,
        log_level="info",
    )

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    start_server()