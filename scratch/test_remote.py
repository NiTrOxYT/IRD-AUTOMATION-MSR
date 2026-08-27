import subprocess

plink = r"tools\putty\plink.exe"
host = "111.93.205.187"
user = "sourik"
password = "s0urik@@"
target_ip = "14.142.185.130"

remote_cmd = (
    "python3 -c \"import urllib.request, ssl; "
    "ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE; "
    "req=urllib.request.Request('http://14.142.185.130:8080/', headers={'User-Agent': 'Mozilla/5.0'}); "
    "resp=urllib.request.urlopen(req, context=ctx, timeout=5); "
    "print('STATUS:', resp.status); print('BODY:', resp.read(200).decode('utf-8', 'ignore'))\""
)

cmd = [plink, "-batch", "-ssh", "-P", "22", "-l", user, "-pw", password, host, remote_cmd]

p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
out, err = p.communicate(timeout=25)
print("STDOUT:", out)
print("STDERR:", err)
