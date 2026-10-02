"""
Ýctimai sayt (Ana s?hif? / Funksiyalar / Qiym?tl?r / Haqqýmýzda / FAQ / ?laq?) üçün baþlanðýc
m?zmunu bazaya yazýr. Bunsuz bu s?hif?l?r frontend-in öz "FALLBACK" (ehtiyat) m?tni il?
görünür (kod içind? sabit), baza is? boþ qalýr — Baþ Admin /kapitan-dan redakt? etm?k
ist?y?nd? d?yiþiklik heç bir yer? yazýlmýr. Bu ?mr frontend-d?ki hazýrký m?tni EYNÝ ÝL?
bazaya köçürür ki, saytýn görünüþü d?yiþm?sin, amma artýq h?qiq?t?n bazadan idar? olunsun.

Ýdempotentdir — t?krar iþl?dils?, mövcud qeydl?ri yalnýz yenil?yir (yeni sur?t yaratmýr).
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from sitecontent.cache import invalidate_site_content_cache
from sitecontent.models import AboutValue, FaqItem, FeatureItem, HomeStep, SiteSettings
from tenants.models import Plan


class Command(BaseCommand):
    help = "Ýctimai saytýn (Ana s?hif?, Funksiyalar, Qiym?tl?r, Haqqýmýzda, FAQ, ?laq?) baþlanðýc m?zmununu bazaya yazýr."

    def say(self, msg, style=None):
        try:
            self.stdout.write(style(msg) if style else msg)
        except UnicodeEncodeError:
            self.stdout.write(msg.encode("ascii", "replace").decode())

    @transaction.atomic
    def handle(self, *args, **opts):
        self.seed_settings()
        self.seed_faq()
        self.seed_features()
        self.seed_about_values()
        self.seed_home_steps()
        self.seed_plans()
        invalidate_site_content_cache()
        self.say("")
        self.say("Sayt m?zmunu bazaya yazýldý — /kapitan panelind?n artýq redakt? edil? bil?r.", self.style.SUCCESS)

    # ------------------------------------------------------------ Sayt ayarlarý (t?k s?tir)
    def seed_settings(self):
        s = SiteSettings.load()
        s.brand_name = "SERVIO"
        s.tagline = ""
        s.hero_title = "Servisinizi daha rahat idar? edin."
        s.hero_subtitle = (
            "Müþt?ril?r, t?mirl?r, g?lir-x?rc, anbar, borclar v? hesabatlar — hamýsý bir "
            "platformada. Telefon v? kompüter servis biznesl?r üçün aðýllý idar?etm? sistemi."
        )
        s.email = "info@servio.az"
        s.phone = "+994 50 000 00 00"
        s.whatsapp = "994500000000"
        s.address = "Baký, Az?rbaycan"
        s.hours = "Bazar ert?si – Þ?nb?, 09:00 – 18:00"
        s.footer_note = ""
        s.save()
        self.say("Sayt ayarlarý yazýldý (brend, hero m?tni, ?laq? m?lumatlarý).")

    # ------------------------------------------------------------------------------- FAQ
    def seed_faq(self):
        items = [
            ("Servio kiml?r üçündür?",
             "Telefon v? kompüter t?miri il? m?þðul olan ustalar v? servis m?rk?zl?ri üçün. "
             "Müþt?ri, t?mir, kassa, anbar, borc v? hesabatlarýn hamýsý bir yerd?dir."),
            ("Telefonda iþl?yirmi?",
             "B?li. Sistem h?m kompüter, h?m d? telefon ekranýnda rahat iþl?yir, ona gör? d? "
             "ustalar iþin ortasýnda da m?lumat daxil ed? bil?r."),
            ("M?nim m?lumatýmý baþqa servis gör? bil?rmi?",
             "Xeyr. H?r servis ayrýca hesab kimi iþl?yir v? yalnýz öz müþt?ril?rini, g?lirini, "
             "x?rcl?rini, borclarýný v? t?mir m?lumatlarýný görür."),
            ("T?l?b?y? giriþ vers?m, qazancý gör?c?kmi?",
             "Yox. Rol v? icaz?l?r bölm?sind?n þ?yird üçün g?lir v? net qazanc r?q?ml?rini "
             "baðlaya bil?rsiniz. O, t?mirl?rl? iþl?y? bil?r, amma maya, qazanc v? g?lir ona "
             "görünmür."),
            ("Bir neç? filialla iþl?m?k mümkündürmü?",
             "B?li. Basic planda 1, Pro planda 5 filial d?st?kl?nir. H?r plan üzr? filial v? "
             "istifad?çi limiti Qiym?tl?r s?hif?sind? göst?rilib."),
            ("T?chizatçýya borcu nec? izl?yir?m?",
             "T?miri qeyd ed?nd? detalý t?chizatçýdan borcla aldýðýnýzý seçirsiniz, m?bl?ð "
             "t?chizatçýnýn hesabýna borc kimi yazýlýr. Öd?y?nd?n sonra öd?nilmiþ kimi "
             "iþar?l?yirsiniz. Detal istifad? olunmayýbsa (m?s?l?n, plata t?miri), bu sah?ni "
             "doldurmaq m?cburi deyil."),
            ("Z?man?t nec? hesablanýr?",
             "Cihaz t?hvil veril?nd? z?man?t müdd?ti avtomatik baþlayýr v? gün-gün geri sayýlýr. "
             "Müdd?ti bit?n z?man?t “müdd?ti bitib” kimi göst?rilir."),
            ("Pulsuz baþlaya bil?r?mmi?",
             "B?li, pulsuz sýnaqla baþlaya bil?rsiniz. Müdd?t v? þ?rtl?r bar?d? ?laq? "
             "s?hif?sind?n biz? yazýn."),
        ]
        for i, (q, a) in enumerate(items):
            FaqItem.objects.update_or_create(question=q, defaults={"answer": a, "order": i, "is_active": True})
        self.say(f"FAQ: {len(items)} sual-cavab yazýldý.")

    # -------------------------------------------------------------------------- Funksiyalar
    def seed_features(self):
        items = [
            ("Users", "primary", "Müþt?ril?r", "Müþt?ri bazasýný yaradýn v? asanlýqla idar? edin.",
             ["Ad, telefon v? qeydl?r üzr? sür?tli axtarýþ", "H?r müþt?rinin bütün t?mir tarixç?si",
              "Öd?niþl?r, borclar v? z?man?tl?r bir profild?"]),
            ("Wrench", "dark", "T?mir / Xidm?tl?r", "T?mir prosesini izl?yin, statuslarý qeyd edin.",
             ["H?r xidm?t? avtomatik nömr? (SRV-2026-000125)",
              "Q?bul edildi › Diaqnostika › Hazýrdýr › T?hvil verildi",
              "Qazanc satýþ v? maya d?y?rind?n avtomatik hesablanýr"]),
            ("Boxes", "primary", "Anbar", "Ehtiyat hiss?l?ri v? mallarýn idar? edilm?si.",
             ["Alýþ v? satýþ qiym?ti, say v? minimum h?dd", "Stok azaldýqda x?b?rdarlýq",
              "Detal istifad? olunanda say avtomatik azalýr"]),
            ("Truck", "dark", "T?chizatçýlar", "T?chizatçýlarý ?lav? edin, borclarý izl?yin.",
             ["Alýþ tarixç?si v? ümumi m?bl?ð", "Ay sonu hesablaþma üçün borc qeydi",
              "T?mird?n avtomatik t?chizatçý borcu yaratmaq"]),
            ("Wallet", "primary", "Kassa", "G?lir v? x?rcl?ri idar? edin, kassa balansýný görün.",
             ["Xidm?t öd?niþl?ri v? dig?r g?lirl?r",
              "X?rcl?r v? t?chizatçý öd?niþl?ri balansdan çýxýlýr", "Bütün ?m?liyyatlarýn tarixç?si"]),
            ("BarChart3", "dark", "Hesabatlar", "Günd?lik, aylýq, illik analizl?r v? qrafikl?r.",
             ["Ýst?nil?n tarix aralýðý üzr? hesabat", "Xidm?t v? t?chizatçý üzr? analiz",
              "Ümumi satýþ, maya, x?rc v? xalis qazanc"]),
            ("ShieldCheck", "primary", "Z?man?tl?r", "Z?man?t müdd?tl?rini izl?yin, müþt?ril?r? x?b?rdarlýq edin.",
             ["T?hvild?n sonra z?man?t avtomatik geri sayýlýr", "Bitm?y? 3 gün qalanlar ayrýca görünür",
              "7 / 14 / 30 / 90 gün v? ya z?man?tsiz"]),
            ("Printer", "dark", "Q?bz / Çap", "R?smi q?bz v? t?hvil-t?slim s?n?dl?rini çap edin.",
             ["A4 formatýnda s?liq?li t?hvil-t?slim aktý", "Servisin öz z?man?t þ?rtl?ri m?tni",
              "Müþt?ri v? usta imza sah?l?ri"]),
        ]
        for i, (icon, tone, title, short, points) in enumerate(items):
            FeatureItem.objects.update_or_create(
                title=title,
                defaults={
                    "icon": icon, "tone": tone, "short_description": short,
                    "points": "\n".join(points), "order": i, "is_active": True,
                },
            )
        self.say(f"Funksiyalar: {len(items)} kart yazýldý.")

    # -------------------------------------------------------------------------- Haqqýmýzda
    def seed_about_values(self):
        items = [
            ("Gauge", "Sad?lik",
             "M?qs?d mühasibat proqramý kimi mür?kk?b sistem yox, ustanýn günd?lik iþini "
             "sür?tl?ndir?n rahat al?tdir. Müþt?rid?n çapa q?d?r proses bir neç? klikdir."),
            ("Lock", "M?lumat t?hlük?sizliyi",
             "H?r servis yalnýz öz m?lumatýný görür. Müþt?ri, g?lir, x?rc, t?chizatçý v? t?mir "
             "m?lumatlarý baþqa servis? heç vaxt görünmür."),
            ("Puzzle", "Böyüm?y? açýq",
             "Sistem modul ?saslýdýr: filial, iþçi rollarý, anbar v? yeni imkanlar biznesiniz "
             "böyüdükc? ?lav? olunur."),
        ]
        for i, (icon, title, text) in enumerate(items):
            AboutValue.objects.update_or_create(
                title=title, defaults={"icon": icon, "text": text, "order": i, "is_active": True},
            )
        self.say(f"Haqqýmýzda: {len(items)} d?y?r kartý yazýldý.")

    # --------------------------------------------------------------------- Nec? iþl?yir (Ana s.)
    def seed_home_steps(self):
        items = [
            ("1", "Müþt?ri v? cihazý qeyd edin",
             "Müþt?ri, cihaz, þikay?t v? görül?c?k iþi bir neç? klikl? ?lav? edin."),
            ("2", "Maya, satýþ v? t?chizatçýný seçin",
             "Qazanc avtomatik hesablanýr, t?chizatçý borcu is? lazým olarsa avtomatik yazýlýr."),
            ("3", "T?hvil verin v? çap edin",
             "Öd?niþi qeyd edin, A4 q?bz çap edin, z?man?t avtomatik geri saymaða baþlasýn."),
        ]
        for i, (number, title, desc) in enumerate(items):
            HomeStep.objects.update_or_create(
                title=title, defaults={"number": number, "description": desc, "order": i, "is_active": True},
            )
        self.say(f"\"Nec? iþl?yir\": {len(items)} addým yazýldý.")

    # ---------------------------------------------------------------------------- Planlar
    def seed_plans(self):
        plans = [
            dict(name="Basic", price_monthly=19, max_branches=1, max_users=3, sort_order=1,
                 is_featured=False, show_on_pricing_page=True,
                 public_description="T?k usta v? kiçik servisl?r üçün",
                 public_features=[
                     "Müþt?ril?r v? t?mir qeydiyyatý", "Kassa, x?rcl?r v? borclar",
                     "Z?man?t izl?m? v? A4 q?bz", "Anbar v? t?chizatçýlar", "Hesabatlar v? analitika",
                 ]),
            dict(name="Pro", price_monthly=49, max_branches=5, max_users=15, sort_order=2,
                 is_featured=True, show_on_pricing_page=True,
                 public_description="Böyüy?n v? çox filiallý servisl?r üçün",
                 public_features=[
                     "Basic planýn bütün imkanlarý", "5 filialad?k bir hesabda",
                     "15 istifad?çiy? q?d?r (usta, t?l?b?, kassir)",
                     "Rol v? icaz?l?rin geniþ idar?si", "Böyük komanda üçün rahat n?zar?t",
                 ]),
        ]
        for p in plans:
            features = p.pop("public_features")
            Plan.objects.update_or_create(
                name=p.pop("name"), defaults={**p, "public_features": "\n".join(features)},
            )
        self.say(f"Planlar: {len(plans)} plan yazýldý (Basic, Pro).")