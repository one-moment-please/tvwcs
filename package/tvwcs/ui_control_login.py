"""Settings: TVWCS's login screen (on the Features page) and the User page's automatic login, password and name.
The system side is loginscreen.py and account.py; the changes that need root go through the window's run_as_root."""
from __future__ import annotations
import shutil
from tvwcs import account, features, loginscreen
from tvwcs.model import CONFIG_HOME
from tvwcs.ui_control import in_background

CONFIG_FILE=CONFIG_HOME/"tvwcs"/"config.json"
SETUP_FILE=CONFIG_HOME/"tvwcs"/"setup"

def me() -> str: return account.read().login
def wm() -> str: return "sway" if features.sway() else "i3"
def setup() -> str:
    try: return SETUP_FILE.read_text(encoding="utf-8").strip()
    except OSError: return ""
def my_session() -> str:
    """The session that starts TVWCS in the window manager running now."""
    return loginscreen.tvwcs_session(loginscreen.sessions(),wm(),setup())

def run_root(page, args, label, done, packages=()):
    """Run `python3 -m tvwcs.loginscreen args` as root (installing `packages` first), then done(problem or "")."""
    lines=[]
    def finished(code, tail):
        page.set_status("")
        if code: done(("\n".join(lines[-6:]) or tail or f"{label} did not work.").strip()); return
        done("")
    if packages and not shutil.which("apt-get"):
        done(f"This needs {', '.join(packages)} (the Debian names). Install them with your package manager first."); return
    page.set_status(f"{label}…")
    page.win.run_as_root(loginscreen.root_command(args,packages),label,lines.append,finished)

# ====================================================================== Features > Login screen
def draw_login_screen(page, st):
    """The Features page's LOGIN SCREEN section: st is loginscreen.status()."""
    page.section("LOGIN SCREEN")
    if st["ours"]:
        value="Needs updating" if st["outdated"] or st["look_changed"] else "On"
        detail=("Its copy of TVWCS is older than this one. " if st["outdated"] else "Its colours differ from TVWCS's now. " if st["look_changed"] else "")+\
               "TVWCS's own login screen: pick who logs in, type the password with the remote, and start i3 or sway."
    else:
        value="Off"; cur=st["current"]
        detail=(f"Now: {loginscreen.name(cur)}. " if cur else "There is no login screen now. ")+"Turning it on shows TVWCS's own login screen, which can start i3 or sway."
    page.row("TVWCS login screen",value,lambda:change_login_screen(page,st),detail=detail,ident="feature:login",
             value_css="state-on" if st["ours"] and value=="On" else "setting-value")
    if not st["ours"] and features.sway() and not loginscreen.wayland_ok(st["current"]):
        page.note(f"{loginscreen.name(st['current'])} cannot start sway reliably. TVWCS's login screen, or SDDM, can.","error")

def change_login_screen(page, st):
    if not st["ours"]: turn_login_on(page,st); return
    options=[("keep","Keep it on")]
    if st["outdated"] or st["look_changed"]: options.append(("update","Update it to this version and these colours"))
    options.append(("off",f"Turn it off ({'back to '+loginscreen.name(st['fallback']) if st['fallback'] else 'there is no other login screen'})"))
    def picked(key):
        if key=="update": update_login_screen(page)
        elif key=="off": turn_login_off(page,st)
    page.win.choose_option("TVWCS login screen",options,"keep",picked)

def _carried_autologin():
    """The automatic login to keep when the login screen changes: this user's, when it is on now."""
    who,_sid=loginscreen.autologin()
    return (who,my_session()) if who and who==me() else None

