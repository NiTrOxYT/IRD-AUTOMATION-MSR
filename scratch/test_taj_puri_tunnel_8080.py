import sys, os
sys.path.insert(0, os.path.abspath("."))
import asyncio
import urllib.request
from app.tunneling.tunnel_manager import tunnel_manager
from app.database.db import get_dth_site_by_name, update_dth_site
from types import SimpleNamespace

# Update TAJ Puri site_port to 8080 in DB
site = get_dth_site_by_name("TAJ Puri Resort & Spa, Odisha")
print("Original site_port:", site.get("site_port"))
update_dth_site(site["id"], {"site_port": 8080, "remote_port": 8080, "portal_url": f"http://localhost:{site['local_port']}/zmp/main-menu.do"})

site_updated = get_dth_site_by_name("TAJ Puri Resort & Spa, Odisha")
print("Updated site_port:", site_updated.get("site_port"))

site_obj = SimpleNamespace(**site_updated)

async def test():
    print("Starting tunnel via Plink...")
    t_ok, t_msg, logs = await tunnel_manager.start_and_verify_tunnel(site_obj, timeout_seconds=25, keep_running=True)
    print("Tunnel OK:", t_ok, "| Msg:", t_msg)
    if not t_ok:
        return

    # Now test fetching http://localhost:18001/zmp/login.do and http://localhost:18001/zmp/main-menu.do
    for url in [f"http://localhost:{site['local_port']}/zmp/login.do", f"http://localhost:{site['local_port']}/zmp/main-menu.do"]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                print(f"SUCCESS loading {url} -> Status: {resp.status}")
                body = resp.read(300).decode("utf-8", "ignore")
                print("Body snippet:", body[:150].replace("\n", " "))
        except Exception as e:
            print(f"FAILED loading {url} -> {e}")

asyncio.run(test())
