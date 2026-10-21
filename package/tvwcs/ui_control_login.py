"""Settings > User: the account (name, password), the automatic login, TVWCS's login screen (update, switch, remove)
and the application to open at login. The system side is loginscreen.py and account.py; the changes that need root go
through the window's run_as_root."""
from __future__ import annotations
import os, shutil
from tvwcs import __version__, account, loginscreen
from tvwcs.model import CONFIG_HOME, STARTUP_LABELS, STARTUP_MODES, ConfigStore, startup_choices
from tvwcs.ui_control import in_background

CONFIG_FILE=CONFIG_HOME/"tvwcs"/"config.json"

def me() -> str: return account.read().login
def wm(env=None) -> str:
    env=os.environ if env is None else env
    return "sway" if env.get("SWAYSOCK") else "i3"
def my_session() -> str:
    """The session that starts TVWCS in TV mode with the window manager running now: TVWCS's own session."""
    return loginscreen.tvwcs_session(loginscreen.sessions(),wm())

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

# ====================================================================== User
def role(a) -> str: return "Administrator" if a.admin else "Standard User"

def read_user():
    a=account.read(); st=loginscreen.status(__version__,ConfigStore().settings); who,_sid=loginscreen.autologin()
    return (a,st,who,loginscreen.autologin_supported(st["current"]))

def draw_user(page, state):
    a,st,who,supported=state; cur=st["current"]
    page.section("ACCOUNT")
    page.row("Name",a.full_name or "Not set",lambda:change_name(page,a),detail="Shown on the login screen",ident="user:name")
    page.row("User name",a.login,None,detail="Used to log in and for the home folder; it cannot be changed here",ident="user:login")
    page.row("Password","Change",lambda:change_password(page),detail="Asks for the current one first",ident="user:password")
    page.section("LOGGING IN")
    if supported:
        mine=who==a.login
        page.row("Log in automatically after startup","On" if mine else f"On for {who}" if who else "Off",lambda:toggle_autologin(page,a,cur,mine),
                 ident="user:auto",value_css="state-on" if mine else "setting-value")
    else:
        page.row("Log in automatically after startup","Not here",None,detail=f"Set it in {loginscreen.name(cur)}'s own settings",ident="user:auto")
    draw_login_screen(page,st)
    draw_startup(page)

def toggle_autologin(page, a, cur, mine):
    turning_on=not mine
    args=["autologin",a.login,my_session()] if turning_on else ["autologin","--off"]
    def done(problem):
        if problem: page.win.notice("Log in automatically",problem); return
        if cur=="": loginscreen.set_start_lines(wm() if turning_on else "")
        page.refresh(quiet=True)
    label="Turning on the automatic login" if turning_on else "Turning off the automatic login"
    run_root(page,args,label,done)

# ---------------------------------------------------------------------- the login screen
def draw_login_screen(page, st):
    """The Login screen row: the one in use, whether TVWCS's copy is out of date, and what it can change to."""
    cur=st["current"]; others=[u for u in st["installed"] if u!=cur]
    if st["ours"]:
        stale=st["outdated"] or st["look_changed"]
        value="Out of date" if st["outdated"] else "Needs updating" if stale else "TVWCS"
        detail=("TVWCS's copy is older than this version: choose this to update it" if st["outdated"] else
                "Its colours differ from TVWCS's now: choose this to update it" if stale else
                "TVWCS's login screen"+(", or switch to another one" if others else ""))
        page.row("Login screen",value,(lambda:change_login_screen(page,st)) if stale or others else None,detail=detail,ident="user:screen",
                 value_css="error" if st["outdated"] else "setting-value")
    else:
        page.row("Login screen",loginscreen.name(cur) if cur else "None",lambda:change_login_screen(page,st),
                 detail="Choose this to use TVWCS's login screen"+(" or another one" if others else ""),ident="user:screen")
        if wm()=="sway" and cur and not loginscreen.wayland_ok(cur):
            page.note(f"{loginscreen.name(cur)} cannot start sway reliably. TVWCS's login screen, or SDDM, can.","error")

def change_login_screen(page, st):
    cur=st["current"]; options=[]
    if st["ours"] and (st["outdated"] or st["look_changed"]): options.append(("update","Update TVWCS's login screen to this version"))
    if not st["ours"]: options.append(("tvwcs","Use TVWCS's login screen"))
    for unit in st["installed"]:
        if unit!=cur: options.append((f"switch:{unit}",f"Switch to {loginscreen.name(unit)}"))
    if st["ours"] and st["installed"]:   # never without another one to go to
        fb=st["fallback"] or st["installed"][0]
        options.append((f"remove:{fb}",f"Remove TVWCS's login screen (back to {loginscreen.name(fb)})"))
    def picked(key):
        what,_,unit=key.partition(":")
        if what=="update": update_login_screen(page)
        elif what=="tvwcs": turn_login_on(page,st)
        elif what=="switch" and st["ours"]: turn_login_off(page,unit,keep_files=True)
        elif what=="switch": switch_login_screen(page,unit)
        elif what=="remove": turn_login_off(page,unit)
    page.win.choose_option("Login screen",options,None,picked)

