import sys, os
sys.path.insert(0, os.path.abspath("."))
import subprocess
from app.database.db import get_office_ssh_password_decrypted

ssh_pass = get_office_ssh_password_decrypted()
python_remote = '''
import urllib.request, ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
for path in ["/zmp/login.do", "/zmp/main-menu.do", "/"]:
    try:
        url = f"http://128.185.59.82:8080{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
            print(f"{path} -> STATUS {resp.status}, length: {len(resp.read(200))}")
    except Exception as e:
        print(f"{path} -> ERROR: {e}")
'''

cmd = [
    r"C:\IRD AUTO\tools\putty\plink.exe", "-batch", "-ssh", "-P", "22",
    "-l", "sourik", "-pw", ssh_pass,
    "111.93.205.187",
    f"python3 -c '{python_remote}'"
]
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
out, err = proc.communicate(timeout=15)
print("STDOUT:", out)
print("STDERR:", err)
