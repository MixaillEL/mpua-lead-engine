from app.core.config import get_settings


def get_user_agent() -> str:
    return get_settings().WEBSITE_USER_AGENT
