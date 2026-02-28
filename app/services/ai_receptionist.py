import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

QUALIFICATION_SCRIPT = [
    "Hello, this is an automated call from {agent_name}'s real estate team. "
    "I'm calling about your inquiry. Is this a good time to talk?",
    "Are you looking to buy or sell a property?",
    "What is your budget range?",
    "What is your preferred location or neighbourhood?",
    "What is your timeline for this transaction?",
    "Thank you for your time. {agent_name} will be in touch with you shortly. Goodbye!",
]


def _get_twilio_client():
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured. AI calling disabled.")
        return None
    try:
        from twilio.rest import Client
        return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    except Exception as exc:
        logger.error("Failed to initialise Twilio client: %s", exc)
        return None


def generate_twiml_script(agent_name: str, step: int = 0) -> str:
    """Generate TwiML XML for a qualification call script step."""
    try:
        from twilio.twiml.voice_response import Gather, VoiceResponse
    except ImportError:
        logger.error("twilio package not available")
        return "<Response><Hangup/></Response>"

    response = VoiceResponse()

    if step >= len(QUALIFICATION_SCRIPT):
        response.say("Thank you. Goodbye!", voice="Polly.Joanna")
        response.hangup()
        return str(response)

    script_line = QUALIFICATION_SCRIPT[step].format(agent_name=agent_name)
    next_step = step + 1
    action_url = f"{settings.BASE_URL}/webhook/voice?step={next_step}&agent={agent_name}"

    if step < len(QUALIFICATION_SCRIPT) - 1:
        gather = Gather(
            input="speech",
            action=action_url,
            method="POST",
            timeout=5,
            speech_timeout="auto",
        )
        gather.say(script_line, voice="Polly.Joanna")
        response.append(gather)
        # Fallback if no input
        response.redirect(action_url)
    else:
        response.say(script_line, voice="Polly.Joanna")
        response.hangup()

    return str(response)


def initiate_qualification_call(lead_phone: str, agent_name: str, lead_id: int) -> Optional[str]:
    """Initiate an AI qualification call to a lead via Twilio. Returns call SID."""
    client = _get_twilio_client()
    if client is None:
        return None

    twiml_url = f"{settings.BASE_URL}/webhook/voice?step=0&agent={agent_name}&lead_id={lead_id}"

    try:
        call = client.calls.create(
            to=lead_phone,
            from_=settings.TWILIO_WHATSAPP_NUMBER.replace("whatsapp:", ""),
            url=twiml_url,
            method="GET",
        )
        logger.info("Qualification call initiated to %s, SID=%s", lead_phone, call.sid)
        return call.sid
    except Exception as exc:
        logger.error("Failed to initiate qualification call to %s: %s", lead_phone, exc)
        return None
