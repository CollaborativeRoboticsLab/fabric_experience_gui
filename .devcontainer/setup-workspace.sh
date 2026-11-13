#!/usr/bin/env bash
set -euo pipefail

gui_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
workspace="${FABRIC_GUI_WS:-$HOME/fabric_gui_ws}"
mkdir -p "$workspace/src"

check_checkout() {
    local path="$1" revision="$2" actual root
    if [[ ! -e "$path" ]]; then
        return 0
    fi
    root="$(git -C "$path" rev-parse --show-toplevel 2>/dev/null || true)"
    if [[ -z "$root" || "$(cd "$root" && pwd -P)" != "$(cd "$path" && pwd -P)" ]]; then
        printf 'Not a separate Git checkout: %s\n' "$path" >&2
        return 1
    fi
    actual="$(git -C "$path" rev-parse HEAD)"
    if [[ "$actual" != "$revision" || -n "$(git -C "$path" status --porcelain --untracked-files=normal)" ]]; then
        printf 'Dependency checkout is modified or not pinned to %s: %s\n' "$revision" "$path" >&2
        return 1
    fi
}

check_dependencies() {
    check_checkout "$workspace/src/fabric" 3abdebd104f7af8a8f8ff97ff34b1c2b197e1e1c
    check_checkout "$workspace/src/capabilities2" 6ef1309adf60b7b5520c79802accebe43fa3bbff
    check_checkout "$workspace/src/prompt_tools" bc573505126d62ce944f67d12d88782c849609bb
}

check_dependencies
if [[ ! -d "$workspace/src/fabric" || ! -d "$workspace/src/capabilities2" || ! -d "$workspace/src/prompt_tools" ]]; then
    vcs import --skip-existing --input "$gui_root/dependencies.repos" "$workspace/src"
fi
check_dependencies
if [[ -f "$workspace/src/fabric/fabric_experience_gui/package.xml" ]]; then
    printf 'The Fabric dependency also contains fabric_experience_gui; select a dependency revision without the duplicate.\n' >&2
    exit 1
fi

set +u
source /opt/ros/jazzy/setup.bash
set -u
cd "$workspace"
mapfile -t package_paths < <(colcon list --base-paths "$gui_root" "$workspace/src" --paths-only --packages-up-to fabric_experience_gui)
if [[ ${#package_paths[@]} -eq 0 ]]; then
    printf 'Could not discover the GUI package and dependencies.\n' >&2
    exit 1
fi
if [[ ! -e /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
    sudo rosdep init
fi
rosdep update
rosdep install --from-paths "${package_paths[@]}" --ignore-src --rosdistro jazzy -y
colcon build --base-paths "$gui_root" "$workspace/src" --packages-up-to fabric_experience_gui
printf 'Workspace ready. Source /opt/ros/jazzy/setup.bash and %s/install/setup.bash.\n' "$workspace"