def _carried_autologin():
    """The automatic login to keep when the login screen changes: this user's, when it is on now."""
    who,_sid=loginscreen.autologin()
    return (who,my_session()) if who and who==me() else None

def turn_login_on(page, st):
    cur=st["current"]; missing=st["packages"]; auto=_carried_autologin()
    text=(f"TVWCS's login screen replaces {loginscreen.name(cur)} from the next start. {loginscreen.name(cur)} stays installed." if cur else
          "TVWCS's login screen shows from the next start.")
    if missing: text+=f" It needs {', '.join(missing)}, which will be installed now."
    args=["enable","--config",str(CONFIG_FILE),"--previous",cur,"--session",me(),my_session()]+(["--autologin",*auto] if auto else [])
    def done(problem):
        if problem: page.win.notice("Login screen",problem); return
        if auto and not cur: loginscreen.set_start_lines("")   # the console's start lines are greetd's job now
        page.win.notice("Login screen","TVWCS's login screen shows from the next start.",lambda:page.refresh(quiet=True))
    page.win.confirm("Use TVWCS's login screen?",text+" It asks for your password.","Use it",
                     lambda:run_root(page,args,"Turning on the login screen",done,missing),danger=False)

def update_login_screen(page):
    def done(problem):
        if problem: page.win.notice("Login screen",problem)
        page.refresh(quiet=True)
    run_root(page,["update","--config",str(CONFIG_FILE)],"Updating the login screen",done)

def switch_login_screen(page, unit):
    def done(problem):
        if problem: page.win.notice("Login screen",problem); return
        page.win.notice("Login screen",f"From the next start, the computer uses {loginscreen.name(unit)}.",lambda:page.refresh(quiet=True))
    page.win.confirm(f"Switch to {loginscreen.name(unit)}?",f"From the next start the computer uses {loginscreen.name(unit)}. It asks for your password.",
                     "Switch",lambda:run_root(page,["switch",unit],"Changing the login screen",done),danger=False)

def turn_login_off(page, unit, keep_files=False):
    """Go from TVWCS's login screen to `unit`. keep_files: only switch (TVWCS's stays installed, to switch back to);
    otherwise TVWCS's login screen is removed."""
    auto=_carried_autologin()
    keep=auto if auto and loginscreen.autologin_supported(unit) else None
    args=["disable","--to",unit]+(["--autologin",*keep] if keep else [])
    if keep_files: args=["switch",unit]
    def done(problem):
        if problem: page.win.notice("Login screen",problem); return
        after=f"From the next start, the computer uses {loginscreen.name(unit)}."
        if auto and not keep and not keep_files: after+=f" The automatic login could not be kept: set it in {loginscreen.name(unit)}'s own settings."
        page.win.notice("Login screen",after,lambda:page.refresh(quiet=True))
    title=f"Switch to {loginscreen.name(unit)}?" if keep_files else "Remove TVWCS's login screen?"
    text=(f"From the next start the computer uses {loginscreen.name(unit)}. TVWCS's login screen stays installed, to switch back to."
          if keep_files else f"TVWCS's login screen is removed, and from the next start the computer uses {loginscreen.name(unit)}.")
    page.win.confirm(title,text+" It asks for your password.","Switch" if keep_files else "Remove",
                     lambda:run_root(page,args,"Changing the login screen",done),danger=not keep_files)

# ---------------------------------------------------------------------- the application to open at login
def draw_startup(page):
    store=ConfigStore(); st=store.settings; mode=st["startup"]["mode"]
    names={p.id:p.name for p in store.profiles}
    page.row("Application to open at login",STARTUP_LABELS[mode],lambda:page.win.choose_option("Application to open at login",
             [(m,STARTUP_LABELS[m]) for m in STARTUP_MODES],mode,lambda m:pick_startup(page,m)),ident="user:startup")
    if mode=="app":
        page.row("Application",names.get(st["startup"]["profile_id"],"Not chosen"),lambda:choose_startup_app(page),ident="user:startup-app",indent=44)
    page.note("Some applications, such as Steam, have their own option to start at login. If you use one of those, choose None here, "
              "so the two do not both open something.")

def _save_startup(page, **changes):
    from tvwcs.ui_control_pages import tell_tvwcs
    store=ConfigStore(); store.settings["startup"].update(changes); store.save(); tell_tvwcs("reload"); page.redraw()

def pick_startup(page, mode):
    store=ConfigStore()
    if mode=="app" and store.get(store.settings["startup"]["profile_id"]) is None: choose_startup_app(page); return   # pick which one first
    _save_startup(page,mode=mode)

def choose_startup_app(page):
    store=ConfigStore(); options=[]
    for _heading,profiles in startup_choices(store.profiles):
        for p in profiles: options.append((p.id,(f"{p.channel:03d}  " if p.channel is not None else "")+p.name+("  ★" if p.favorite else "")))
    if not options: page.win.notice("Application to open at login","There are no applications to choose from yet."); return
    page.win.choose_option("Application to open at login",options,store.settings["startup"]["profile_id"],lambda pid:_save_startup(page,profile_id=pid,mode="app"))

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
