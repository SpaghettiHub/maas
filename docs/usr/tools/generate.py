#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Generate MAAS CLI documentation from introspector JSON."""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except Exception:
    Environment = None
    FileSystemLoader = None
    select_autoescape = None


def normalize_text(text: str) -> str:
    """Normalize text for Markdown output."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.strip()
    text = text.replace("|", "\\|")
    text = text.replace("\n", "<br>")
    return text


def escape_md(text: str) -> str:
    if not text:
        return ""
    return text.replace('|', '\\|')


def bold_list_leaders(text: str) -> str:
    """Bold the leader word(s) in list items like "- Name: details".

    Preserves indentation and leaves other lines untouched.
    """
    if not text:
        return text
    lines = text.splitlines()
    processed: List[str] = []
    for ln in lines:
        stripped = ln.lstrip()
        indent = ln[: len(ln) - len(stripped)]
        if stripped.startswith("- ") and ":" in stripped:
            head, rest = stripped[2:].split(":", 1)
            head = head.strip()
            processed.append(f"{indent}- **{head}**:{rest}")
        else:
            processed.append(ln)
    return "\n".join(processed)


def parse_keywords_text(keywords_text: str) -> Dict[str, Any]:
    """Parse sphinx-style epilog into structured keywords."""
    result: Dict[str, Any] = {"lead": "", "params": []}
    if not keywords_text:
        return result

    lines = keywords_text.splitlines()
    lead_lines: List[str] = []
    params: Dict[str, Dict[str, str]] = {}
    current_param: Optional[str] = None

    def get_or_create(name: str) -> Dict[str, str]:
        if name not in params:
            params[name] = {"name": name, "desc": "", "type": ""}
        return params[name]

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        if line.startswith(":param "):
            try:
                after = line[len(":param ") :]
                name, desc = after.split(":", 1)
                name = name.strip()
                desc = desc.strip()
            except ValueError:
                lead_lines.append(raw)
                i += 1
                continue
            entry = get_or_create(name)
            entry_desc_lines = [desc]
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if nxt.strip().startswith(":param ") or nxt.strip().startswith(
                    ":type "
                ):
                    break
                entry_desc_lines.append(nxt.rstrip())
                j += 1
            entry["desc"] = "\n".join([s.rstrip() for s in entry_desc_lines]).strip()
            current_param = name
            i = j
            continue
        elif line.startswith(":type "):
            try:
                after = line[len(":type ") :]
                name, typ = after.split(":", 1)
                name = name.strip()
                typ = typ.strip()
            except ValueError:
                lead_lines.append(raw)
                i += 1
                continue
            entry = get_or_create(name)
            entry["type"] = typ
            i += 1
            continue
        else:
            if current_param is None:
                lead_lines.append(raw)
            else:
                if raw.startswith(" ") or raw.startswith("\t"):
                    entry = get_or_create(current_param)
                    entry["desc"] = (
                        entry.get("desc", "") + "\n" + raw.rstrip()
                    ).strip()
                else:
                    lead_lines.append(raw)
            i += 1
            continue

    ordered_params: List[Dict[str, str]] = []
    seen: set = set()
    for line in lines:
        if line.strip().startswith(":param "):
            name = line.strip()[len(":param ") :].split(":", 1)[0].strip()
            if name in params and name not in seen:
                ordered_params.append(params[name])
                seen.add(name)
    for name, entry in params.items():
        if name not in seen:
            ordered_params.append(entry)

    lead = "\n".join(lead_lines).strip()
    lead = escape_md(lead)
    try:
        lead = re.sub(r"(?m)^:([a-z0-9_\-]+):", r"**:\\1:**", lead)
    except Exception:
        pass
    lead = (
        "<br>".join([l.rstrip() for l in lead.splitlines()]) if lead else ""
    )
    for e in ordered_params:
        desc_text = escape_md(e.get("desc", "")).strip()
        try:
            desc_text = re.sub(
                r"(?m)^:([a-z0-9_\-]+):", r"**:\1:**", desc_text
            )
        except Exception:
            pass
        e["desc"] = (
            "<br>".join([l.rstrip() for l in desc_text.splitlines()])
            if desc_text
            else ""
        )
        e["type"] = escape_md(e.get("type", "")).strip()

    result["lead"] = lead
    result["params"] = ordered_params
    return result


def format_usage(usage: str, command_path: str) -> str:
    """Format usage string for Markdown."""
    if not usage:
        parts = command_path.split()
        if len(parts) == 1:
            return f"maas {parts[0]} [-h]"
        elif len(parts) == 2:
            return f"maas {parts[0]} {parts[1]} [-h]"
        else:
            return f"maas {' '.join(parts)} [-h]"

    usage = usage.replace("usage:", "").replace("usage :", "").strip()
    markers = [
        " positional arguments:",
        " options:",
        " optional arguments:",
        " Keywords",
        " Command-line options",
    ]
    for marker in markers:
        idx = usage.find(marker)
        if idx != -1:
            usage = usage[:idx].rstrip()

    parts = command_path.split()
    top_level = {
        "login",
        "logout",
        "list",
        "refresh",
        "configauth",
        "apikey",
        "changepassword",
        "config-tls",
        "config-vault",
        "createadmin",
        "msm",
        "status",
        "init",
        "config",
        "migrate",
    }
    if parts and parts[0] in top_level:
        return usage

    usage_parts = usage.split()
    if len(usage_parts) > 1 and usage_parts[0] == "maas":
        usage_parts[1] = "$PROFILE"
        usage = " ".join(usage_parts)

    return usage


def format_options(options: List[Dict[str, Any]]) -> str:
    """Format command options as a Markdown table."""
    if not options:
        return ""

    lines: List[str] = []
    lines.append("#### Command-line options")
    lines.append("| Option | Effect |")
    lines.append("|---|---|")
    for row in options:
        opt_text = str(row.get("option", "")).strip()
        eff_text = str(row.get("effect", "")).strip()
        if not eff_text:
            eff_text = ""
        lines.append(f"| {opt_text} | {eff_text} |")
    lines.append("")
    return "\n".join(lines)


def extract_positional_args(usage: str, command_path: str) -> List[str]:
    """Extract positional arguments from usage."""
    if not usage:
        return []
    parts = command_path.split()
    if len(parts) == 1:
        top_level = {
            "login",
            "logout",
            "list",
            "refresh",
            "configauth",
            "apikey",
            "changepassword",
            "config-tls",
            "config-vault",
            "createadmin",
            "msm",
            "status",
            "init",
            "config",
            "migrate",
        }
        if parts[0] in top_level:
            return []
    scrubbed = re.sub(r"\[[^\]]*\]", "", usage)
    tokens = scrubbed.split()
    if not tokens:
        return []
    if tokens and tokens[0] == "maas":
        tokens = tokens[1:]
    if tokens and tokens[0] == "$PROFILE":
        tokens = tokens[1:]
    path_tokens = command_path.split()
    i = 0
    for pt in path_tokens:
        if i < len(tokens) and tokens[i] == pt:
            i += 1
    tokens = tokens[i:]
    return [
        t.strip(",|")
        for t in tokens
        if t not in {"...", "COMMAND", "|"}
        and "{" not in t
        and "}" not in t
    ]


def format_positional_args(args: List[str]) -> str:
    """Format positional arguments as Markdown table."""
    if not args:
        return ""

    markdown = "#### Positional arguments\n"
    markdown += "| Argument | Effect |\n"
    markdown += "|----------|--------|\n"

    for arg in args:
        if arg == "system_id":
            description = "The system ID of the machine/device"
        elif arg == "id":
            description = "The ID of the resource"
        elif arg == "name":
            description = "The name of the resource"
        elif arg == "data ...":
            description = "Additional keyword arguments in the form `key=value`"
        else:
            description = f"The {arg} parameter"

        markdown += f"| {arg} | {description} |\n"

    markdown += "\n"
    return markdown


def render_with_template(env: Any, context: Dict[str, Any]) -> str:
    template = env.get_template("cli_page.md.j2")
    return template.render(**context)


def generate_command_markdown(
    env: Any, command: Dict[str, Any], command_path: str
) -> str:
    """Generate Markdown content for a single command using Jinja2."""
    overview_raw = command.get("overview", "") or ""
    overview_lines = [
        ln
        for ln in overview_raw.splitlines()
        if not ln.strip().lower().startswith("cli help for:")
    ]
    overview = normalize_text("\n".join(overview_lines))
    if overview and overview.endswith("<br>"):
        tmp = overview.replace("<br>", " ").strip()
        if tmp and ("." not in tmp) and (len(tmp.split()) >= 2):
            overview = ""
    usage_raw = command.get("usage", "")
    options = command.get("options", [])
    keywords_text = command.get("keywords_text", "")
    keywords = parse_keywords_text(keywords_text)
    usage = format_usage(usage_raw, command_path)
    if overview_lines:
        ov_line = overview_lines[0].strip()
        if ov_line and usage.endswith(ov_line):
            usage = usage[: -len(ov_line)].rstrip()

    additional_sections = command.get("additional_sections", [])
    has_positional_section = any(
        (
            isinstance(sec, dict)
            and str(sec.get("title", "")).strip().lower()
            == "positional arguments"
        )
        for sec in additional_sections
    )
    positional_args = (
        []
        if has_positional_section
        else extract_positional_args(usage, command_path)
    )

    if (not has_positional_section) and not positional_args and overview:
        token_only = re.match(
            r"^[a-z_][a-z0-9_]*(\s+[a-z_][a-z0-9_]*)+$",
            overview.replace("<br>", " "),
        )
        if token_only and len(command_path.split()) >= 2:
            positional_args = overview.replace("<br>", " ").split()
            overview = ""

    normalized_options: List[Dict[str, str]] = []
    moved_notes: List[str] = []
    for row in options:
        opt_text = str(row.get("option", "")).rstrip()
        eff_text = str(row.get("effect", "")).strip()

        if not eff_text and opt_text:
            m = re.match(r"^(?P<opt>\S(?:.*?\S)?)\s{2,}(?P<desc>.+)$", opt_text)
            if m:
                opt_text = m.group("opt")
                eff_text = m.group("desc").strip()

        if (
            not eff_text
            or eff_text.startswith("Running")
            or eff_text.startswith("Usage")
        ):
            m = re.match(
                r"^(?P<opt>-?\w+(?:,\s*--\w+)?)\s{2,}(?P<desc>.+)$", opt_text
            )
            if m:
                opt_text = m.group("opt")
                eff_text = m.group("desc").strip()

        if eff_text and "|" in eff_text:
            eff_text = eff_text.split("|", 1)[0].strip()

        if eff_text and (
            eff_text.startswith("Running ") or eff_text.startswith("usage")
        ):
            eff_text = ""

        if "If credentials are not provided" in eff_text:
            moved_notes.append(
                "If credentials are not provided on the command-line, "
                "they will be prompted for interactively."
            )
            eff_text = eff_text.split("If credentials are not provided", 1)[
                0
            ].rstrip()

        if opt_text:
            normalized_options.append({"option": opt_text, "effect": eff_text})

    if moved_notes:
        additional_sections.append(
            {"title": "additional_info", "content": "\n".join(moved_notes)}
        )

    if keywords_text:
        try:
            keywords_text = re.sub(
                r"(?m)^:([a-z0-9_\-]+):", r"**:\\1:**", keywords_text
            )
        except Exception:
            pass


    try:
        for sec in additional_sections:
            if isinstance(sec, dict) and isinstance(sec.get("content"), str):
                sec["content"] = bold_list_leaders(sec["content"])
    except Exception:
        # Non-fatal formatting; proceed even if it fails
        pass

    context = {
        "overview": overview,
        "usage": usage,
        "positional_args": positional_args,
        "options": normalized_options,
        "keywords_text": keywords_text,
        "keywords": keywords,
        "accepts_json": bool(command.get("accepts_json", False)),
        "returns_json": bool(command.get("returns_json", False)),
        "additional_sections": additional_sections,
    }
    return render_with_template(env, context)


def path_to_filename(path: str) -> str:
    """Convert command path to filename."""
    return path.replace(" ", "-").lower() + ".md"


def pluralize_for_filename(base_name: str) -> str:
    """Convert singular filename to plural form for lookup."""
    plural_map = {
        'commissioning-script': 'commissioning-scripts',
        'event': 'events',
        'ipaddress': 'ipaddresses',
        'node-result': 'node-results',
        'vmfs-datastore': 'vmfs-datastores',
    }
    return plural_map.get(base_name, base_name)


def find_existing_topic_number(
    base_name: str, output_dir: Path
) -> Tuple[Optional[str], Optional[str]]:
    """Find existing file with topic number or return None."""
    if not output_dir.exists():
        return None, None

    search_names = [base_name]
    plural_name = pluralize_for_filename(base_name)
    if plural_name != base_name:
        search_names.append(plural_name)

    for search_name in search_names:
        pattern = re.compile(rf"^{re.escape(search_name)}-(\d+).md$")
        tba_pattern = re.compile(rf"^{re.escape(search_name)}-tba.md$")

        for file in output_dir.iterdir():
            if file.is_file() and file.suffix == ".md":
                filename = file.name
                match = pattern.match(filename)
                if match:
                    return match.group(1), search_name
                if tba_pattern.match(filename):
                    return "tba", search_name

    return None, None


def singularize_resource(resource: str) -> str:
    """Singularize a CLI resource token."""
    curated: Dict[str, str] = {
        "machines": "machine",
        "nodes": "node",
        "subnets": "subnet",
        "fabrics": "fabric",
        "vlans": "vlan",
        "spaces": "space",
        "tags": "tag",
        "users": "user",
        "zones": "zone",
        "resource-pools": "resource-pool",
        "interfaces": "interface",
        "ipranges": "iprange",
        "ipaddresses": "ipaddress",
        "files": "file",
        "partitions": "partition",
        "block-devices": "block-device",
        "raid": "raid",
        "bcaches": "bcache",
        "vm-hosts": "vm-host",
        "vm-clusters": "vm-cluster",
        "boot-resources": "boot-resource",
        "boot-sources": "boot-source",
        "devices": "device",
        "node-devices": "node-device",
        "discoveries": "discovery",
        "dnsresources": "dnsresource",
        "static-routes": "static-route",
        "package-repositories": "package-repository",
        "vmfs-datastores": "vmfs-datastore",
        "volume-groups": "volume-group",
        "rack-controllers": "rack-controller",
        "region-controllers": "region-controller",
        "maas": "maas",
    }
    if resource in curated:
        return curated[resource]

    if "-" in resource and resource.endswith("s"):
        return resource[:-1]

    if resource.endswith("es") and len(resource) > 3:
        return resource[:-2]
    if resource.endswith("s") and len(resource) > 2:
        return resource[:-1]
    return resource


def parse_key_to_group(key: str) -> Tuple[str, Optional[str]]:
    """Return (group_name, command_path_for_usage)."""
    parts = key.split()
    if len(parts) >= 3 and parts[0] == "maas":
        if len(parts) >= 4:
            resource = parts[2]
            group = singularize_resource(resource)
            command_path = " ".join(parts[2:])
            return group, command_path
        if len(parts) == 3:
            top = parts[1]
            command_path = " ".join(parts[1:])
            return top, command_path
        if len(parts) == 2:
            return parts[1], parts[1]
    fallback = (
        " ".join(parts[1:]) if parts and parts[0] == "maas" else key
    )
    return fallback or key, fallback or key


def group_commands_by_resource(
    commands: List[Dict[str, Any]]
) -> Dict[str, List[Tuple[Dict[str, Any], str]]]:
    """Group commands by resource base (singular), or by top-level cmd."""
    groups: Dict[str, List[Tuple[Dict[str, Any], str]]] = {}
    for cmd in commands:
        key = str(cmd.get("key", ""))
        group, command_path = parse_key_to_group(key)
        groups.setdefault(group, []).append((cmd, command_path or group))
    return groups


def main():
    parser = argparse.ArgumentParser(
        description="Generate MAAS CLI documentation from introspector JSON"
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read introspector JSON array from stdin",
    )
    parser.add_argument(
        "--source", help="Optional path to JSON file (array of nodes)"
    )
    parser.add_argument(
        "--out", required=True, help="Output directory for Markdown files"
    )
    parser.add_argument(
        "--check-dirty",
        action="store_true",
        help="Exit nonzero if any file would change",
    )
    parser.add_argument(
        "--template-dir",
        default="docs/usr/tools",
        help="Directory containing cli_page.md.j2",
    )
    args = parser.parse_args()

    nodes: List[Dict[str, Any]] = []
    try:
        if args.stdin:
            nodes = json.load(sys.stdin)
        elif args.source:
            with open(args.source, "r", encoding="utf-8") as f:
                nodes = json.load(f)
        else:
            print("Error: Provide --stdin or --source")
            return 2
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}")
        return 1

    if not isinstance(nodes, list) or not nodes:
        print("Warning: No commands found in input")
        return 0

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)

    if Environment is None:
        print("Error: Jinja2 is required to render templates.")
        return 1
    env = Environment(
        loader=FileSystemLoader(args.template_dir),
        autoescape=select_autoescape(enabled_extensions=(".j2",)),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    seen_keys: Dict[str, Dict[str, Any]] = {}
    for node in nodes:
        k = str(node.get("key", ""))
        if not k:
            continue
        seen_keys[k] = node
    unique_commands: List[Dict[str, Any]] = [
        seen_keys[k] for k in sorted(seen_keys.keys())
    ]

    groups = group_commands_by_resource(unique_commands)

    files_created = 0
    files_updated = 0
    files_skipped = 0
    files_would_change = 0

    groups_to_skip = {"local", "admin"}

    for group_name, cmd_list in sorted(groups.items()):
        if group_name in groups_to_skip:
            continue

        filename = (
            f"{group_name}.md"
            if " " not in group_name
            else path_to_filename(group_name)
        )

        base_name = filename.replace(".md", "")
        suffix, actual_base_name = find_existing_topic_number(
            base_name, output_dir
        )
        if suffix and actual_base_name:
            filename = f"{actual_base_name}-{suffix}.md"
        else:
            filename = f"{base_name}-tba.md"

        filepath = output_dir / filename

        markdown_parts: List[str] = []
        for command, command_path in sorted(
            cmd_list, key=lambda t: (t[1], str(t[0].get("key", "")))
        ):
            markdown_parts.append(
                generate_command_markdown(env, command, command_path)
            )
            markdown_parts.append("")
        markdown_content = "\n".join(markdown_parts).rstrip() + "\n"

        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                existing_content = f.read()
            if existing_content == markdown_content:
                files_skipped += 1
            else:
                files_updated += 1
                files_would_change += 1
                if not args.check_dirty:
                    with open(filepath, "w", encoding="utf-8") as wf:
                        wf.write(markdown_content)
        else:
            files_created += 1
            files_would_change += 1
            if not args.check_dirty:
                with open(filepath, "w", encoding="utf-8") as wf:
                    wf.write(markdown_content)

    print(f"Documentation generation completed!")
    print(f"Output directory: {output_dir}")
    print(f"Files created: {files_created}")
    print(f"Files updated: {files_updated}")
    print(f"Files skipped: {files_skipped}")
    print(f"Total commands processed: {len(unique_commands)}")

    if args.check_dirty and files_would_change:
        return 3
    return 0


if __name__ == "__main__":
    exit(main())