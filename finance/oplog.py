"""Silinmiş əməliyyatlar jurnalı üçün köməkçilər: "kim sildi" məlumatı + log yazma."""
import json
from contextlib import contextmanager
from contextvars import ContextVar

_actor = ContextVar("oplog_actor", default=None)
_suppress_cash = ContextVar("oplog_suppress_cash", default=False)


@contextmanager
def deletion_actor(user):
    """View-larda `with deletion_actor(request.user): obj.delete()` — silməni kimin etdiyini siqnala çatdırır."""
    token = _actor.set(user if getattr(user, "is_authenticated", False) else None)
    try:
        yield
    finally:
        _actor.reset(token)


@contextmanager
def suppress_cash_logs():
    """Təmir silinəndə onun kassa sətirləri ayrıca log yazılmasın (təmirin jurnalında artıq var)."""
    token = _suppress_cash.set(True)
    try:
        yield
    finally:
        _suppress_cash.reset(token)


def cash_logs_suppressed():
    return _suppress_cash.get()


def write_log(shop, kind, title, amount, details):
    from .models import OperationLog
    user = _actor.get()
    OperationLog.objects.create(
        shop=shop, kind=kind, title=title[:255], amount=amount,
        details=json.dumps(details, ensure_ascii=False, default=str),
        deleted_by=user, deleted_by_name=(user.get_full_name() or user.username) if user else "Sistem",
    )
