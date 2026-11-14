"""GitHub coding workspace and checked publication, separate from the running app."""
import json
import os
import sys
import re
import subprocess
import threading
import time
import tempfile
from pathlib import Path

REPO = 'fatmakahraman304-hash/JARV-S'
WORK = Path.home() / 'JarvisDevelopment' / 'Mark-LVII'
_LOCK = threading.Lock()
PLUGIN = {'name':'github_develop','description':
    'JARVIS GitHub development workflow. prepare clones the user JARVIS repo into a separate workspace and creates a development branch; inspect reports its state. develop uses the coding agent to write/fix code there. self_edit is the entry point when the user asks JARVIS to change itself or add an extension: prepares the isolated repository if needed, then hands off to the code agent. Never use self_edit on other repositories. self_release prepares a benign JARVIS feature or evidenced bug fix, tests it, waits for GitHub checks, merges and updates. Use only for a concrete user request explicitly asking for code and automatic publication. Never use it for a missing third-party app, network error, security exploit, or offensive automation. sync updates a clean development branch from main by fast-forward only. test runs the Python tests and shows failures inside JARVIS. publish commits ONLY the explicitly selected files, pushes a branch, creates a PR and merges into main ONLY after GitHub checks succeed. Use publish only when the user asks to publish/merge. main then becomes available through the existing GÜNCELLE button; this tool never updates running source. Requires local Git and authenticated GitHub CLI for publication. Existing dev_agent builds other projects.',
    'parameters':{'type':'OBJECT','properties':{
        'mode':{'type':'STRING','enum':['prepare','inspect','develop','self_edit','self_release','sync','test','publish','merge']},
        'instruction':{'type':'STRING'},
        'files':{'type':'ARRAY','items':{'type':'STRING'},'description':'Exact changed source/test paths to include; never secrets or personal config.'}},'required':['mode']}}


_LOCAL_COMMANDS = {
    "/git sync": "sync",
    "/git test": "test",
    "github geliştirme alanını main ile eşitle": "sync",
    "github geliştirme alanındaki testleri çalıştır": "test",
    "github geliştirme alanındaki testleri çalıştır ve sonucu göster": "test",
}


def local_command_mode(text: str) -> str | None:
    """Recognize explicit typed commands without interpreting free-form prose."""
    normalized = " ".join(text.strip().replace("İ", "i").casefold().split())
    return _LOCAL_COMMANDS.get(normalized.rstrip(".!"))


class TestFailure(RuntimeError):
    """Test output safe to show locally, without losing the failing filename."""


def command(args, cwd=None, timeout=180, *, test_name=None):
    options = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    if test_name:
        options["env"] = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONUTF8="1")
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
        raise RuntimeError(
            f"{Path(args[0]).name} işlemi başarısız (kod {result.returncode}). "
            "Yerel Git/CLI oturumunu kontrol edin."
        )
    return result.stdout.strip()


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


