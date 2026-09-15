"""Feishu event transport foundation. No ServiceCase handlers in D6.5.1."""

from app.integrations.feishu.events.dispatcher import create_event_dispatcher

__all__ = ["create_event_dispatcher"]
