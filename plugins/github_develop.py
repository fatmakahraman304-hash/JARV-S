"""GitHub coding workspace and checked publication, separate from the running app."""
import json
import os
import shutil
import sys
import re
import subprocess
import threading
import time
import tempfile
from pathlib import Path

from core.app_updater import REPOSITORY as REPO
# Use the user's GitHub CLI credential just for this repository and invocation.
_GH_GIT = ["git", "-c", "credential.https://github.com.helper=",
           "-c", "credential.https://github.com.helper=!gh auth git-credential"]


def find_github_cli() -> str | None:
    executable = shutil.which("gh")
    if executable or sys.platform != "win32":
        return executable

    # A running process or its launcher may still have the pre-install PATH.
    for variable, directory in (
        ("ProgramW6432", "GitHub CLI"),
        ("ProgramFiles", "GitHub CLI"),
        ("ProgramFiles(x86)", "GitHub CLI"),
        ("LOCALAPPDATA", "Microsoft/WinGet/Links"),
        ("ProgramFiles", "WinGet/Links"),
    ):
        root = os.environ.get(variable)
        if root:
            candidate = Path(root) / directory / "gh.exe"
            if candidate.is_absolute() and candidate.is_file():
                return str(candidate)
    return None


def _development_workspace(parent):
    preferred = parent / "Murat"
    if preferred.exists() or not parent.is_dir():
        return preferred
    existing = []
    for path in parent.iterdir():
        if not (path / ".git").is_dir():
            continue
        try:
            channel = json.loads((path / "update_channel.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(channel, dict) and channel.get("repository") == REPO:
            existing.append(path)
    return existing[0] if len(existing) == 1 else preferred


WORK = _development_workspace(Path.home() / "AetherDevelopment")
_LOCK = threading.Lock()
PLUGIN = {'name':'github_develop','description':
    'FRIDAY GitHub development workflow. prepare clones the user FRIDAY repo into a separate workspace and creates a development branch; inspect reports its state. develop uses the coding agent to write/fix code there. self_edit is the entry point when the user asks FRIDAY to change itself or add an extension: prepares the isolated repository if needed, then hands off to the code agent. Never use self_edit on other repositories. self_release prepares a benign FRIDAY feature or evidenced bug fix, tests it, waits for GitHub checks, merges and updates. Use only for a concrete user request explicitly asking for code and automatic publication. Never use it for a missing third-party app, network error, security exploit, or offensive automation. sync updates a clean development branch from main by fast-forward only. test runs the Python tests and shows failures inside FRIDAY. publish commits ONLY the explicitly selected files, pushes a branch, creates a PR and merges into main ONLY after GitHub checks succeed. Use publish only when the user asks to publish/merge. main then becomes available through the existing GÜNCELLE button; this tool never updates running source. Requires local Git and authenticated GitHub CLI for publication. Existing dev_agent builds other projects.',
    'parameters':{'type':'OBJECT','properties':{
        'mode':{'type':'STRING','enum':['prepare','inspect','develop','self_edit','self_release','sync','test','publish','merge']},
        'instruction':{'type':'STRING'},
        'files':{'type':'ARRAY','items':{'type':'STRING'},'description':'Exact changed source/test paths to include; never secrets or personal config.'}},'required':['mode']}}


_LOCAL_COMMANDS = {
    "/git sync": "sync",
    "/git test": "test",
    "github geliştirme alanını main ile eşitle": "sync",
    "github geliştirme alanını ana dal ile eşitle": "sync",
    "github geliştirme alanını güncelle": "sync",
    "github geliştirme dalını güncelle": "sync",
    "friday github geliştirme dalını eşitle": "sync",
    "github geliştirme alanındaki testleri çalıştır": "test",
    "github geliştirme alanındaki testleri çalıştır ve sonucu göster": "test",
    "github testlerini çalıştır": "test",
    "github testlerini çalıştır ve sonucu göster": "test",
    "friday github testlerini çalıştır": "test",
}
from core.voice_commands import normalize_command

_NORMALIZED_LOCAL_COMMANDS = {
    normalize_command(text): mode for text, mode in _LOCAL_COMMANDS.items()
}


def local_command_mode(text: str) -> str | None:
    """Tam eşleşen Türkçe geliştirme komutlarını, yazım farklarıyla tanı."""
    return _NORMALIZED_LOCAL_COMMANDS.get(normalize_command(text))


class TestFailure(RuntimeError):
    """Test output safe to show locally, without losing the failing filename."""


class CommandFailure(RuntimeError):
    def __init__(self, operation, result):
        detail = (result.stderr or "").lower()
        self.missing_identity = any(message in detail for message in (
            "unable to auto-detect email address", "identity unknown",
            "empty ident name", "no email was given",
        ))
        if self.missing_identity:
            hint = "Git commit kimliğinde ad veya e-posta eksik."
        elif "authentication failed" in detail or "could not read username" in detail:
            hint = "Terminalde gh auth status ile GitHub oturumunu kontrol edin."
        elif "could not resolve host" in detail:
            hint = "GitHub adresi çözümlenemedi. İnternet bağlantısını kontrol edin."
        elif "index.lock" in detail:
            hint = "Git dizini başka bir işlem tarafından kilitlenmiş."
        elif "non-fast-forward" in detail or "fetch first" in detail:
            hint = "Uzak dal ilerlemiş. GitHub’daki dalı kontrol edin."
        else:
            hint = "Git ve GitHub CLI durumunu kontrol edin."
        super().__init__(f"{operation} başarısız (kod {result.returncode}). {hint}")


def command(args, cwd=None, timeout=180, *, test_name=None):
    options = {}
    if args[0] == "git":
        index = 1
        while index < len(args) and args[index] in {"-c", "--literal-pathspecs"}:
            index += 2 if args[index] == "-c" else 1
        operation = "git " + args[index] if index < len(args) else "git"
    elif args[0] == "gh":
        operation = " ".join(args[:3])
    else:
        operation = Path(args[0]).name
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    if args[0] in {"git", "gh"}:
        options["env"] = dict(os.environ, GIT_TERMINAL_PROMPT="0", GH_PROMPT_DISABLED="1")
    if test_name:
        options.setdefault("env", dict(os.environ)).update(QT_QPA_PLATFORM="offscreen", PYTHONUTF8="1")
    if args[0] == "gh" or args[:len(_GH_GIT)] == _GH_GIT:
        executable = find_github_cli()
        if not executable:
            raise RuntimeError("GitHub CLI (gh) bulunamadı. GitHub CLI’ı yükleyip tekrar deneyin.")
        if args[0] == "gh":
            args = [executable, *args[1:]]
        else:
            # The scoped Git credential helper looks up gh in its own PATH.
            env = options["env"]
            env["PATH"] = str(Path(executable).parent) + os.pathsep + env.get("PATH", os.defpath)
    try:
        result = subprocess.run(
            args, cwd=WORK if cwd is None else cwd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, **options,
        )
    except subprocess.TimeoutExpired as exc:
        if test_name:
            raise TestFailure(f"{test_name}: {timeout} saniyede tamamlanamadı.") from exc
        raise
    if test_name:
        output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
        if result.returncode:
            raise TestFailure(
                f"{test_name}: test başarısız (kod {result.returncode}).\n\n"
                + (output[-6000:] or "Python hata çıktısı üretmedi.")
            )
        return output
    if result.returncode:
        raise CommandFailure(operation, result)
    return result.stdout if "\0" in result.stdout else result.stdout.strip()


def selected_files(files):
    if not files:
        raise ValueError('Yayınlanacak dosyalar belirtilmeli.')
    for name in files:
        p=Path(name)
        if p.is_absolute() or '..' in p.parts or not (WORK/p).resolve().is_relative_to(WORK.resolve()):
            raise ValueError('Geçersiz kaynak yolu.')
        if any(part.startswith('.') for part in p.parts) or any(x in name.lower() for x in ('api_keys','token','secret','credential','.env')) or p.parts[0] in {'config','downloads','logs'}:
            raise ValueError('Kişisel/gizli dosya yayına alınamaz.')
    return files


def tests(folder=None):
    folder = WORK if folder is None else folder
    paths = sorted((folder / "tests").glob("test_*.py"))
    if not paths:
        raise RuntimeError('Test bulunamadı; yayın durduruldu.')
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe":
        console_python = python.with_name("python.exe")
        if console_python.is_file():
            python = console_python
    for path in paths:
        output=command([str(python),'-m','unittest','discover','-s','tests','-p',path.name,'-v'], cwd=folder, timeout=300, test_name=path.name)
        if not re.search(r"Ran [1-9][0-9]* tests?", output):
            raise TestFailure(f"{path.name}: test çalışması doğrulanamadı.\n\n{output[-6000:]}")
    return f'{len(paths)} Python test dosyası başarıyla çalıştı.'


def _commit_selected(changed, scope, instruction):
    identity = []
    try:
        command(["git", "var", "GIT_AUTHOR_IDENT"])
        command(["git", "var", "GIT_COMMITTER_IDENT"])
    except CommandFailure as exc:
        if not exc.missing_identity:
            raise
        account = json.loads(command(["gh", "api", "--hostname", "github.com", "user"]))
        login, account_id = account.get("login"), account.get("id")
        if (not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", login)
                or type(account_id) is not int or account_id < 1):
            raise ValueError("Commit kimliği için bağlı GitHub hesabı doğrulanamadı.") from exc
        identity = ["-c", f"user.name={login}",
                    "-c", f"user.email={account_id}+{login}@users.noreply.github.com"]
    if changed:
        command(["git", "--literal-pathspecs", "add", "--", *sorted(changed)])
    staged = _paths(["git", "diff", "--cached", "--name-only", "-z", "--no-renames"])
    if not staged or staged - scope:
        raise ValueError("Commit kapsamındaki dosyalar doğrulanamadı.")
    command(["git", *identity, "commit", "-m", instruction or "FRIDAY geliştirmesi"])


def _paths(args):
    return set(command(args).split("\0")) - {""}


def _merge_checked(branch, head):
    info = json.loads(command(["gh", "pr", "view", branch, "--repo", REPO,
                               "--json", "headRefOid,baseRefName,statusCheckRollup,state,url"]))
    if info["headRefOid"] != head or info["baseRefName"] != "main":
        raise ValueError("Pull request commit’i veya hedef dalı doğrulanamadı.")
    checks = info.get("statusCheckRollup") or []
    if info["state"] != "MERGED":
        if not checks or any(c.get("conclusion", c.get("state")) != "SUCCESS" for c in checks):
            return "PR açıldı. GitHub kontrolleri başarılı olunca birleştirme komutunu verin. " + info["url"]
        command(["gh", "pr", "merge", info["url"], "--repo", REPO, "--merge",
                 "--match-head-commit", head], timeout=90)
        state = json.loads(command(["gh", "pr", "view", info["url"], "--repo", REPO, "--json", "state"]))
        if state.get("state") != "MERGED":
            return "Birleştirme henüz doğrulanamadı. " + info["url"]
    return "Main’e birleştirildi. GÜNCELLE düğmesini kullanabilirsiniz. " + info["url"]


def workflow(mode, instruction, files):
    if mode=='prepare':
        if WORK.exists():
            raise ValueError('Geliştirme klasörü zaten var. İncele veya geliştir komutunu kullanın.')
        WORK.parent.mkdir(parents=True,exist_ok=True)
        command(['git','clone','https://github.com/'+REPO+'.git',str(WORK)],cwd=WORK.parent)
        command(['git','switch','-c','aether-dev/'+str(int(time.time()))])
        return 'Ayrı geliştirme alanı hazır: '+str(WORK)
    if not (WORK/'.git').exists():
        raise ValueError('Önce geliştirme alanını hazırla komutunu verin.')
    if mode=='inspect':
        return command(['git','status','--short'])+'\n'+command(['git','log','-5','--oneline'])
    if mode == "sync":
        from actions import dev_agent
        branch = command(["git", "branch", "--show-current"])
        if not branch.startswith("aether-dev/") or command(["git", "status", "--porcelain"]):
            raise ValueError("Eşitlemek için temiz bir FRIDAY geliştirme dalı gerekli.")
        if dev_agent._job_lock.locked():
            raise ValueError("Kod geliştirme işi tamamlanınca tekrar deneyin.")
        command(["git", "fetch", "https://github.com/" + REPO + ".git", "refs/heads/main"])
        command(["git", "merge", "--ff-only", "FETCH_HEAD"])
        return "Geliştirme alanı güncel. Testleri çalıştırabilirsiniz."
    if mode=='test':
        return tests()
    if mode=='merge':
        branch=command(['git','branch','--show-current'])
        if not branch.startswith('aether-dev/') or command(['git','status','--porcelain']):
            raise ValueError('Temiz geliştirme dalı gerekli.')
        return _merge_checked(branch, command(["git", "rev-parse", "HEAD"]))
    if mode=='publish':
        files = list(dict.fromkeys(Path(file).as_posix() for file in selected_files(files)))
        scope = set(files)
        branch=command(['git','branch','--show-current'])
        if not branch.startswith('aether-dev/'):
            raise ValueError('Yayın yalnızca ayrı geliştirme dalından yapılır.')
        from actions import dev_agent
        if dev_agent._job_lock.locked():
            raise ValueError('Kod geliştirme işi henüz bitmedi.')
        command(["gh", "auth", "status", "--hostname", "github.com"])
        remote = f"https://github.com/{REPO}.git"
        command([*_GH_GIT, "fetch", "--no-tags", remote, "refs/heads/main"])
        main = command(["git", "rev-parse", "FETCH_HEAD"])
        history_args = ["git", "log", "--format=", "--name-only", "-z",
                        "--no-renames", "--diff-merges=first-parent", f"{main}..HEAD"]
        history = _paths(history_args)
        staged = _paths(["git", "diff", "--cached", "--name-only", "-z", "--no-renames"])
        if (history | staged) - scope:
            raise ValueError("Geliştirme dalında seçilen dosyaların dışında yayınlanacak değişiklikler var.")
        changed = _paths(["git", "--literal-pathspecs", "ls-files", "--modified",
                          "--others", "--exclude-standard", "-z", "--", *files])
        if scope - (history | staged | changed):
            raise ValueError("Seçilen dosyalardan en az birinde yayınlanacak değişiklik yok.")
        tests()
        if staged or changed:
            _commit_selected(changed, scope, instruction)
        head=command(['git','rev-parse','HEAD'])
        history_args[-1] = f"{main}..{head}"
        if _paths(history_args) != scope:
            raise ValueError("GitHub’a gönderilecek commit’lerin dosya kapsamı doğrulanamadı.")
        command([*_GH_GIT, 'push', remote, f"{head}:refs/heads/{branch}"])
        prs=json.loads(command(['gh','pr','list','--repo',REPO,'--head',branch,'--base','main','--json','number']))
        if not prs:
            command(['gh','pr','create','--repo',REPO,'--base','main','--head',branch,'--title',instruction[:120] or 'FRIDAY geliştirmesi','--body','FRIDAY geliştirme alanında hazırlanmış değişiklikler. Python testleri yerel olarak çalıştırıldı; GitHub kontrolleri birleştirmeden önce zorunludur.'])
        return _merge_checked(branch, head)
    raise ValueError('Geçersiz işlem.')


def self_release(instruction, player):
    """Work from the current remote main, independently of the user's checkout."""
    from actions import dev_agent
    from core.code_checks import Protection

    command(["gh", "auth", "status"], cwd=Path.home())
    with tempfile.TemporaryDirectory(prefix="aether-release-") as temp:
        folder = Path(temp) / "source"
        remote = f"https://github.com/{REPO}.git"
        command(["git", "clone", "--branch", "main", "--single-branch", remote, str(folder)],
                cwd=Path(temp))
        branch = f"aether-dev/release-{time.time_ns()}"
        command(["git", "switch", "-c", branch], cwd=folder)

        if not dev_agent._job_lock.acquire(False):
            raise RuntimeError("Başka bir kod geliştirme işi sürüyor.")
        try:
            dev_agent._new_job(folder, "FRIDAY", instruction, player, kind="improve")
            result = dev_agent._improve_folder(
                folder,
                instruction + "\n\nModify only FRIDAY source for the benign user request. "
                "Follow AGENTS.md. Keep the release workflow, updater, secrets and CI gates intact. "
                "Do not add offensive automation, exploits, or arbitrary command execution.",
                player,
                open_editor=False,
            )
            dev_agent._update("finished", result=result, finished=time.time())
        except Exception as exc:
            dev_agent._update("failed", result=str(exc), finished=time.time())
            raise
        finally:
            dev_agent._job_lock.release()

        changed = command(["git", "-c", "core.quotePath=false", "ls-files",
                           "--modified", "--others", "--exclude-standard"], cwd=folder)
        files = sorted(set(changed.splitlines()) - {""})
        generated = (".aether_backup/",)
        files = [name for name in files if not name.startswith(generated)]
        if not files:
            raise RuntimeError("Kod değişikliği üretilmedi.")
        protection = Protection(folder)
        for name in files:
            path = folder / name
            if (name.startswith(".") or not path.resolve().is_relative_to(folder.resolve())
                    or path.is_symlink() or not path.is_file() or protection.reason(name)
                    or name in {"core/app_updater.py", "plugins/github_develop.py", "requirements.txt"}):
                raise RuntimeError(f"Otomatik yayın durduruldu: {name}")

        command(["git", "diff", "--check"], cwd=folder)
        player.write_log("GELİŞTİRME: " + tests(folder))
        command(["git", "--literal-pathspecs", "add", "--", *files], cwd=folder)
        command(["git", "commit", "-m", "FRIDAY: kullanıcı geliştirme isteği"], cwd=folder)
        head = command(["git", "rev-parse", "HEAD"], cwd=folder)
        command([*_GH_GIT, "push", remote, branch], cwd=folder)
        pr = command(["gh", "pr", "create", "--repo", REPO, "--base", "main",
                      "--head", branch, "--title", "FRIDAY geliştirmesi",
                      "--body", "Kullanıcı isteğiyle oluşturuldu. Yerel Python testleri geçti."],
                     cwd=folder)
        player.write_log("GELİŞTİRME: GitHub kontrolleri bekleniyor. " + pr)
        command(["gh", "pr", "checks", pr, "--repo", REPO, "--watch", "--interval", "10"],
                cwd=folder, timeout=900)
        state = json.loads(command(["gh", "pr", "view", pr, "--repo", REPO,
                                    "--json", "headRefOid,baseRefName,statusCheckRollup"], cwd=folder))
        checks = state.get("statusCheckRollup") or []
        if (state.get("headRefOid") != head or state.get("baseRefName") != "main"
                or not checks
                or any(check.get("conclusion", check.get("state")) != "SUCCESS" for check in checks)):
            raise RuntimeError("Doğrulanmış başarılı GitHub kontrolleri bulunamadı.")
        command(["gh", "pr", "merge", pr, "--repo", REPO, "--merge", "--match-head-commit", head],
                cwd=folder)
        merged = json.loads(command(["gh", "pr", "view", pr, "--repo", REPO, "--json", "state"],
                                    cwd=folder))
        if merged.get("state") != "MERGED":
            raise RuntimeError("Birleştirme henüz doğrulanamadı.")
        player.write_log("GELİŞTİRME: Main’e alındı, FRIDAY güncelleniyor. " + pr)
        player.request_app_update()
        return "GitHub birleştirmesi doğrulandı ve güncelleme isteği gönderildi."


def run(parameters, player=None, session_memory=None):
    mode = parameters.get("mode", "")
    if mode in ("publish", "merge", "self_release"):
        from core import confirm
        files = parameters.get("files", [])
        if not isinstance(files, list) or any(not isinstance(path, str) for path in files):
            return "Yayınlanacak dosya listesi geçersiz."
        request = {"mode": mode, "files": list(files), "instruction": str(parameters.get("instruction") or "")}
        detail = f"Depo: {REPO}\nHedef: main\nİşlem: {mode}\nİstek: {request['instruction']}"
        if files:
            detail += "\nDosyalar:\n" + "\n".join(files)
        if mode == "self_release":
            detail += "\nKod üretimi, test, yayın, birleştirme ve uygulama güncellemesini onaylıyorsunuz."
        return confirm.request("github_develop", "GitHub yayını ve birleştirme", detail,
                               lambda: _start(request, player))
    return _start(parameters, player)


def _start(parameters, player):
    mode=parameters.get('mode','')
    instruction=str(parameters.get('instruction','')).strip()
    if mode == "self_edit":
        if not instruction:
            return "FRIDAY’ta yapılacak kod değişikliğini tarif et."
        if not player:
            return "Geliştirme ilerlemesi için FRIDAY arayüzü gerekli."
        if not _LOCK.acquire(False):
            return "Bir GitHub işlemi zaten çalışıyor."

        def prepare_and_edit():
            try:
                from actions import dev_agent

                if dev_agent._job_lock.locked():
                    raise ValueError("Kod geliştirme işi tamamlanınca tekrar deneyin.")
                if WORK.resolve() == Path(__file__).resolve().parents[1]:
                    raise ValueError("FRIDAY’ı normal kurulumdan aç; bu klasör geliştirme kopyası.")
                if not (WORK / ".git").exists():
                    workflow("prepare", "", [])
                branch = command(["git", "branch", "--show-current"])
                if not branch.startswith("aether-dev/"):
                    raise ValueError("FRIDAY değişiklikleri geliştirme dalında hazırlanır.")
                notes = (
                    "\n\nWork only in this development checkout. Follow AGENTS.md. "
                    "For a new FRIDAY tool, use the existing Python plugin contract; "
                    "add a JavaScript helper only if needed and use an explicit, narrow "
                    "Python entry point. Preserve user settings. Add focused tests for "
                    "new behavior. Do not publish or change the running installation."
                )
                result = dev_agent.dev_agent(
                    {"mode": "improve", "folder": str(WORK), "description": instruction + notes},
                    player=player,
                )
                player.write_log("GELİŞTİRME: " + result)
            except Exception as exc:
                player.write_log("GELİŞTİRME: " + str(exc))
            finally:
                _LOCK.release()

        try:
            threading.Thread(target=prepare_and_edit, daemon=True, name="aether-self-edit").start()
        except Exception:
            _LOCK.release()
            raise
        return "FRIDAY kod değişikliği için ayrı geliştirme alanı hazırlanıyor."

    if mode=='develop':
        if _LOCK.locked(): return 'GitHub işlemi bitene kadar kod düzenleme beklemeli.'
        if not (WORK/'.git').exists(): return 'Önce geliştirme alanını hazırlayın.'
        from actions.dev_agent import dev_agent
        return dev_agent({'mode':'improve','folder':str(WORK),'description':instruction},player=player)
    if not player: return 'Geliştirme ilerlemesi için FRIDAY arayüzü gerekli.'
    if mode == "self_release" and (
        not instruction or not callable(getattr(player, "request_app_update", None))
    ):
        return "Kod değişikliğini açıkça belirt ve FRIDAY masaüstü arayüzünü kullan."

    if not _LOCK.acquire(False): return 'Bir GitHub işlemi zaten çalışıyor.'
    def work():
        try:
            if mode == "self_release":
                result = self_release(instruction, player)
            else:
                result = workflow(mode, instruction, parameters.get("files", []))
            player.write_log('GELİŞTİRME: '+result)
        except TestFailure as exc:
            player.write_log("GELİŞTİRME: " + str(exc).splitlines()[0])
            show = getattr(player, "show_content", None)
            if callable(show):
                show("Geliştirme testi", str(exc))
        except Exception as exc:
            player.write_log('GELİŞTİRME: '+str(exc))
        finally:
            _LOCK.release()
    try:
        threading.Thread(target=work,daemon=True,name='aether-github').start()
    except RuntimeError:
        _LOCK.release()
        return 'Geliştirme işi başlatılamadı. Tekrar deneyebilirsiniz.'
    return 'GitHub geliştirme işlemi arka planda başladı; sonucu ekranda göstereceğim.'