def turn_login_on(page, st):
    cur=st["current"]; missing=st["packages"]; auto=_carried_autologin()
    text=(f"TVWCS's login screen replaces {loginscreen.name(cur)} from the next start. {loginscreen.name(cur)} stays installed, and "
          "turning this off goes back to it." if cur else "TVWCS's login screen shows from the next start. Turning it off goes back to having none.")
    if auto: text+=f" {auto[0]} is still logged in automatically at start-up; the login screen shows after logging out."
    if missing: text+=f" It needs {', '.join(missing)}, which will be installed now."
    args=["enable","--config",str(CONFIG_FILE),"--previous",cur]+(["--autologin",*auto] if auto else [])
    def done(problem):
        if problem: page.win.notice("TVWCS login screen",problem); return
        if auto and not cur: loginscreen.set_start_lines("")   # the console's start lines are greetd's job now
        page.win.notice("TVWCS login screen","It shows from the next start.",lambda:page.refresh(quiet=True))
    page.win.confirm("Turn on TVWCS's login screen?",text+" It asks for your password.","Turn on",
                     lambda:run_root(page,args,"Turning on the login screen",done,missing),danger=False)

def update_login_screen(page):
    def done(problem):
        if problem: page.win.notice("TVWCS login screen",problem)
        page.refresh(quiet=True)
    run_root(page,["update","--config",str(CONFIG_FILE)],"Updating the login screen",done)

def turn_login_off(page, st):
    fb=st["fallback"]; auto=_carried_autologin(); sway=features.sway()
    def go_to(unit, packages=()):
        keep=auto if auto and loginscreen.autologin_supported(unit or "") else None
        args=["disable","--to",unit]+(["--autologin",*keep] if keep else [])
        def done(problem):
            if problem: page.win.notice("TVWCS login screen",problem); return
            if not unit and keep: loginscreen.set_start_lines(wm())
            after=f"From the next start, the computer uses {loginscreen.name(unit)}." if unit else \
                  f"From the next start, {keep[0]} is logged in automatically and {wm()} starts on the first console." if keep else \
                  "From the next start, there is no login screen."
            if auto and not keep: after+=f" The automatic login could not be kept: set it in {loginscreen.name(unit)}'s own settings."
            page.win.notice("TVWCS login screen",after,lambda:page.refresh(quiet=True))
        run_root(page,args,"Changing the login screen",done,packages)
    def standard():
        choices=[("sddm","SDDM (it can start i3 and sway)")]+([] if sway else [("lightdm","LightDM (i3 only: it cannot start sway reliably)")])
        def picked(unit):
            pk=list(loginscreen.STANDARD[unit])
            page.win.confirm(f"Install {loginscreen.name(unit)}?",f"This installs {', '.join(pk)} and uses it from the next start, "
                             "instead of TVWCS's login screen. It asks for your password.","Install",lambda:go_to(unit,pk),danger=False)
        page.win.choose_option("Which login screen?",choices,choices[0][0],picked)
    if fb and sway and not loginscreen.wayland_ok(fb):
        def picked(key):
            if key=="standard": standard()
            elif key=="fallback": go_to(fb)
        page.win.choose_option(f"{loginscreen.name(fb)} cannot start sway",
                               [("standard","Install a login screen that can (SDDM)"),("fallback",f"Go back to {loginscreen.name(fb)} anyway"),("cancel","Keep TVWCS's login screen")],
                               "standard",picked)
        return
    if fb:
        page.win.confirm(f"Go back to {loginscreen.name(fb)}?",f"From the next start the computer uses {loginscreen.name(fb)}, the login screen "
                         "it had before. It asks for your password.","Go back",lambda:go_to(fb),danger=False)
        return
    def picked(key):
        if key=="none":
            page.win.confirm("No login screen?",f"From the next start, the computer logs {me()} in by itself and starts {wm()} with TVWCS, "
                             "with no password. Anyone who switches it on gets your session. It asks for your password now.","No login screen",
                             lambda:_no_screen(),danger=True)
        elif key=="standard": standard()
    def _no_screen():
        nonlocal auto
        auto=(me(),my_session()); go_to("")
    page.win.choose_option("No other login screen is installed",
                           [("none",f"None: log {me()} in automatically and start TVWCS"),("standard","Install a standard login screen"),
                            ("cancel","Keep TVWCS's login screen")],"none",picked)

# ====================================================================== User
def read_user():
    a=account.read(); cur=loginscreen.current(); who,_sid=loginscreen.autologin()
    return (a,cur,who,loginscreen.autologin_supported(cur))

