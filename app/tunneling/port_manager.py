import socket
import logging
from typing import List, Dict, Set, Optional, Tuple, Any

logger = logging.getLogger("IRD_PortManager")

class PortManager:
    """
    Manages local port availability, collision checking, and allocation for SSH tunnels.
    """

    @staticmethod
    def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
        """
        Checks if local port is currently occupied/bound by another process.
        """
        if not (1 <= port <= 65535):
            return True

        # Check by attempting to bind to local port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            try:
                sock.bind((host, port))
                return False  # Successfully bound, port is free
            except (OSError, socket.error):
                return True   # Port occupied or prohibited

    @staticmethod
    def verify_port_available(port: int, host: str = "127.0.0.1") -> bool:
        """
        Returns True if the specified local port is free for use.
        """
        return not PortManager.is_port_in_use(port, host)

    @staticmethod
    def allocate_next_available_port(start_port: int = 18001, occupied_ports: Optional[Set[int]] = None) -> int:
        """
        Finds and returns the lowest available TCP port starting at `start_port`.
        """
        if occupied_ports is None:
            occupied_ports = set()

        candidate = start_port
        while candidate <= 65535:
            if candidate not in occupied_ports and not PortManager.is_port_in_use(candidate):
                return candidate
            candidate += 1

        raise RuntimeError(f"No available TCP ports found starting from {start_port}.")

    @staticmethod
    def check_site_port_collisions(sites: List[Any]) -> Tuple[bool, List[str]]:
        """
        Validates site list for local port conflicts.
        Returns (has_conflicts, conflict_messages).
        """
        port_map: Dict[int, List[str]] = {}
        for site in sites:
            p = getattr(site, 'local_port', 0) or 18001
            name = getattr(site, 'name', 'Unknown')
            if p not in port_map:
                port_map[p] = []
            port_map[p].append(name)

        conflicts = []
        has_conflicts = False
        for port, site_names in port_map.items():
            if len(site_names) > 1:
                has_conflicts = True
                conflicts.append(f"Port {port} conflict: assigned to multiple sites ({', '.join(site_names)})")

        return has_conflicts, conflicts

port_manager = PortManager()
