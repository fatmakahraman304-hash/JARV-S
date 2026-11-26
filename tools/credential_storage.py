"""Explicit local Windows credential protection; never print credential values."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memory import config_manager as config
from memory.secret_storage import StorageError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--status', action='store_true')
    actions.add_argument('--enable', action='store_true', help='Bind credentials to this Windows profile')
    actions.add_argument('--disable', action='store_true', help='Explicitly restore plaintext before export/downgrade')
    args = parser.parse_args()
    try:
        changed = config.configure_credential_storage(args.enable) if not args.status else False
        print(json.dumps({**config.credential_storage_status(), 'changed': changed}))
    except (OSError, ValueError, StorageError):
        raise SystemExit('Credential storage operation failed. Files were preserved; check the Windows profile and existing backups.') from None


if __name__ == '__main__':
    main()
