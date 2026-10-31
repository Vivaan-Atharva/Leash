"""Create demo keys in keys/ if they don't exist yet."""
from shared.config import keys_dir
from shared.keys import ensure_keys

if __name__ == "__main__":
    ensure_keys()
    print(f"keys ready in {keys_dir()}")
