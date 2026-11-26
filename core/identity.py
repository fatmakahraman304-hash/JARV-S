"""FRIDAY display identity and narrowly scoped, read-only legacy compatibility.

Legacy names here are identifiers, never UI labels. Do not delete or rename
existing user stores, Android identities, updater journals or third-party APIs.
"""
import os
from pathlib import Path

NAME = 'FRIDAY'
LEGACY_UI_CLASS = 'AetherUI'
LEGACY_LIVE_CLASS = 'AetherLive'
LEGACY_DATA_DIR = 'AetherMurat'
LEGACY_WORKSPACE = 'Murat'


def data_home():
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_DATA_HOME')
    base = Path(base) if base else Path.home() / '.local' / 'share'
    legacy = base / LEGACY_DATA_DIR
    # Existing stores stay exactly where they are. Fresh installs use FRIDAY.
    return legacy if legacy.is_dir() else base / 'FridayAssistant'


def workspace_parent():
    legacy = Path.home() / 'AetherDevelopment'
    return legacy if legacy.is_dir() else Path.home() / 'FridayDevelopment'


def projects_home():
    desktop = Path.home() / 'Desktop'
    legacy = desktop / 'AetherProjects'
    return legacy if legacy.is_dir() else desktop / 'FridayProjects'


LEGACY_DISCOVERY_MAGIC = 'AETHER-DEVICE-1'
LEGACY_AES_SALT = b'AETHER-DASHBOARD-v1'


def artifact_home(base, *, logs=False):
    base = Path(base)
    legacy = base / ('Aether' if logs else 'AETHER')
    return legacy if legacy.is_dir() else base / ('Friday' if logs else 'FRIDAY')

LEGACY_SPOKEN_NAME = 'aether'


DEV_BRANCH_PREFIX = 'friday-dev/'
LEGACY_DEV_BRANCH_PREFIX = 'aether-dev/'


def is_development_branch(name):
    return name.startswith((DEV_BRANCH_PREFIX, LEGACY_DEV_BRANCH_PREFIX))
