"""Extract the real provider catalog from a 9router checkout into Zeline data.

Reads ``open-sse/providers/registry/*.js`` — one file per provider — and emits a
compact JSON catalog of what Zeline actually needs to prefill a connection:
display name, chat base URL, wire protocol, and auth mode. Endpoint URLs are
copied verbatim from the source; nothing is invented.

Usage:
    python tools/extract_provider_catalog.py ~/.cache/9router-mibp-version \\
        > zeline-frontend/provider_catalog.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Only chat-capable providers belong in a Zeline connection picker. Media-only
# entries (TTS, embeddings, image, search) cannot serve an agent chat loop.
CHAT_PATH_HINTS = ("/chat/completions", "/v1/messages", "/api/chat")
SKIP_IDS = {
    "index", "selfhosted-embedding", "selfhosted-stt", "selfhosted-tts",
    "assemblyai", "deepgram", "elevenlabs", "cartesia", "playht", "inworld",
    "fish-audio", "coqui", "edge-tts", "google-tts", "aws-polly", "tortoise",
    "black-forest-labs", "fal-ai", "recraft", "runwayml", "stability-ai",
    "topaz", "nanobanana", "comfyui", "sdwebui",
    "brave-search", "exa", "firecrawl", "google-pse", "jina-ai", "jina-reader",
    "linkup", "perplexity", "perplexity-agent", "searchapi", "serper",
    "tavily", "youcom", "ollama-search", "searxng",
    "voyage-ai", "huggingface", "cohere", "mistral",
}

AUTH_MODE_LABELS = {
    "apikey": "api_key",
    "oauth": "oauth",
    "none": "none",
}


def quoted(source: str, key: str) -> str:
    match = re.search(rf'^\s*{key}\s*:\s*"([^"]*)"', source, re.M)
    return match.group(1) if match else ""


def all_quoted(source: str, key: str) -> list[str]:
    return re.findall(rf'^\s*{key}\s*:\s*"([^"]*)"', source, re.M)


def display_name(source: str, fallback: str) -> str:
    block = re.search(r"display\s*:\s*\{", source)
    if not block:
        return fallback
    # Walk braces from the display object so a nested `notice` cannot truncate it.
    depth, start = 0, block.end() - 1
    end = start
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    inner = source[start:end]
    name = re.search(r'\bname\s*:\s*"([^"]+)"', inner)
    return name.group(1) if name else fallback


def auth_modes(source: str) -> list[str]:
    raw = re.search(r"authModes\s*:\s*\[([^\]]*)\]", source)
    if raw:
        modes = re.findall(r'"([^"]+)"', raw.group(1))
    else:
        single = quoted(source, "authType")
        modes = [single] if single else []
    if not modes:
        modes = ["apikey"]
    seen: list[str] = []
    for mode in modes:
        label = AUTH_MODE_LABELS.get(mode, mode)
        if label not in seen:
            seen.append(label)
    return seen


def protocol_for(url: str, source: str) -> str:
    if "/v1/messages" in url:
        return "anthropic"
    if "/chat/completions" in url or "/v1/chat" in url:
        return "openai"
    if "ollama" in url:
        return "ollama"
    return "openai"


def chat_base(url: str, protocol: str) -> str:
    """Trim a full endpoint back to the base URL a provider config wants.

    Zeline appends the protocol's own path to a configured base URL, so an
    Anthropic connection keeps the ``/v1/messages`` suffix it was verified
    against while an OpenAI one keeps just the API root.
    """
    url = url.split("?")[0].rstrip("/")
    if protocol == "anthropic" and url.endswith("/v1/messages"):
        return url
    for suffix in ("/chat/completions", "/v1/messages", "/api/chat"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    return url or ""


# The dashboard groups providers by how a connection is made. These buckets
# mirror that grouping so the UI can render the same sections without deriving
# them from auth mode at render time.
def bucket_for(category: str) -> str:
    if category == "oauth":
        return "oauth"
    if category in {"free", "freeTier"}:
        return "free"
    return "apikey"


def build_entry(provider_id: str, source: str) -> dict | None:
    urls = [u for u in all_quoted(source, "baseUrl") if any(h in u for h in CHAT_PATH_HINTS)]
    if not urls:
        return None
    # Zeline's tool loop is lossless on the native Anthropic wire format, so
    # prefer that endpoint whenever a provider publishes one.
    chosen = next((u for u in urls if "/v1/messages" in u), urls[0])
    protocol = protocol_for(chosen, source)
    name = display_name(source, provider_id)
    category = quoted(source, "category") or "apikey"
    return {
        "id": provider_id,
        "name": name,
        "protocol": protocol,
        "base_url": chat_base(chosen, protocol),
        "auth": auth_modes(source),
        "category": category,
        "group": bucket_for(category),
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1]).expanduser()
    registry = root / "open-sse" / "providers" / "registry"
    if not registry.is_dir():
        print(f"not a 9router checkout: {registry}", file=sys.stderr)
        return 1

    entries = []
    for path in sorted(registry.glob("*.js")):
        if path.stem in SKIP_IDS or path.stem == "index":
            continue
        entry = build_entry(path.stem, path.read_text(encoding="utf-8", errors="ignore"))
        if entry:
            entries.append(entry)

    entries.sort(key=lambda item: (item["category"] != "apikey", item["name"].lower()))
    json.dump({"providers": entries}, sys.stdout, indent=2, ensure_ascii=False)
    print(file=sys.stderr)
    print(f"# {len(entries)} chat providers extracted", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