def workflow(mode, instruction, files):
    if mode=='prepare':
        if WORK.exists():
            raise ValueError('Geliştirme klasörü zaten var. İncele veya geliştir komutunu kullanın.')
        WORK.parent.mkdir(parents=True,exist_ok=True)
        command(['git','clone','https://github.com/'+REPO+'.git',str(WORK)],cwd=WORK.parent)
        command(['git','switch','-c','jarvis-dev/'+str(int(time.time()))])
        return 'Ayrı geliştirme alanı hazır: '+str(WORK)
    if not (WORK/'.git').exists():
        raise ValueError('Önce geliştirme alanını hazırla komutunu verin.')
    if mode=='inspect':
        return command(['git','status','--short'])+'\n'+command(['git','log','-5','--oneline'])
    if mode == "sync":
        from actions import dev_agent
        branch = command(["git", "branch", "--show-current"])
        if not branch.startswith("jarvis-dev/") or command(["git", "status", "--porcelain"]):
            raise ValueError("Eşitlemek için temiz bir JARVIS geliştirme dalı gerekli.")
        if dev_agent._job_lock.locked():
            raise ValueError("Kod geliştirme işi tamamlanınca tekrar deneyin.")
        command(["git", "fetch", "https://github.com/" + REPO + ".git", "refs/heads/main"])
        command(["git", "merge", "--ff-only", "FETCH_HEAD"])
        return "Geliştirme alanı güncel. Testleri çalıştırabilirsiniz."
    if mode=='test':
        return tests()
    if mode=='merge':
        branch=command(['git','branch','--show-current'])
        if not branch.startswith('jarvis-dev/') or command(['git','status','--porcelain']):
            raise ValueError('Temiz geliştirme dalı gerekli.')
        head=command(['git','rev-parse','HEAD'])
        info=json.loads(command(['gh','pr','view',branch,'--repo',REPO,'--json','headRefOid,baseRefName,statusCheckRollup']))
        checks=info.get('statusCheckRollup') or []
        if info['headRefOid']!=head or info['baseRefName']!='main' or not checks or any(c.get('conclusion',c.get('state')) not in {'SUCCESS'} for c in checks):
            return 'Main değişmedi: doğru sürümün bütün GitHub kontrolleri başarılı olmalı.'
        command(['gh','pr','merge',branch,'--repo',REPO,'--merge','--match-head-commit',head])
        return 'Main’e birleştirildi. GÜNCELLE düğmesini kullanabilirsiniz.'
    if mode=='publish':
        selected_files(files)
        branch=command(['git','branch','--show-current'])
        if not branch.startswith('jarvis-dev/'):
            raise ValueError('Yayın yalnızca ayrı geliştirme dalından yapılır.')
        from actions import dev_agent
        if dev_agent._job_lock.locked():
            raise ValueError('Kod geliştirme işi henüz bitmedi.')
        command(['gh','auth','status'])
        tests()
        if command(['git','diff','--cached','--name-only']):
            raise ValueError('Önceden hazırlanmış commit değişiklikleri var; önce inceleyin.')
        command(['git','add','--',*files])
        command(['git','commit','-m',instruction or 'JARVIS geliştirmesi'])
        head=command(['git','rev-parse','HEAD'])
        command(['git','push','-u','origin',branch])
        prs=json.loads(command(['gh','pr','list','--repo',REPO,'--head',branch,'--json','number']))
        if not prs:
            command(['gh','pr','create','--repo',REPO,'--base','main','--head',branch,'--title',instruction[:120] or 'JARVIS geliştirmesi','--body','JARVIS geliştirme alanında hazırlanmış değişiklikler. Python testleri yerel olarak çalıştırıldı; GitHub kontrolleri birleştirmeden önce zorunludur.'])
        checks=json.loads(command(['gh','pr','checks',branch,'--repo',REPO,'--json','name,state']))
        if not checks or any(c['state']!='SUCCESS' for c in checks):
            return 'PR oluşturuldu; kontroller henüz başarılı değil. Main değişmedi. Daha sonra merge işlemiyle tekrar kontrol edin.'
        command(['gh','pr','merge',branch,'--repo',REPO,'--merge','--match-head-commit',head],timeout=90)
        return 'Main’e birleştirildi. GÜNCELLE düğmesiyle bu sürümü yükleyebilirsiniz.'
    raise ValueError('Geçersiz işlem.')


