from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Limit requests by client address without applying defaults to unrelated routes
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
)