def draw_user(page, state):
    a,cur,who,supported=state
    page.section("ACCOUNT")
    page.row("Name",a.full_name or "Not set",lambda:change_name(page,a),detail="Shown on the login screen",ident="user:name")
    page.row("User name",a.login,None,detail="Used to log in and for the home folder; it cannot be changed here",ident="user:login")
    page.row("Password","Change",lambda:change_password(page),detail="Asks for the current one first",ident="user:password")
    page.row("Administrator","Yes" if a.admin else "No",None,
             detail="Can install software and change the system (in the sudo group)" if a.admin else "Changes to the system need an administrator's password",ident="user:admin")
    page.section("LOGGING IN")
    page.row("Login screen",loginscreen.name(cur) if cur else "None",lambda:(page.win.select_tab("features"),page.win.enter_page()),
             detail="Change it in Features",ident="user:screen")
    if not supported:
        page.row("Log in automatically","Not here",None,detail=f"Set it in {loginscreen.name(cur)}'s own settings",ident="user:auto"); return
    mine=who==a.login
    value="On" if mine else f"On for {who}" if who else "Off"
    page.row("Log in automatically",value,lambda:toggle_autologin(page,a,cur,mine),ident="user:auto",value_css="state-on" if mine else "setting-value",
             detail=("The login screen shows after logging out" if cur=="tvwcs" else "At start-up, without a password"))
    page.note("With it on, the computer logs you in and starts TVWCS when it is switched on, like a TV. Anyone who switches it on "
              "then gets your session without a password."+(" Off, the login screen asks who is watching." if cur=="tvwcs" else ""))

def toggle_autologin(page, a, cur, mine):
    turning_on=not mine
    session=my_session()
    args=["autologin",a.login,session] if turning_on else ["autologin","--off"]
    def done(problem):
        if problem: page.win.notice("Log in automatically",problem); return
        if cur=="": loginscreen.set_start_lines(wm() if turning_on else "")
        page.refresh(quiet=True)
    if turning_on:
        page.win.confirm("Log in automatically?",f"From the next start, the computer logs {a.login} in and starts TVWCS without asking for "
                         "a password. It asks for your password now.","Turn on",lambda:run_root(page,args,"Turning on the automatic login",done),danger=False)
    else: run_root(page,args,"Turning off the automatic login",done)

def change_name(page, a):
    def got(name):
        name=" ".join(name.split())
        why=account.valid_full_name(name)
        if why: page.win.notice("Name",why); return
        if name==a.full_name: return
        lines=[]
        def done(code, tail):
            page.set_status("")
            if code: page.win.notice("Name",("\n".join(lines[-4:]) or tail or "The name could not be changed.").strip())
            page.refresh(quiet=True)
        page.set_status("Changing the name…")
        page.win.run_as_root(account.full_name_argv(a.login,name),"Changing your name",lines.append,done)
    page.win.ask_text("Name","Your full name, as the login screen shows it. Changing it asks for your password.",got,a.full_name,ok_label="Save")

def change_password(page):
    def ask_current(error=""):
        page.win.ask_text("Current password","Type the password you use now.",ask_new,secret=True,ok_label="Next",error=error)
    def ask_new(current, error=""):
        if not current: return
        page.win.ask_text("New password","Type the new password.",lambda new:ask_again(current,new),secret=True,ok_label="Next",error=error)
    def ask_again(current, new):
        if not new: return
        def again(repeat):
            if repeat!=new: ask_new(current,"The two did not match. Type the new password again."); return
            page.set_status("Changing the password…")
            def done(problem):
                page.set_status("")
                if not problem: page.win.notice("Password","Your password is changed. Use the new one from now on (also for sudo)."); return
                if "current password" in problem: ask_current(problem)
                else: ask_new(current,problem)
            in_background(lambda:account.change_password(current,new),done,lambda exc:done(str(exc)))
        page.win.ask_text("New password, again","Type the new password once more.",again,secret=True,ok_label="Change")
    ask_current()
