# Synthetic vulnerable Python file for B-SCAN-03 testing
# DO NOT USE IN PRODUCTION — intentionally insecure code

import os
import subprocess
import pickle
import sqlite3

# === INJ-SQL: SQL injection via string concatenation ===
def get_user(username):
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE name = '" + username + "'")
    return cursor.fetchone()

# === INJ-CMD: Command injection via user input ===
def run_command(user_input):
    os.system("grep " + user_input + " /var/log/app.log")
    subprocess.call("ls " + user_input, shell=True)

# === AUTH-HARDCODED: Hardcoded password ===
password = "SuperSecret123!"
api_key = "sk-1234567890abcdef"
DB_PASSWORD = "admin_p@ssw0rd"

# === DESER-UNSAFE: Unsafe deserialization ===
def load_data(raw_bytes):
    return pickle.loads(raw_bytes)

def load_yaml(text):
    import yaml
    return yaml.load(text)

# === AC-PATH-TRAVERSAL: Path traversal ===
def read_file(request):
    filename = request.args.get("file")
    with open("/data/" + filename) as f:
        return f.read()

# === CRYPTO-HARDCODED-KEY: Hardcoded crypto key ===
from Crypto.Cipher import AES
cipher = AES.new(b'ThisIsASecretKey', AES.MODE_ECB)

# === MEM-BUFFER (not applicable to Python, but keep for coverage) ===

# === DATA-LOG-SENSITIVE: Logging sensitive data ===
import logging
logger = logging.getLogger(__name__)
def login(user, password_input):
    logger.info("Login attempt with password: " + password_input)

# === ERR-IGNORE: Silently ignored exception ===
try:
    risky_operation = 1 / 0
except:
    pass

# === CRYPTO-RANDOM: Insecure random ===
import random
session_token = random.randint(0, 999999)
