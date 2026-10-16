"""TVWCS's login screen, the part without GTK: talking to greetd, the users to show, and what the greeter remembers.

greetd's protocol (greetd-ipc(7)) is JSON messages over the Unix socket named by GREETD_SOCK, each preceded by its
length as a 32-bit number in the machine's byte order. Logging in is create_session (the user), then one
post_auth_message_response for each question PAM asks (usually just the password), then start_session with the
command to run; greetd starts it once the greeter has exited."""
from __future__ import annotations
import json, os, pwd, socket, struct
from pathlib import Path
from tvwcs import loginscreen

class GreetdError(Exception): pass

class Greetd:
    """A connection to greetd. Each method sends one request and returns greetd's answer (a dict)."""
    def __init__(self, sock_path=None, sock=None):
        if sock is None:
            sock_path=sock_path or os.environ.get("GREETD_SOCK")
            if not sock_path: raise GreetdError("GREETD_SOCK is not set: the login screen must be started by greetd.")
            sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); sock.connect(sock_path)
        self.sock=sock
    def close(self):
        try: self.sock.close()
        except OSError: pass
    def _recv(self, n):
        data=b""
        while len(data)<n:
            chunk=self.sock.recv(n-len(data))
            if not chunk: raise GreetdError("greetd closed the connection.")
            data+=chunk
        return data
    def request(self, message):
        body=json.dumps(message).encode("utf-8")
        self.sock.sendall(struct.pack("=I",len(body))+body)
        (n,)=struct.unpack("=I",self._recv(4))
        return json.loads(self._recv(n).decode("utf-8"))
    def create_session(self, username): return self.request({"type":"create_session","username":username})
    def answer(self, response=None):
        msg={"type":"post_auth_message_response"}
        if response is not None: msg["response"]=response
        return self.request(msg)
    def start_session(self, cmd, env=()): return self.request({"type":"start_session","cmd":list(cmd),"env":list(env)})
    def cancel(self): return self.request({"type":"cancel_session"})

def log_in(greetd, username, password, cmd, env=()):
    """Log `username` in with `password` and have greetd start `cmd`. Returns "" when it worked, else why not (for
    people). PAM's questions are answered in turn: the password for a hidden one, nothing for information. A session
    that failed half-way is cancelled, so the next try starts afresh."""
    try:
        reply=greetd.create_session(username); answered=False
        for _ in range(8):
            kind=reply.get("type")
            if kind=="success": break
            if kind=="error":
                greetd.cancel()
                if reply.get("error_type")=="auth_error": return "That password is not right. Try again."
                return reply.get("description") or "Could not log in."
            if kind!="auth_message":
                greetd.cancel(); return "greetd answered something unexpected."
            mtype=reply.get("auth_message_type")
            if mtype in ("secret","visible"):
                if answered and mtype=="secret":   # PAM asks again (a new password is needed, say): not here
                    greetd.cancel(); return (reply.get("auth_message") or "").strip() or "The password must be changed first."
                reply=greetd.answer(password); answered=True
            else:   # info or error: read, nothing to answer
                if mtype=="error" and reply.get("auth_message"):
                    text=reply["auth_message"]; greetd.answer(); greetd.cancel(); return text.strip()
                reply=greetd.answer()
        else:
            greetd.cancel(); return "Logging in asked too many questions."
        reply=greetd.start_session(cmd,env)
        if reply.get("type")!="success":
            greetd.cancel(); return reply.get("description") or "The session could not be started."
        return ""
    except (OSError,ValueError,GreetdError,struct.error) as exc:
        return f"Could not reach greetd: {exc}"

# ---------------------------------------------------------------------- who can log in
def users(entries=None, shells_file="/etc/shells") -> list:
    """The people who can log in: [(login, full name)], ordinary accounts (UID 1000 to 59999) with a real shell."""
    try: shells={s.strip() for s in Path(shells_file).read_text().splitlines() if s.strip() and not s.startswith("#")}
    except OSError: shells=set()
    out=[]
    for e in (pwd.getpwall() if entries is None else entries):
        if not 1000<=e.pw_uid<60000: continue
        if e.pw_shell.endswith(("nologin","false")) or (shells and e.pw_shell not in shells): continue
        out.append((e.pw_name,(e.pw_gecos or "").split(",")[0].strip() or e.pw_name))
    return sorted(out,key=lambda u:u[1].casefold())

# ---------------------------------------------------------------------- what it remembers
KEYBOARDS=("full","digits")
class Memory:
    """The last user, and each user's last session and on-screen keyboard (the full one until the number pad is used)."""
    def __init__(self, folder=None):
        self.file=Path(folder or loginscreen.path(loginscreen.STATE_DIR))/"state.json"
        try: raw=json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError,ValueError): raw={}
        self.last_user=raw.get("last_user","") if isinstance(raw.get("last_user"),str) else ""
        self.people={k:v for k,v in (raw.get("users") or {}).items() if isinstance(k,str) and isinstance(v,dict)} if isinstance(raw.get("users"),dict) else {}
    def session(self, user): return str(self.people.get(user,{}).get("session",""))
    def keyboard(self, user):
        k=self.people.get(user,{}).get("keyboard"); return k if k in KEYBOARDS else "full"
    def remember(self, user, session=None, keyboard=None):
        p=self.people.setdefault(user,{})
        if session is not None: p["session"]=session
        if keyboard in KEYBOARDS: p["keyboard"]=keyboard
        self.last_user=user; self.save()
    def save(self):
        try:
            self.file.parent.mkdir(parents=True,exist_ok=True); tmp=self.file.with_suffix(".tmp")
            tmp.write_text(json.dumps({"last_user":self.last_user,"users":self.people},indent=1),encoding="utf-8"); os.replace(tmp,self.file)
        except OSError: pass   # a login screen that cannot remember still logs in
