"""
Session management for ATDD sessions.

Manages session files in atdd-sessions/ directory:
- Create new sessions from template
- List sessions from manifest
- Archive completed sessions

Usage:
    atdd session new my-feature                    # Create SESSION-NN-my-feature.md
    atdd session new my-feature --type migration   # Specify session type
    atdd session list                              # List all sessions
    atdd session archive 01                        # Archive SESSION-01-*.md

Convention: src/atdd/coach/conventions/session.convention.yaml
"""
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml


class SessionManager:
    """Manage session files."""

    VALID_TYPES = {
        "implementation",
        "migration",
        "refactor",
        "analysis",
        "planning",
        "cleanup",
        "tracking",
    }

    def __init__(self, target_dir: Optional[Path] = None):
        """
        Initialize the SessionManager.

        Args:
            target_dir: Target directory containing atdd-sessions/. Defaults to cwd.
        """
        self.target_dir = target_dir or Path.cwd()
        self.sessions_dir = self.target_dir / "atdd-sessions"
        self.archive_dir = self.sessions_dir / "archive"
        self.atdd_config_dir = self.target_dir / ".atdd"
        self.manifest_file = self.atdd_config_dir / "manifest.yaml"

        # Package template location
        self.package_root = Path(__file__).parent.parent  # src/atdd/coach
        self.template_source = self.package_root / "templates" / "SESSION-TEMPLATE.md"

    def _check_initialized(self) -> bool:
        """Check if ATDD is initialized."""
        if not self.sessions_dir.exists():
            print(f"Error: ATDD not initialized. Run 'atdd init' first.")
            print(f"Expected: {self.sessions_dir}")
            return False
        if not self.manifest_file.exists():
            print(f"Error: Manifest not found. Run 'atdd init' first.")
            print(f"Expected: {self.manifest_file}")
            return False
        return True

    def _load_manifest(self) -> Dict[str, Any]:
        """Load the manifest.yaml file."""
        with open(self.manifest_file) as f:
            return yaml.safe_load(f) or {}

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        """Save the manifest.yaml file."""
        with open(self.manifest_file, "w") as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

    def _get_next_session_number(self, manifest: Dict[str, Any]) -> str:
        """Get the next available session number."""
        sessions = manifest.get("sessions", [])
        if not sessions:
            return "01"

        # Find the highest session number
        max_num = 0
        for session in sessions:
            session_id = session.get("id", "00")
            try:
                num = int(session_id)
                if num > max_num:
                    max_num = num
            except ValueError:
                continue

        # Also check for session files not in manifest
        for f in self.sessions_dir.glob("SESSION-*.md"):
            match = re.match(r"SESSION-(\d+)-", f.name)
            if match:
                try:
                    num = int(match.group(1))
                    if num > max_num:
                        max_num = num
                except ValueError:
                    continue

        return f"{max_num + 1:02d}"

    def _slugify(self, text: str) -> str:
        """Convert text to kebab-case slug."""
        # Convert to lowercase
        slug = text.lower()
        # Replace spaces and underscores with hyphens
        slug = re.sub(r"[\s_]+", "-", slug)
        # Remove non-alphanumeric characters except hyphens
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        # Remove consecutive hyphens
        slug = re.sub(r"-+", "-", slug)
        # Remove leading/trailing hyphens
        slug = slug.strip("-")
        return slug

    def new(self, slug: str, session_type: str = "implementation") -> int:
        """
        Create new session from template.

        Args:
            slug: Session slug (will be converted to kebab-case).
            session_type: Type of session (implementation, migration, etc.).

        Returns:
            0 on success, 1 on error.
        """
        if not self._check_initialized():
            return 1

        # Validate session type
        if session_type not in self.VALID_TYPES:
            print(f"Error: Invalid session type '{session_type}'")
            print(f"Valid types: {', '.join(sorted(self.VALID_TYPES))}")
            return 1

        # Load manifest
        manifest = self._load_manifest()

        # Get next session number
        session_num = self._get_next_session_number(manifest)

        # Slugify the name
        slug = self._slugify(slug)
        if not slug:
            print("Error: Invalid slug - results in empty string")
            return 1

        # Generate filename
        filename = f"SESSION-{session_num}-{slug}.md"
        session_path = self.sessions_dir / filename

        if session_path.exists():
            print(f"Error: Session already exists: {session_path}")
            return 1

        # Read template
        if not self.template_source.exists():
            print(f"Error: Template not found: {self.template_source}")
            return 1

        template_content = self.template_source.read_text()

        # Replace placeholders in template
        today = date.today().isoformat()
        title = slug.replace("-", " ").title()

        # Replace frontmatter placeholders
        content = template_content
        content = re.sub(r'session:\s*"\{NN\}"', f'session: "{session_num}"', content)
        content = re.sub(r'title:\s*"\{Title\}"', f'title: "{title}"', content)
        content = re.sub(r'date:\s*"\{YYYY-MM-DD\}"', f'date: "{today}"', content)
        content = re.sub(r'type:\s*"\{type\}"', f'type: "{session_type}"', content)

        # Replace markdown header
        content = re.sub(
            r"# SESSION-\{NN\}: \{Title\}",
            f"# SESSION-{session_num}: {title}",
            content,
        )

        # Write session file
        session_path.write_text(content)
        print(f"Created: {session_path}")

        # Update manifest
        session_entry = {
            "id": session_num,
            "slug": slug,
            "file": filename,
            "type": session_type,
            "status": "INIT",
            "created": today,
            "archived": None,
        }

        if "sessions" not in manifest:
            manifest["sessions"] = []
        manifest["sessions"].append(session_entry)

        self._save_manifest(manifest)
        print(f"Updated: {self.manifest_file}")

        print(f"\nSession created: {filename}")
        print(f"  Type: {session_type}")
        print(f"  Status: INIT")
        print(f"\nNext: Edit {session_path} and update status to PLANNED")

        return 0

    def list(self) -> int:
        """
        List sessions from manifest.

        Returns:
            0 on success, 1 on error.
        """
        if not self._check_initialized():
            return 1

        manifest = self._load_manifest()
        sessions = manifest.get("sessions", [])

        if not sessions:
            print("No sessions found.")
            print("Create one with: atdd session new my-feature")
            return 0

        # Print header
        print("\n" + "=" * 70)
        print("ATDD Sessions")
        print("=" * 70)
        print(f"{'ID':<4} {'Status':<10} {'Type':<15} {'File':<40}")
        print("-" * 70)

        # Group by status
        active = []
        archived = []

        for session in sessions:
            if session.get("archived"):
                archived.append(session)
            else:
                active.append(session)

        # Print active sessions
        for session in active:
            session_id = session.get("id", "??")
            status = session.get("status", "UNKNOWN")
            session_type = session.get("type", "unknown")
            filename = session.get("file", "unknown")

            print(f"{session_id:<4} {status:<10} {session_type:<15} {filename:<40}")

        if archived:
            print("\n--- Archived ---")
            for session in archived:
                session_id = session.get("id", "??")
                status = session.get("status", "UNKNOWN")
                session_type = session.get("type", "unknown")
                filename = session.get("file", "unknown")

                print(f"{session_id:<4} {status:<10} {session_type:<15} {filename:<40}")

        print("-" * 70)
        print(f"Total: {len(sessions)} sessions ({len(active)} active, {len(archived)} archived)")

        return 0

    def archive(self, session_id: str) -> int:
        """
        Move session to archive/.

        Args:
            session_id: Session ID (e.g., "01" or "1").

        Returns:
            0 on success, 1 on error.
        """
        if not self._check_initialized():
            return 1

        # Normalize session ID to 2-digit
        try:
            session_num = int(session_id)
            session_id_normalized = f"{session_num:02d}"
        except ValueError:
            print(f"Error: Invalid session ID '{session_id}'")
            return 1

        # Load manifest
        manifest = self._load_manifest()
        sessions = manifest.get("sessions", [])

        # Find session in manifest
        session_entry = None
        session_index = None
        for i, s in enumerate(sessions):
            if s.get("id") == session_id_normalized:
                session_entry = s
                session_index = i
                break

        if session_entry is None:
            print(f"Error: Session {session_id_normalized} not found in manifest")
            return 1

        if session_entry.get("archived"):
            print(f"Error: Session {session_id_normalized} is already archived")
            return 1

        # Find session file
        filename = session_entry.get("file")
        session_path = self.sessions_dir / filename

        if not session_path.exists():
            # Try to find file by pattern
            pattern = f"SESSION-{session_id_normalized}-*.md"
            matches = list(self.sessions_dir.glob(pattern))
            if matches:
                session_path = matches[0]
                filename = session_path.name
            else:
                print(f"Error: Session file not found: {filename}")
                return 1

        # Ensure archive directory exists
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # Move file to archive
        archive_path = self.archive_dir / filename
        shutil.move(str(session_path), str(archive_path))
        print(f"Moved: {session_path} -> {archive_path}")

        # Update manifest
        session_entry["archived"] = date.today().isoformat()
        session_entry["file"] = f"archive/{filename}"
        manifest["sessions"][session_index] = session_entry

        self._save_manifest(manifest)
        print(f"Updated: {self.manifest_file}")

        print(f"\nSession {session_id_normalized} archived successfully")

        return 0

    def sync(self) -> int:
        """
        Sync manifest with actual session files.

        Scans atdd-sessions/ and updates manifest to match actual files.

        Returns:
            0 on success, 1 on error.
        """
        if not self._check_initialized():
            return 1

        manifest = self._load_manifest()
        existing_sessions = {s.get("file"): s for s in manifest.get("sessions", [])}

        # Scan for session files
        found_files = set()
        new_sessions = []

        # Scan main directory
        for f in self.sessions_dir.glob("SESSION-*.md"):
            if f.name == "SESSION-TEMPLATE.md":
                continue

            found_files.add(f.name)

            if f.name not in existing_sessions:
                # Parse filename to extract info
                match = re.match(r"SESSION-(\d+)-(.+)\.md", f.name)
                if match:
                    session_id = match.group(1)
                    slug = match.group(2)

                    new_sessions.append({
                        "id": session_id,
                        "slug": slug,
                        "file": f.name,
                        "type": "unknown",
                        "status": "UNKNOWN",
                        "created": date.today().isoformat(),
                        "archived": None,
                    })

        # Scan archive directory
        if self.archive_dir.exists():
            for f in self.archive_dir.glob("SESSION-*.md"):
                archive_path = f"archive/{f.name}"
                found_files.add(archive_path)

                if archive_path not in existing_sessions:
                    match = re.match(r"SESSION-(\d+)-(.+)\.md", f.name)
                    if match:
                        session_id = match.group(1)
                        slug = match.group(2)

                        new_sessions.append({
                            "id": session_id,
                            "slug": slug,
                            "file": archive_path,
                            "type": "unknown",
                            "status": "UNKNOWN",
                            "created": date.today().isoformat(),
                            "archived": date.today().isoformat(),
                        })

        # Add new sessions to manifest
        if new_sessions:
            manifest["sessions"] = manifest.get("sessions", []) + new_sessions
            print(f"Added {len(new_sessions)} new session(s) to manifest")

        # Report missing files
        for filename, session in existing_sessions.items():
            if filename not in found_files and f"archive/{filename}" not in found_files:
                print(f"Warning: Session file not found: {filename}")

        self._save_manifest(manifest)
        print(f"Manifest synced: {self.manifest_file}")

        return 0
