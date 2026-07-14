import logging

from sentinel.core.user_profile import UserProfileManager

log = logging.getLogger("sentinel.profile")

_svc: UserProfileManager = None


def wire_dependencies(db=None):
    global _svc
    if db is None:
        log.warning("No database provided, profile manager not available")
        return
    _svc = UserProfileManager(db)
    _svc.get_or_create_profile("local-user", username="local-user", display_name="Local User")
    log.info("Profile module wired: default profile ready")