def self_release(instruction, player):
    """Work from the current remote main, independently of the user's checkout."""
    from actions import dev_agent
    from core.code_checks import Protection

    command(["gh", "auth", "status"], cwd=Path.home())
    with tempfile.TemporaryDirectory(prefix="jarvis-release-") as temp:
        folder = Path(temp) / "source"
        remote = f"https://github.com/{REPO}.git"
        command(["git", "clone", "--branch", "main", "--single-branch", remote, str(folder)],
                cwd=Path(temp))
        branch = f"jarvis-dev/release-{time.time_ns()}"
        command(["git", "switch", "-c", branch], cwd=folder)

        if not dev_agent._job_lock.acquire(False):
            raise RuntimeError("Başka bir kod geliştirme işi sürüyor.")
        try:
            dev_agent._new_job(folder, "JARVIS", instruction, player, kind="improve")
            result = dev_agent._improve_folder(
                folder,
                instruction + "\n\nModify only JARVIS source for the benign user request. "
                "Follow AGENTS.md. Keep the release workflow, updater, secrets and CI gates intact. "
                "Do not add offensive automation, exploits, or arbitrary command execution.",
                player,
                open_editor=False,
            )
            dev_agent._update("finished", result=result, finished=time.time())
        finally:
            dev_agent._job_lock.release()

        changed = command(["git", "-c", "core.quotePath=false", "ls-files",
                           "--modified", "--others", "--exclude-standard"], cwd=folder)
        files = sorted(set(changed.splitlines()) - {""})
        generated = (".jarvis_backup/",)
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
        command(["git", "commit", "-m", "JARVIS: kullanıcı geliştirme isteği"], cwd=folder)
        head = command(["git", "rev-parse", "HEAD"], cwd=folder)
        command(["git", "push", "origin", branch], cwd=folder)
        pr = command(["gh", "pr", "create", "--repo", REPO, "--base", "main",
                      "--head", branch, "--title", "JARVIS geliştirmesi",
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
        player.write_log("GELİŞTİRME: Main’e alındı, JARVIS güncelleniyor. " + pr)
        player.request_app_update()
        return "GitHub birleştirmesi doğrulandı ve güncelleme isteği gönderildi."


def run(parameters, player=None, session_memory=None):
    mode=parameters.get('mode','')
    instruction=str(parameters.get('instruction','')).strip()
    if mode == "self_edit":
        if not instruction:
            return "JARVIS’te yapılacak kod değişikliğini tarif et."
        if not player:
            return "Geliştirme ilerlemesi için JARVIS arayüzü gerekli."
        if not _LOCK.acquire(False):
            return "Bir GitHub işlemi zaten çalışıyor."

        def prepare_and_edit():
            try:
                from actions import dev_agent

                if dev_agent._job_lock.locked():
                    raise ValueError("Kod geliştirme işi tamamlanınca tekrar deneyin.")
                if WORK.resolve() == Path(__file__).resolve().parents[1]:
                    raise ValueError("JARVIS’i normal kurulumdan aç; bu klasör geliştirme kopyası.")
                if not (WORK / ".git").exists():
                    workflow("prepare", "", [])
                branch = command(["git", "branch", "--show-current"])
                if not branch.startswith("jarvis-dev/"):
                    raise ValueError("JARVIS değişiklikleri geliştirme dalında hazırlanır.")
                notes = (
                    "\n\nWork only in this development checkout. Follow AGENTS.md. "
                    "For a new JARVIS tool, use the existing Python plugin contract; "
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
            threading.Thread(target=prepare_and_edit, daemon=True, name="jarvis-self-edit").start()
        except Exception:
            _LOCK.release()
            raise
        return "JARVIS kod değişikliği için ayrı geliştirme alanı hazırlanıyor."

    if mode=='develop':
        if _LOCK.locked(): return 'GitHub işlemi bitene kadar kod düzenleme beklemeli.'
        if not (WORK/'.git').exists(): return 'Önce geliştirme alanını hazırlayın.'
        from actions.dev_agent import dev_agent
        return dev_agent({'mode':'improve','folder':str(WORK),'description':instruction},player=player)
    if not player: return 'Geliştirme ilerlemesi için JARVIS arayüzü gerekli.'
    if mode == "self_release" and (
        not instruction or not callable(getattr(player, "request_app_update", None))
    ):
        return "Kod değişikliğini açıkça belirt ve JARVIS masaüstü arayüzünü kullan."

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
        threading.Thread(target=work,daemon=True,name='jarvis-github').start()
    except RuntimeError:
        _LOCK.release()
        return 'Geliştirme işi başlatılamadı. Tekrar deneyebilirsiniz.'
    return 'GitHub geliştirme işlemi arka planda başladı; sonucu ekranda göstereceğim.'
