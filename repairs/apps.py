from django.apps import AppConfig


class RepairsConfig(AppConfig):
    name = 'repairs'

    def ready(self):
        # Windows-da Python-un defolt mətn kodlaşdırması UTF-8 deyil (adətən cp1252) —
        # reportlab (xhtml2pdf-in PDF mühərriki) öz daxili font/resurs fayllarını bu
        # defolt ilə açır və Azərbaycan hərfləri/dırnaq işarələri olan HTML-i emal edərkən
        # "UnicodeDecodeError: 'utf-8' codec can't decode byte 0x93" ilə çökür. Bu, prosesin
        # "üstünlük verilən kodlaşdırması"nı məcburi UTF-8 edir — yalnız Windows-da effektlidir,
        # Linux/macOS-da onsuz da UTF-8-dir, zərərsizdir.
        import locale
        locale.getpreferredencoding = lambda do_setlocale=True: "utf-8"

        from . import signals  # noqa: F401 — status tarixçəsi siqnalını qeydə alır