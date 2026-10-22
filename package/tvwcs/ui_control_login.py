"""Settings > User: the account (name, password), the automatic login, the login screen, the TVWCS logo at startup and
the application to open at login. The system side is loginscreen.py, bootlogo.py and account.py; the changes that need
root go through the window's run_as_root."""
from __future__ import annotations
from tvwcs import __version__, account, bootlogo, loginscreen, selfupdate
from tvwcs.model import STARTUP_LABELS, STARTUP_MODES, ConfigStore, startup_choices
from tvwcs.ui_control import in_background

def me() -> str: return account.read().login

def run_root(page, args, label, done, packages=()):
    """Run `python3 -m tvwcs.loginscreen args` as root (installing `packages` first), then done(problem or "")."""
    lines=[]
    def finished(code, tail):
        page.set_status("")
        if code: done(("\n".join(lines[-6:]) or tail or f"{label} did not work.").strip()); return
        done("")
    page.set_status(f"{label}…")
    page.win.run_as_root(loginscreen.root_command(args,packages),label,lines.append,finished)

# ====================================================================== User
def role(a) -> str: return "Administrator" if a.admin else "Standard User"

def read_user():
    return (account.read(),loginscreen.status(),bootlogo.installed())

def draw_user(page, state):
    a,st,logo=state; cur=st["current"]; who,_sid=st["autologin"]
    page.section("ACCOUNT")
    page.row("Name",a.full_name or "Not set",lambda:change_name(page,a),detail="Shown on the login screen",ident="user:name")
    page.row("User name",a.login,None,detail="Used to log in and for the home folder; it cannot be changed here",ident="user:login")
    page.row("Password","Change",lambda:change_password(page),detail="Asks for the current one first",ident="user:password")
    page.section("LOGGING IN")
    if loginscreen.autologin_supported(cur):
        mine=who==a.login
        page.row("Log in automatically after startup","On" if mine else f"On for {who}" if who else "Off",lambda:toggle_autologin(page,a,mine),
                 detail="Straight into TVWCS, without the login screen",ident="user:auto",value_css="state-on" if mine else "setting-value")
    elif cur:
        page.row("Log in automatically after startup","Not here",None,detail=f"Set it in {loginscreen.name(cur)}'s own settings",ident="user:auto")
    others=[u for u in st["installed"] if u!=cur]
    page.row("Login screen",loginscreen.name(cur) if cur else "None",(lambda:change_login_screen(page,cur,others)) if others else None,
             detail="Choose this to switch to another one installed here" if others else "",ident="user:screen")
    if cur and not loginscreen.wayland_ok(cur):
        page.note(f"{loginscreen.name(cur)} cannot start sway reliably. greetd or SDDM can.","error")
    if st["old_greeter"]:
        page.row("Remove TVWCS's old login screen","",lambda:remove_old_greeter(page),ident="user:old",
                 detail="TVWCS 4's login screen is still set up; TVWCS 5 no longer has one",icon="user-trash-symbolic",fallback="✕")
    page.row("TVWCS logo at startup","On" if logo else "Off",lambda:toggle_boot_logo(page,logo),ident="user:logo",
             detail="Shows the TVWCS logo while the computer starts, instead of lines of text",value_css="state-on" if logo else "setting-value")
    draw_startup(page)

def toggle_autologin(page, a, mine):
    args=["autologin",a.login,loginscreen.SESSION] if not mine else ["autologin","--off"]
    def done(problem):
        if problem: page.win.notice("Log in automatically",problem); return
        page.refresh(quiet=True)
    run_root(page,args,"Turning off the automatic login" if mine else "Turning on the automatic login",done)

def change_login_screen(page, cur, others):
    def picked(unit):
        def done(problem):
            if problem: page.win.notice("Login screen",problem); return
            page.win.notice("Login screen",f"From the next start, the computer uses {loginscreen.name(unit)}.",lambda:page.refresh(quiet=True))
        page.win.confirm(f"Switch to {loginscreen.name(unit)}?",f"From the next start the computer uses {loginscreen.name(unit)}. It asks for your password.",
                         "Switch",lambda:run_root(page,["switch",unit],"Changing the login screen",done),danger=False)
    page.win.choose_option("Login screen",[(u,f"Switch to {loginscreen.name(u)}") for u in others],None,picked)

def remove_old_greeter(page):
    def done(problem):
        if problem: page.win.notice("Login screen",problem); return
        page.refresh(quiet=True)
    page.win.confirm("Remove TVWCS's old login screen?","Another login screen installed here takes over from the next start; without one, "
                     "greetd's text login does, and the automatic login is kept. It asks for your password.","Remove",
                     lambda:run_root(page,["migrate"],"Removing the old login screen",done),danger=False)

def toggle_boot_logo(page, on):
    lines=[]
    def finished(folder):
        def done(code, tail):
            if folder: selfupdate.discard(folder)
            page.set_status("")
            if code: page.win.notice("TVWCS logo at startup",("\n".join(lines[-4:]) or tail or "It did not work.").strip())
            else: page.win.notice("TVWCS logo at startup",("It shows" if not on else "The start-up text shows")+" from the next start.")
            page.refresh(quiet=True)
        return done
    if on:
        page.win.confirm("Turn off the TVWCS logo?","The computer shows its start-up text again from the next start. It asks for your password.","Turn off",
                         lambda:(page.set_status("Removing the logo…"),page.win.run_as_root(bootlogo.remove_argv(),"Removing the startup logo",lines.append,finished(None))),
                         danger=False)
        return
    def go():
        page.set_status("Downloading the logo…")
        def got(result):
            folder,files=result; page.set_status("Installing the logo…")
            page.win.run_as_root(bootlogo.install_argv(files),"Installing the startup logo",lines.append,finished(folder))
        def failed(exc): page.set_status(""); page.win.notice("TVWCS logo at startup",f"The logo could not be downloaded: {exc}")
        in_background(lambda:bootlogo.download(__version__),got,failed)
    page.win.confirm("Show the TVWCS logo at startup?","Installs the tvwcs-boot-logo package (with Plymouth, which draws it) from TVWCS's GitHub release. "
                     "It asks for your password.","Turn on",go,danger=False)

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
