"""
Workspace color customization for ATDD projects.

Sets the VS Code workspace title/status bar color via named presets or hex
values.  The chosen color is persisted in .atdd/config.yaml and applied to
the .code-workspace file so that ``atdd init --worktree-layout`` and
``atdd sync`` respect it.

Usage:
    atdd color              # interactive prompt
    atdd color red          # named preset
    atdd color "#D32F2F"    # hex value
"""

import json
import re
from pathlib import Path
from typing import Optional

import yaml

from atdd.coach.utils.repo import find_repo_root


class ColorManager:
    """Manage workspace title/status bar colors."""

    COLOR_PRESETS = {
        "yellow": "#FFC107",
        "blue": "#1976D2",
        "green": "#388E3C",
        "red": "#D32F2F",
        "orange": "#F57C00",
        "purple": "#7B1FA2",
    }

    _HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or find_repo_root()
        self.config_path = self.repo_root / ".atdd" / "config.yaml"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def color(self, value: Optional[str] = None) -> int:
        """Set workspace color from *value* (preset name, hex, or interactive).

        Returns 0 on success, 1 on error.
        """
        if value is None:
            hex_color = self._interactive()
            if hex_color is None:
                return 1
        elif value.lower() in self.COLOR_PRESETS:
            hex_color = self.COLOR_PRESETS[value.lower()]
        elif self._HEX_RE.match(value):
            hex_color = value.upper()
        else:
            print(f"Error: '{value}' is not a known preset or valid hex (#RRGGBB).")
            print(f"Presets: {', '.join(self.COLOR_PRESETS)}")
            return 1

        fg = self._foreground(hex_color)
        self._update_workspace(hex_color, fg)
        self._persist(hex_color)
        print(f"Set workspace color: {hex_color} (foreground: {fg})")
        return 0

    # ------------------------------------------------------------------
    # Interactive mode
    # ------------------------------------------------------------------

    def _interactive(self) -> Optional[str]:
        """Prompt user to pick a preset or enter a hex value."""
        names = list(self.COLOR_PRESETS.keys())
        print("Workspace color presets:")
        for i, name in enumerate(names, 1):
            print(f"  {i}. {name:<8} {self.COLOR_PRESETS[name]}")
        print()

        try:
            choice = input("Enter number, preset name, or hex (#RRGGBB): ").strip()
        except (EOFError, KeyboardInterrupt):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            print("\nAborted.")
            return None

        if not choice:
            print("No selection.")
            return None

        # Number selection
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(names):
                return self.COLOR_PRESETS[names[idx]]
            print(f"Invalid number (1-{len(names)}).")
            return None

        # Preset name
        if choice.lower() in self.COLOR_PRESETS:
            return self.COLOR_PRESETS[choice.lower()]

        # Hex value
        if self._HEX_RE.match(choice):
            return choice.upper()

        print(f"Invalid input: '{choice}'")
        return None

    # ------------------------------------------------------------------
    # WCAG relative-luminance contrast
    # ------------------------------------------------------------------

    @staticmethod
    def _relative_luminance(hex_color: str) -> float:
        """WCAG 2.1 relative luminance from a ``#RRGGBB`` string."""
        r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
        channels = []
        for c in (r, g, b):
            channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    @classmethod
    def _foreground(cls, bg_hex: str) -> str:
        """Return ``#FFFFFF`` or ``#000000`` for best contrast on *bg_hex*."""
        return "#000000" if cls._relative_luminance(bg_hex) > 0.179 else "#FFFFFF"

    # ------------------------------------------------------------------
    # Workspace file update
    # ------------------------------------------------------------------

    def _find_workspace(self) -> Optional[Path]:
        """Locate the .code-workspace file in the parent of repo root."""
        parent = self.repo_root.parent
        for p in parent.iterdir():
            if p.suffix == ".code-workspace" and p.is_file():
                return p
        return None

    def _update_workspace(self, bg: str, fg: str) -> None:
        """Update color keys in the .code-workspace file (if it exists)."""
        ws_path = self._find_workspace()
        if ws_path is None:
            print("No .code-workspace file found — skipping workspace update.")
            print("Run `atdd init --worktree-layout` to create one.")
            return

        try:
            data = json.loads(ws_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            print(f"Warning: could not read {ws_path}: {exc}")
            return

        settings = data.setdefault("settings", {})
        colors = settings.setdefault("workbench.colorCustomizations", {})
        colors["titleBar.activeBackground"] = bg
        colors["titleBar.activeForeground"] = fg
        colors["statusBar.background"] = bg
        colors["statusBar.foreground"] = fg

        ws_path.write_text(json.dumps(data, indent=2) + "\n")
        print(f"Updated: {ws_path}")

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------

    def _persist(self, hex_color: str) -> None:
        """Write hex_color to .atdd/config.yaml → workspace.color."""
        if not self.config_path.exists():
            print(f"Warning: {self.config_path} not found — color not persisted.")
            return

        with open(self.config_path) as f:
            config = yaml.safe_load(f) or {}

        workspace = config.setdefault("workspace", {})
        workspace["color"] = hex_color

        with open(self.config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print(f"Persisted: {self.config_path} (workspace.color: {hex_color})")
