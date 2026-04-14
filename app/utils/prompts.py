import logging
from pathlib import Path
import yaml

logger = logging.getLogger("tprm.prompts")

_cache: dict[str, dict] = {}

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(name: str) -> dict:
    """Load a prompt template from YAML file."""
    if name in _cache:
        return _cache[name]

    path = PROMPTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        template = yaml.safe_load(f)

    _cache[name] = template
    return template


def render_prompt(name: str, **kwargs) -> str:
    """Load a prompt template and render it with provided variables."""
    template = load_prompt(name)
    system_prompt = template.get("system", "")
    user_prompt = template.get("user", "")

    for key, value in kwargs.items():
        placeholder = f"{{{{{key}}}}}"
        user_prompt = user_prompt.replace(placeholder, str(value))
        system_prompt = system_prompt.replace(placeholder, str(value))

    return user_prompt


def get_system_prompt(name: str) -> str:
    """Get just the system prompt from a template."""
    template = load_prompt(name)
    return template.get("system", "You are a TPRM security analysis assistant.")
