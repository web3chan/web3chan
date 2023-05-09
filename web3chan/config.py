import os
import logging


def env_var(key, default=None):
    """Retrieves env vars and makes Python boolean replacements"""
    val = os.environ.get(key, default)
    if val == 'True':
        val = True
    elif val == 'False':
        val = False
 
    return val

APP_NAME = env_var("WEB3CHAN_APP_NAME", "web3chan")
DATABASE = env_var("WEB3CHAN_DATABASE", "")
RPC_ADDRESS = env_var("WEB3CHAN_RPC_ADDRESS", "127.0.0.1:18166")
AUTOFOLLOW = env_var("WEB3CHAN_AUTOFOLLOW", "True")
REPLIES = env_var("WEB3CHAN_REPLIES", "True")
STREAMING = env_var("WEB3CHAN_STREAMING", "False")
FETCHER_COOLDOWN = int(env_var("FETCHER_COOLDOWN", "120"))
FETCHER_COOLDOWN_WITH_STREAMING = int(env_var("FETCHER_COOLDOWN_WITH_STREAMING", "300"))
RELATIONSHIPS_SYNCER_COOLDOWN = int(env_var("RELATIONSHIPS_SYNCER_COOLDOWN", "1800"))

LOGLEVEL = env_var("WEB3CHAN_LOGLEVEL", "DEBUG")
if LOGLEVEL in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
    logging.basicConfig(level=getattr(logging, LOGLEVEL))

logging.getLogger("websockets").setLevel(logging.CRITICAL)