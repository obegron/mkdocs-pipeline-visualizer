import os
from packaging import version


def semantic_version_key(version_str):
    try:
        return version.parse(version_str or "0.0.0")
    except version.InvalidVersion:
        return version.parse("0.0.0")


def add_to_nav(nav_section, resources):
    for resource_name, versions in sorted(resources.items()):
        sorted_versions = sorted(
            [(v[0], v[1]) for v in versions],
            key=lambda x: semantic_version_key(x[0]),
            reverse=True,
        )

        if len(sorted_versions) == 1:
            nav_section.append({resource_name: sorted_versions[0][1]})
        else:
            version_dict = {}
            for ver, path in sorted_versions:
                version_name = f"{resource_name} v{ver}" if ver else resource_name
                version_dict[version_name] = path
            nav_section.append({resource_name: version_dict})


def remove_empty_sections(nav_list):
    items_to_remove = []
    for item in nav_list:
        if isinstance(item, dict):
            for _, value in item.items():
                if isinstance(value, list):
                    remove_empty_sections(value)
                    if not value:
                        items_to_remove.append(item)

    for item in items_to_remove:
        nav_list.remove(item)


def find_or_create_section(nav, section_name):
    def find_section_recursive(nav_item, section_name):
        if isinstance(nav_item, list):
            for item in nav_item:
                result = find_section_recursive(item, section_name)
                if result is not None:
                    return result
        elif isinstance(nav_item, dict):
            for key, value in nav_item.items():
                if key == section_name and isinstance(value, list) and not value:
                    return value
                result = find_section_recursive(value, section_name)
                if result is not None:
                    return result
        return None

    result = find_section_recursive(nav, section_name)
    if result is not None:
        return result

    new_section = {section_name: []}
    nav.append(new_section)
    return new_section[section_name]


def get_group(path, offset):
    if not offset:
        return ""

    path = path.replace("\\", "/")
    parts = os.path.dirname(path).split("/")

    if len(parts) <= 1:
        return ""

    start, end = offset
    if end is None:
        end = len(parts)

    if end < 0:
        end = len(parts) + end

    if start >= len(parts) or end > len(parts) or start < 0:
        return ""

    return "/".join(parts[start:end])


def get_relative_path(from_path, to_path):
    from_path = from_path.replace("\\", "/").rstrip("/")
    to_path = to_path.replace("\\", "/").rstrip("/")

    from_parts = from_path.split("/")
    to_parts = to_path.split("/")

    from_dir = from_parts[:-1]
    to_dir = to_parts[:-1]

    common_length = 0
    for f, t in zip(from_dir, to_dir):
        if f != t:
            break
        common_length += 1

    up_levels = len(from_dir) - common_length
    remaining_path = to_parts[common_length:]
    relative_path = "../" * up_levels + "/".join(remaining_path)

    if not relative_path.endswith(".md"):
        relative_path += ".md"

    return relative_path
